"""Claude CLI, quota, provider isolation and desktop recovery regressions."""
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from dataclasses import replace
from urllib.error import HTTPError

import pytest

from recharge_ai_task import claude, cli, targets, wrapper, watch, watch_state, tray_control
from recharge_ai_task.config import AppConfig
from recharge_ai_task.quota import (RateWindow, Quota, quota_blocked, exhausted_windows,
                                   quota_to_snapshot, quota_from_snapshot, format_quota)
from recharge_ai_task.targets import Target


NOW = dt.datetime(2026, 11, 6, 14, 0, tzinfo=dt.timezone.utc)


@pytest.mark.parametrize('text,expected', [
    ('3pm (UTC)', '2026-11-06T15:00:00+00:00'),
    ('3:45pm (UTC)', '2026-11-06T15:45:00+00:00'),
    ('3:45 pm (UTC)', '2026-11-06T15:45:00+00:00'),
    ('12am (UTC)', '2026-11-07T00:00:00+00:00'),
    ('Nov 12 at 3pm (UTC)', '2026-11-12T15:00:00+00:00'),
    ('Dec 1, 3:45pm (UTC)', '2026-12-01T15:45:00+00:00'),
    ('Jan 2 at 1am (UTC)', '2027-01-02T01:00:00+00:00'),
    ('Mon 12:00am (UTC)', '2026-11-09T00:00:00+00:00'),
    ('10am (America/New_York)', '2026-11-06T15:00:00+00:00'),
    ('in 2 hrs 30 min', '2026-11-06T16:30:00+00:00'),
])
def test_reset_formats(text, expected):
    assert claude.parse_reset_time(text, NOW) == int(dt.datetime.fromisoformat(expected).timestamp())


@pytest.mark.parametrize('text', [
    "You've hit your limit · resets 3pm (UTC)\n",
    "You've hit your session limit · resets 3:45pm (UTC)\n",
    "You've hit your weekly limit · resets Nov 12 at 3pm (UTC)\n",
    "Usage limit reached · limit resets 3:45pm\n",
    "Usage limit. Try again in 2 hours.\n",
])
def test_claude_limit_messages(text):
    result = claude.ClaudeLimitWatcher().feed(text)
    assert result is not None and result[0] > 0


def test_partial_and_nonlimit_output():
    parser = claude.ClaudeLimitWatcher()
    assert parser.feed('ordinary assistant response\n') is None
    assert parser.feed("You've hit your limit · resets ") is None
    assert parser.feed('3:45pm (UTC)\n') is not None
    parser.reset()
    assert parser.feed('Usage limit · resets nonsense\n') is None


@pytest.mark.parametrize('text', [
    'Usage limit reached · limit resets 3pm\nContinuing automatically at 3pm · Esc to cancel\n',
    'Usage limit reached · continuing automatically at 3pm · esc to cancel',
    'Usage limit reset · Continuing automatically',
    'Automatic continue cancelled',
])
def test_native_recovery_does_not_queue_extra_prompt(text):
    parser = claude.ClaudeLimitWatcher()
    assert parser.feed(text) is None
    assert parser.native_owned


def test_native_recovery_arriving_after_limit_detection(monkeypatch):
    class Pty:
        def isalive(self): return True
        def read(self, size): return 'Continuing automatically at 3pm · Esc to cancel\n'
    parser = claude.ClaudeLimitWatcher()
    assert wrapper.wait_for_claude_reset(Pty(), wrapper.StopEvent(), 0, parser) is None


def usage():
    return {'five_hour': {'utilization': 70.5, 'resets_at': '2026-11-06T18:00:00Z'},
            'seven_day': {'utilization': 21, 'resets_at': '2026-11-10T18:00:00Z'},
            'seven_day_sonnet': {'utilization': 100, 'resets_at': '2026-11-11T18:00:00Z'},
            'extra_usage': {'is_enabled': True, 'used_credits': 0}}


def test_every_usage_window_blocks_and_survives_snapshot():
    quota = claude.parse_usage(usage())
    assert quota_blocked(quota)
    assert [w.label for w in exhausted_windows(quota)] == ['Seven day sonnet']
    assert quota_from_snapshot(quota_to_snapshot(quota)) == quota
    assert 'Seven day sonnet' in format_quota(quota)
    assert 'Claude Quota' in format_quota(quota)
    # Merely enabling extra usage does not prove it is funded or usable.
    assert not quota.has_credits


@pytest.mark.parametrize('data', [
    {}, [], {'five_hour': {'utilization': 'NaN', 'resets_at': '2026-11-06T18:00:00Z'}},
    {'five_hour': {'utilization': 40, 'resets_at': None}},
    {'five_hour': {'utilization': 40, 'resets_at': '2026-11-06T18:00:00'}},
])
def test_invalid_or_missing_usage_never_means_available(data):
    with pytest.raises(RuntimeError): claude.parse_usage(data)


def test_unused_window_and_weekly_only_account():
    data = {'five_hour': None, 'seven_day': {'utilization': 0, 'resets_at': None}}
    quota = claude.parse_usage(data)
    assert not quota_blocked(quota) and quota.primary.window_duration_mins == 10080
    assert 'not started' in format_quota(quota)


def credentials(tmp_path, monkeypatch, **overrides):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    data = dict(accessToken='test-token-do-not-display', expiresAt=9999999999999, subscriptionType='max')
    data.update(overrides)
    path = tmp_path / '.credentials.json'
    path.write_text(json.dumps({'claudeAiOauth': data}))
    return path


def test_usage_read_is_fixed_origin_readonly_and_never_saves_token(tmp_path, monkeypatch):
    path = credentials(tmp_path, monkeypatch)
    before = path.read_bytes()
    requests = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def read(self, limit): return json.dumps(usage()).encode()
    class Opener:
        def open(self, request, timeout):
            requests.append(request)
            assert timeout == 15
            return Response()
    monkeypatch.setattr(claude, 'build_opener', lambda *handlers: Opener())
    assert claude.fetch_claude_quota().plan_type == 'Claude max'
    request = requests[0]
    assert request.get_method() == 'GET'
    assert request.full_url == 'https://api.anthropic.com/api/oauth/usage'
    assert request.get_header('Authorization') == 'Bearer test-token-do-not-display'
    assert path.read_bytes() == before
    assert claude._NoRedirect().redirect_request(None, None, None, None, None, None) is None


@pytest.mark.parametrize('code', [401, 403, 429, 500])
def test_http_failures_are_not_recovery_or_credentials_in_errors(tmp_path, monkeypatch, code):
    credentials(tmp_path, monkeypatch)
    class Opener:
        def open(self, *_args, **_kwargs):
            raise HTTPError('secret-url', code, 'secret body test-token-do-not-display', {}, None)
    monkeypatch.setattr(claude, 'build_opener', lambda *_: Opener())
    with pytest.raises(RuntimeError) as error: claude.fetch_claude_quota()
    assert str(code) in str(error.value)
    assert 'secret' not in str(error.value) and 'test-token' not in str(error.value)


def test_expired_credentials_require_claude_refresh(tmp_path, monkeypatch):
    credentials(tmp_path, monkeypatch, expiresAt=1)
    monkeypatch.setattr(claude, 'build_opener', lambda *_: pytest.fail('Network on expired login'))
    with pytest.raises(RuntimeError, match='expired'): claude.fetch_claude_quota()


def test_missing_credentials_are_actionable(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    with pytest.raises(RuntimeError, match='claude auth login'): claude.fetch_claude_quota()


def test_executable_discovery(tmp_path, monkeypatch):
    exe = tmp_path / 'custom-claude'
    exe.write_text('test')
    monkeypatch.setenv('CLAUDE_CLI_PATH', str(exe))
    assert claude.discover_claude() == str(exe)
    assert claude.discover_claude(str(exe)) == str(exe)
    with pytest.raises(FileNotFoundError): claude.discover_claude(str(tmp_path / 'missing'))


def test_provider_and_recipient_roundtrip_preserves_codex_keys():
    codex = Target('window', '42', 'Codex', instance=':0:7', pid=7)
    anthropic = replace(codex, title='Claude', provider='claude', send_goal=True)
    old_key = '["window",":0:7","42"]'
    assert codex.key == old_key and anthropic.key != old_key
    assert anthropic.signal_actions(True) == (True, False)
    config = AppConfig(provider='claude', claude_path='/cli/claude', claude_args=['--continue'],
                       desktop_targets=[codex.to_dict(), anthropic.to_dict()])
    config.save()
    loaded = AppConfig.load()
    assert [t.provider for t in loaded.targets()] == ['codex', 'claude']
    assert [t.provider for t in loaded.targets('claude')] == ['claude']
    assert loaded.claude_path == '/cli/claude' and loaded.claude_args == ['--continue']
    claude_checkpoint = watch_state.state_path(loaded)
    claude_settings = tray_control.watch_settings(loaded)
    loaded.provider = 'codex'
    assert [t.key for t in loaded.targets("codex")] == [old_key]
    assert watch_state.state_path(loaded) == claude_checkpoint
    assert tray_control.watch_settings(loaded) == claude_settings
    assert len(loaded.all_targets()) == 2


def test_claude_discovery_never_reads_codex(tmp_path, monkeypatch):
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path))
    target = Target('window', '42', 'Claude', provider='claude', pid=7)
    monkeypatch.setattr(targets, 'discover_windows', lambda provider: [target] if provider == 'claude' else [])
    monkeypatch.setattr(targets, 'discover_homes', lambda: pytest.fail('Read Codex homes for Claude'))
    assert targets.discover_targets('claude').targets == [target]


def test_claude_window_delivery_checks_provider_pid_and_focus(monkeypatch):
    from recharge_ai_task import target_delivery as delivery
    target = Target('window', '42', 'Claude', provider='claude', pid=7)
    providers, commands = [], []
    def windows(provider):
        providers.append(provider)
        return [target]
    monkeypatch.setattr(delivery, 'discover_windows', windows)
    monkeypatch.setattr(delivery.sys, 'platform', 'linux')
    monkeypatch.setattr(delivery.subprocess, 'run', lambda args, **kw: commands.append(args))
    monkeypatch.setattr(delivery.subprocess, 'check_output', lambda *args, **kw: '42\n')
    result = delivery.deliver_targets([target], 'Continue', key_delay=0)[0]
    assert result.success and providers == ['claude']
    assert commands[-1] == ['xdotool', 'key', '--clearmodifiers', 'Return']
    assert not delivery.recover_target(target, 'Continue').success
    monkeypatch.setattr(delivery, 'discover_windows', lambda _: [replace(target, provider='codex')])
    commands.clear()
    assert not delivery.deliver_targets([target], 'Continue')[0].success
    assert commands == []


def test_claude_desktop_waits_for_all_limits_and_sends_only_claude(monkeypatch):
    target = Target('window', '42', 'Claude', provider='claude', pid=7, send_prompt=True, send_goal=False)
    codex = replace(target, id='43', title='Codex', provider='codex')
    AppConfig(provider='claude', desktop_targets=[target.to_dict(), codex.to_dict()]).save()
    blocked = claude.parse_usage(usage())
    available = replace(blocked, rate_limit_reached=False, additional=())
    sequence = iter([RuntimeError('offline'), blocked, blocked, available, available, available])
    count, sends = [], []
    now = [100.]
    class Stop:
        def is_set(self): return len(count) >= 6
        def wait(self, seconds): count.append(seconds); now[0] += seconds
    def fetch():
        item = next(sequence)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(claude, 'fetch_claude_quota', fetch)
    monkeypatch.setattr(watch, 'discover_codex', lambda *_: pytest.fail('Claude watch needs no Codex'))
    monkeypatch.setattr(watch.time, 'time', lambda: now[0])
    def deliver(selected, text, **kwargs):
        from recharge_ai_task.target_delivery import DeliveryResult
        sends.extend((t.provider, t.id, text, now[0]) for t in selected)
        return [DeliveryResult(t, True, 'accepted') for t in selected]
    monkeypatch.setattr(watch, 'send_signals', deliver)
    state = watch.WatchState()
    config = watch.WatchConfig(provider='claude', desktop_targets=(target, codex), grace_seconds=10, poll_seconds=5, state=state)
    assert watch.run_desktop_watch(config, Stop()) == 0
    assert sends == [('claude', '42', 'Continue', 125.)]
    assert state.progress['quota_snapshot']['plan_type'].startswith('Claude')


def test_cli_provider_uses_separate_paths_args_and_prompt(monkeypatch):
    AppConfig(codex_args=['codex-arg'], claude_args=['--continue'], goal_mode=True).save()
    captured = []
    monkeypatch.setattr(cli, 'run_wrapper', lambda config: captured.append(config) or 0)
    assert cli.main(['run', '--provider', 'claude', '--claude', '/claude']) == 0
    config = captured[0]
    assert config.provider == 'claude' and config.claude_path == '/claude'
    assert config.claude_args == ['--continue']
    assert wrapper._continue_prompt(config, True) == 'Continue'
    assert cli.main(['run', '--provider', 'claude', '--', '--resume', 'session']) == 0
    assert captured[1].claude_args == ['--resume', 'session']


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX PTY subprocess')
def test_claude_cli_actual_pty_reset_and_continue(tmp_path):
    script = tmp_path / 'fake_claude.py'
    receipt = tmp_path / 'receipt.txt'
    script.write_text('print("Usage limit. Try again in 1 second.", flush=True)\n'
                      'text = input()\nprint("RECEIVED:" + text, flush=True)\n'
                      f'from pathlib import Path\nPath({str(receipt)!r}).write_text(text)\n'
                      'raise SystemExit(0 if text == "Continue" else 2)\n')
    result = subprocess.run([sys.executable, '-m', 'recharge_ai_task.cli', 'run',
                             '--provider', 'claude', '--claude', sys.executable,
                             '--goal', '--grace', '0', '--', str(script)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert receipt.read_text() == 'Continue'
    assert '/goal resume' not in result.stdout + result.stderr


def test_repeated_output_does_not_move_relative_reset(monkeypatch):
    parser = claude.ClaudeLimitWatcher()
    result = parser.feed('Usage limit. Try again in 1 second.\n')
    # Re-reading the same buffered limit must not start another relative delay.
    monkeypatch.setattr(claude, 'parse_reset_time', lambda *_: pytest.fail('Reparsed old reset'))
    assert parser.feed('more output\n') == result


def test_manual_terminal_input_cancels_pending_continuation():
    import threading
    event = threading.Event(); event.set()
    class Pty:
        def isalive(self): return True
        def read(self, *_): pytest.fail('Read after manual cancellation')
    assert wrapper.wait_for_claude_reset(Pty(), wrapper.StopEvent(), 9999999999,
                                        claude.ClaudeLimitWatcher(), user_input=event) is None


def test_cli_selection_and_clear_preserve_other_provider(monkeypatch):
    codex = Target('thread', 'codex-chat', 'Codex', send_prompt=True, send_goal=False)
    anthropic = Target('window', '42', 'Claude', provider='claude', pid=7, send_prompt=True, send_goal=False)
    AppConfig(desktop_targets=[codex.to_dict()]).save()
    monkeypatch.setattr(targets, 'discover_targets', lambda provider='codex': targets.Inventory([anthropic] if provider == 'claude' else [codex]))
    assert cli.main(['targets', '--provider', 'claude', '--select', '42']) == 0
    config = AppConfig.load()
    assert config.provider == 'codex' and len(config.targets()) == 2
    assert next(t for t in config.all_targets() if t.id == 'codex-chat').send_prompt
    assert cli.main(['targets', '--provider', 'claude', '--clear']) == 0
    config = AppConfig.load()
    assert [t.id for t in config.targets()] == ['codex-chat']
    config.provider = 'codex'
    assert len(config.targets()) == 1 and config.targets()[0].id == 'codex-chat'


def test_tray_claude_launch_uses_its_own_executable_and_args(monkeypatch):
    monkeypatch.setenv('PYSTRAY_BACKEND', 'dummy')
    from recharge_ai_task import tray
    AppConfig(provider='claude', claude_path='/custom/claude', claude_args=['--continue'],
              codex_path='/codex', codex_args=['codex-only']).save()
    launches = []
    class Process:
        def poll(self): return None
    monkeypatch.setattr(tray, '_resolve_cli_exe', lambda: ['recharge-ai-task-cli'])
    monkeypatch.setattr(tray, '_console_command', lambda args: args)
    monkeypatch.setattr(tray.subprocess, 'Popen', lambda args, **kwargs: launches.append(args) or Process())
    app = tray.TrayApp()
    monkeypatch.setattr(app, '_watch_process', lambda: None)
    app.start_goal()
    assert launches == [['recharge-ai-task-cli', 'run', '--provider', 'claude', '--no-goal',
                         '--claude', '/custom/claude', '--', '--continue']]


def test_claude_checkpoint_is_scoped_to_login_directory(tmp_path, monkeypatch):
    target = Target('window', '42', 'Claude', provider='claude')
    config = AppConfig(provider='claude', desktop_targets=[target.to_dict()])
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'one'))
    first = watch_state.state_path(config)
    config.codex_path = '/unrelated/codex'
    assert watch_state.state_path(config) == first
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(tmp_path / 'two'))
    assert watch_state.state_path(config) != first
