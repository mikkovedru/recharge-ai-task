"""OpenCode terminal launch, recovery, isolation and documented limitations."""
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from recharge_ai_task import cli, opencode, providers, targets, watch, wrapper
from recharge_ai_task.config import AppConfig


def test_executable_discovery(tmp_path, monkeypatch):
    executable = tmp_path / 'opencode'
    executable.touch()
    monkeypatch.setenv('OPENCODE_CLI_PATH', str(executable))
    assert opencode.discover_opencode() == str(executable)
    assert opencode.discover_opencode(str(executable)) == str(executable)
    with pytest.raises(FileNotFoundError, match='OpenCode'):
        opencode.discover_opencode(str(tmp_path / 'missing'))
    monkeypatch.delenv('OPENCODE_CLI_PATH')
    monkeypatch.setattr(opencode.shutil, 'which', lambda _: None)
    monkeypatch.setattr(Path, 'home', lambda: tmp_path)
    binary = tmp_path / '.opencode/bin/opencode'
    binary.parent.mkdir(parents=True)
    binary.touch()
    assert opencode.discover_opencode() == str(binary)


def test_cli_settings_and_arguments_are_independent(monkeypatch):
    AppConfig(codex_args=['codex-only'], opencode_args=['--session', 'chosen']).save()
    assert cli.main(['configure', '--provider', 'opencode', '--opencode', '/custom/opencode']) == 0
    saved = AppConfig.load()
    assert saved.provider == 'opencode' and saved.opencode_path == '/custom/opencode'
    captured = []
    monkeypatch.setattr(cli, 'run_wrapper', lambda cfg: captured.append(cfg) or 0)
    assert cli.main(['run']) == 0
    assert captured[0].opencode_args == ['--session', 'chosen']
    assert captured[0].opencode_path == '/custom/opencode'
    assert wrapper._continue_prompt(captured[0], True) == 'Continue'
    assert cli.main(['run', '--provider', 'opencode', '--opencode', '/other', '--', '--continue']) == 0
    assert captured[1].opencode_path == '/other' and captured[1].opencode_args == ['--continue']


def test_no_codex_quota_or_discovery_fallback(monkeypatch, capsys):
    monkeypatch.setattr(cli, 'discover_codex', lambda *_: pytest.fail('Codex discovery'))
    monkeypatch.setattr(targets, 'discover_windows', lambda *_: pytest.fail('Guessed desktop identity'))
    assert cli.main(['quota', '--provider', 'opencode']) == 1
    assert 'model provider' in capsys.readouterr().err
    inventory = targets.discover_targets('opencode')
    assert not inventory.targets and 'wrapped interactive terminal' in inventory.warnings[0]
    assert watch.run_desktop_watch(watch.WatchConfig(provider='opencode')) == 1
    assert 'wrapped interactive terminal' in capsys.readouterr().err


def test_installed_provider_detection(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, 'discover_opencode', lambda *_: '/native/opencode')
    assert providers.installed_providers(AppConfig())['opencode'] == '/native/opencode'


def test_limit_chunks_unknown_time_and_native_retry():
    watcher = opencode.OpenCodeLimitWatcher()
    assert watcher.feed('\x1b[31mRate limit reached; try again in ') is None
    reset, raw = watcher.feed('2 seconds\x1b[0m\n')
    assert reset > 0 and raw == '2 seconds'
    watcher.reset()
    assert watcher.feed('Rate limit reached; try again at someday\n') is None
    watcher.reset()
    assert watcher.feed('Rate limit reached\n') is None
    assert watcher.feed('retrying in 2s attempt #1\n') is None
    assert watcher.native_retry
    assert watcher.feed('some output\n') is None
    assert watcher.feed('Rate limit reached; try again in 3 seconds\n')
    assert not watcher.native_retry


@pytest.mark.parametrize('manual,native', [(True, False), (False, True)])
def test_pending_wait_cancelled_by_input_or_native_retry(manual, native):
    user_input = threading.Event()
    if manual:
        user_input.set()
    class Pty:
        def isalive(self): return True
        def read(self, _): return 'Rate limit reached; retrying in 2s attempt #1\n'
    watcher = opencode.OpenCodeLimitWatcher()
    assert wrapper.wait_for_opencode_reset(Pty(), wrapper.StopEvent(), sys.maxsize,
                                           watcher, 0, user_input) is None
    assert watcher.native_retry == native


def test_later_limit_extends_timer(monkeypatch):
    now = [100]
    monkeypatch.setattr(wrapper.time, 'time', lambda: now[0])
    watcher = opencode.OpenCodeLimitWatcher()
    monkeypatch.setattr(watcher, 'feed', lambda _: (103, '3 seconds'))
    class Pty:
        def isalive(self): return True
        def read(self, _):
            now[0] += 1
            return 'later limit' if now[0] == 101 else ''
    assert wrapper.wait_for_opencode_reset(Pty(), wrapper.StopEvent(), 102, watcher, 1,
                                           threading.Event()) is True
    assert now[0] == 104


def test_tray_launches_opencode_without_codex_goal(monkeypatch):
    monkeypatch.setenv('PYSTRAY_BACKEND', 'dummy')
    from recharge_ai_task import tray
    AppConfig(provider='opencode', opencode_path='/opencode', opencode_args=['--session', 'selected']).save()
    calls = []
    class Process:
        def poll(self): return None
    monkeypatch.setattr(tray, '_resolve_cli_exe', lambda: ['recharge-ai-task-cli'])
    monkeypatch.setattr(tray, '_console_command', lambda args: args)
    monkeypatch.setattr(tray.subprocess, 'Popen', lambda args, **kw: calls.append(args) or Process())
    app = tray.TrayApp()
    monkeypatch.setattr(app, '_watch_process', lambda: None)
    app.start_goal()
    assert calls == [['recharge-ai-task-cli', 'run', '--provider', 'opencode', '--no-goal',
                      '--opencode', '/opencode', '--', '--session', 'selected']]


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX PTY fixture')
@pytest.mark.parametrize('native_retry', [False, True])
def test_actual_pty_recovery_and_native_retry_ownership(tmp_path, native_retry):
    binary = tmp_path / 'opencode'
    receipt = tmp_path / 'receipt'
    binary.write_text(f'''#!{sys.executable}
import select,sys,time
from pathlib import Path
print("Rate limit reached; try again in 1 seconds",flush=True)
if {native_retry!r}:
 print("retrying in 1s attempt #1",flush=True)
 ready,_,_=select.select([sys.stdin],[],[],3)
 Path({str(receipt)!r}).write_text('unexpected' if ready else 'native retry only')
else:
 message=input()
 Path({str(receipt)!r}).write_text(message)
''')
    binary.chmod(0o755)
    result = subprocess.run([sys.executable, '-m', 'recharge_ai_task.cli', 'run', '--provider', 'opencode',
                             '--opencode', str(binary), '--goal', '--grace', '0'],
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert receipt.read_text() == ('native retry only' if native_retry else 'Continue')
    assert '/goal resume' not in result.stdout + result.stderr


def test_native_retry_split_across_chunks():
    watcher = opencode.OpenCodeLimitWatcher()
    assert watcher.feed('Retry') is None
    assert watcher.feed('ing in 2 seconds') is None
    assert watcher.native_retry


def test_noninteractive_command_reports_error_without_traceback(monkeypatch, capsys):
    monkeypatch.setattr(opencode, 'discover_opencode', lambda *_: '/fixture/opencode')
    assert cli.main(['run', '--provider', 'opencode', '--', 'run', 'Continue']) == 1
    assert 'requires a local interactive terminal' in capsys.readouterr().err
