"""Muse's supported CLI allowance contract and safe continuation behavior."""
from dataclasses import replace
import json
import os
import subprocess
import sys
import threading
import time

import pytest

from recharge_ai_task import cli, config, muse, targets, watch, wrapper
from recharge_ai_task.quota import Quota, RateWindow, quota_blocked, format_quota
from recharge_ai_task.targets import Target


def usage(now=None, session=12, weekly=30):
    now = time.time() if now is None else now
    return {'schemaVersion': 1, 'allowance': {'tier': 'test-tier', 'source': 'mint',
        'asOfMs': int(now * 1000),
        'window': {'usedPercent': session, 'resetsAtMs': int((now + 300) * 1000)},
        'weekly': {'usedPercent': weekly, 'resetsAtMs': int((now + 86400) * 1000)}}}


@pytest.mark.parametrize('session,weekly,blocked', [(0,0,False),(100,20,True),(20,100,True),(101,120,True)])
def test_usage_milliseconds_and_both_independent_windows(session, weekly, blocked):
    value = muse.parse_usage(usage(1000, session, weekly), now=1000)
    assert value.primary == RateWindow(session, 300, 1300, 'Session')
    assert value.secondary == RateWindow(weekly, 10080, 87400, 'Weekly')
    assert quota_blocked(value) == blocked
    assert 'Muse Quota' in format_quota(value)


@pytest.mark.parametrize('change', [
    lambda v: v.update(schemaVersion=2),
    lambda v: v.update(schemaVersion=True),
    lambda v: v.update(allowance=None),
    lambda v: v['allowance'].pop('asOfMs'),
    lambda v: v['allowance'].update(asOfMs=879000),
    lambda v: v['allowance'].update(asOfMs=1031000),
    lambda v: v['allowance'].update(asOfMs=float('nan')),
    lambda v: v['allowance'].pop('weekly'),
    lambda v: v['allowance'].update(window=None),
    lambda v: v['allowance'].pop('tier'),
    lambda v: v['allowance']['window'].update(usedPercent=-1),
    lambda v: v['allowance']['window'].update(usedPercent=True),
    lambda v: v['allowance']['weekly'].update(usedPercent=float('inf')),
    lambda v: v['allowance']['window'].update(resetsAtMs='1300000'),
    lambda v: v['allowance']['window'].update(resetsAtMs=0),
    lambda v: v['allowance']['window'].update(windowDurationMins=0),
])
def test_unknown_stale_or_invalid_allowance_never_proves_recovery(change):
    payload = usage(1000)
    change(payload)
    with pytest.raises(RuntimeError): muse.parse_usage(payload, now=1000)


def test_api_key_billing_is_not_subscription_availability():
    with pytest.raises(RuntimeError, match='API-key billing'):
        muse.parse_usage({'schemaVersion':1,'allowance':None,'reason':'api_key'})


def test_reported_session_duration_is_preserved():
    payload = usage(1000)
    payload['allowance']['window']['windowDurationMins'] = 60
    assert muse.parse_usage(payload, now=1000).primary.window_duration_mins == 60


@pytest.mark.parametrize('banner', [
    'Usage limit reached\nThis turn stopped because your usage limit was reached.',
    '\x1b[31mUsage limit reached\x1b[0m\r\n',
    'agent loop failed: usage limit reached\n',
    'Error: usage limit exceeded\n',
])
def test_native_limit_banner_does_not_invent_a_reset_time(banner):
    parser = muse.MuseLimitWatcher()
    result = parser.feed(banner)
    assert result is not None and result[0] is None
    parser.reset()
    assert parser.feed('ordinary response\n') is None


def test_fragmented_banner_and_false_positives():
    parser = muse.MuseLimitWatcher()
    assert parser.feed('Usage lim') is None
    assert parser.feed('it reached\n') is not None
    parser.reset()
    assert parser.feed('Explain what usage limit reached means in this code.\n') is None
    assert parser.feed('HTTP 429 server rate limited\n') is None


def test_usage_subprocess_is_bounded_and_does_not_run_a_model(tmp_path, monkeypatch):
    binary = tmp_path / 'muse'; binary.write_text('fixture')
    calls = []
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, json.dumps(usage()), '')
    monkeypatch.setattr(muse.subprocess, 'run', run)
    quota = muse.fetch_muse_quota(str(binary), timeout=7)
    assert not quota_blocked(quota)
    argv, kwargs = calls[0]
    assert argv == [str(binary), 'usage', '--json']
    assert kwargs['timeout'] == 7 and kwargs['env']['MUSE_NO_AUTO_UPDATE'] == '1'
    assert 'shell' not in kwargs


@pytest.mark.parametrize('variant', ['failure','timeout','invalid_json'])
def test_usage_errors_do_not_leak_subprocess_output_or_auth(tmp_path, monkeypatch, variant):
    binary = tmp_path / 'muse'; binary.write_text('fixture')
    def run(*args, **kwargs):
        if variant == 'timeout':raise subprocess.TimeoutExpired('secret-command',7)
        return subprocess.CompletedProcess(args[0], 1 if variant == 'failure' else 0,
                                           'secret-stdout', 'secret-token')
    monkeypatch.setattr(muse.subprocess, 'run', run)
    with pytest.raises(RuntimeError) as error:muse.fetch_muse_quota(str(binary))
    assert 'secret' not in str(error.value)


def test_executable_discovery(tmp_path, monkeypatch):
    binary = tmp_path / 'custom-muse'; binary.write_text('fixture')
    monkeypatch.setenv('MUSE_CLI_PATH', str(binary))
    assert muse.discover_muse() == str(binary)
    assert muse.discover_muse(str(binary)) == str(binary)
    with pytest.raises(FileNotFoundError):muse.discover_muse(str(tmp_path / 'missing'))


def run_recovery(monkeypatch, snapshots, *, cancel_during_fetch=False):
    now = [0.]
    calls = []
    sequence = iter(snapshots)
    user_input = threading.Event()
    class Pty:
        def isalive(self): return True
        def read(self, *_): return ''
    class Stop:
        def is_set(self): return now[0] > 30
        def wait(self, seconds): now[0] += .5
    def fetch(path, **kwargs):
        calls.append(now[0])
        if cancel_during_fetch:user_input.set()
        item = next(sequence)
        if isinstance(item, Exception):raise item
        return item
    monkeypatch.setattr(muse, 'fetch_muse_quota', fetch)
    monkeypatch.setattr(wrapper.time, 'monotonic', lambda: now[0])
    result = wrapper.wait_for_muse_recovery(Pty(), Stop(), 'muse',
                                          wrapper.WrapperConfig(grace_seconds=3,poll_seconds=2),user_input)
    return result, calls


def test_waits_for_weekly_and_session_recovery_then_grace(monkeypatch):
    blocked = Quota('Muse test',RateWindow(100,300,1),RateWindow(100,10080,2),True)
    weekly = replace(blocked,primary=replace(blocked.primary,used_percent=0))
    available = replace(weekly,secondary=replace(weekly.secondary,used_percent=0),rate_limit_reached=False)
    result, calls = run_recovery(monkeypatch,[blocked,weekly,available,available,available])
    assert result is True and calls == [0,2,4,6,7]


def test_error_during_grace_requires_a_new_fresh_grace(monkeypatch):
    available = muse.parse_usage(usage())
    result, calls = run_recovery(monkeypatch,[available,RuntimeError('offline'),available,available,available])
    assert result is True and calls == [0,2,4,6,7]


def test_manual_input_during_quota_read_does_not_send(monkeypatch):
    result, calls = run_recovery(monkeypatch,[muse.parse_usage(usage())],cancel_during_fetch=True)
    assert result is None and calls == [0]


def test_cached_available_observation_before_limit_is_not_recovery():
    with pytest.raises(RuntimeError, match='predates this usage limit'):
        muse.parse_usage(usage(950), now=1000, not_before=990)
    assert not quota_blocked(muse.parse_usage(usage(1000), now=1000, not_before=990))


def test_cli_settings_keep_provider_paths_and_arguments_independent(monkeypatch):
    config.AppConfig(codex_path='/codex',claude_path='/claude',muse_path='/muse',
                     codex_args=['codex-only'],claude_args=['claude-only'],muse_args=['resume','--last']).save()
    captured=[]
    monkeypatch.setattr(cli,'run_wrapper',lambda cfg:captured.append(cfg) or 0)
    assert cli.main(['run','--provider','muse']) == 0
    cfg=captured[0]
    assert cfg.muse_path=='/muse' and cfg.muse_args==['resume','--last']
    assert wrapper._continue_prompt(cfg,True)=='Continue'
    assert cli.main(['run','--provider','muse','--muse','/other','--','--version'])==0
    assert captured[1].muse_path=='/other' and captured[1].muse_args==['--version']


def test_muse_default_never_enters_unsupported_desktop_watch(monkeypatch):
    config.AppConfig(provider='muse',mode='desktop').save()
    calls=[]
    monkeypatch.setattr(cli,'run_wrapper',lambda cfg:calls.append(cfg.provider) or 0)
    assert cli.main([])==0 and calls==['muse']
    assert cli.main(['watch','--provider','muse'])==1


def test_configure_and_quota_use_muse_executable(monkeypatch):
    assert cli.main(['configure','--provider','muse','--muse','/custom/muse'])==0
    stored=config.AppConfig.load()
    assert stored.provider=='muse' and stored.mode=='cli' and stored.muse_path=='/custom/muse'
    calls=[]
    monkeypatch.setattr(muse,'fetch_muse_quota',lambda path:calls.append(path) or muse.parse_usage(usage()))
    assert cli.main(['quota'])==0 and calls==['/custom/muse']
    with pytest.raises(SystemExit):cli.main(['configure','--provider','muse','--mode','desktop'])


def test_unsupported_browser_targets_do_not_become_codex_targets(monkeypatch):
    monkeypatch.setattr(targets,'discover_windows',lambda *_:pytest.fail('Guessed app identity'))
    inventory=targets.discover_targets('muse')
    assert not inventory.targets and 'app/browser' in inventory.warnings[0]
    assert watch.run_desktop_watch(watch.WatchConfig(provider='muse'))==1
    a=Target('thread','codex-chat','Codex',send_prompt=True,send_goal=False)
    b=replace(a,id='claude',provider='claude',kind='window')
    c=replace(a,id='muse',provider='muse')
    settings=config.AppConfig(provider='muse',desktop_targets=[t.to_dict() for t in (a,b,c)])
    settings.save();stored=config.AppConfig.load()
    assert stored.targets()==[] and len(stored.all_targets())==3
    stored.provider='codex';assert stored.targets()[0].id=='codex-chat'
    stored.provider='claude';assert stored.targets()[0].id=='claude'


def test_tray_starts_muse_with_its_arguments_and_no_codex_goal(monkeypatch):
    monkeypatch.setenv('PYSTRAY_BACKEND','dummy')
    from recharge_ai_task import tray
    config.AppConfig(provider='muse',muse_path='/muse',muse_args=['resume','--last']).save()
    calls=[]
    class Process:
        def poll(self):return None
    monkeypatch.setattr(tray,'_resolve_cli_exe',lambda:['recharge-ai-task-cli'])
    monkeypatch.setattr(tray,'_console_command',lambda args:args)
    monkeypatch.setattr(tray.subprocess,'Popen',lambda args,**kw:calls.append(args) or Process())
    app=tray.TrayApp();monkeypatch.setattr(app,'_watch_process',lambda:None)
    app.start_goal()
    assert calls==[['recharge-ai-task-cli','run','--provider','muse','--no-goal','--muse','/muse','--','resume','--last']]


@pytest.mark.skipif(sys.platform=='win32',reason='POSIX PTY fixture')
def test_actual_muse_pty_continues_only_after_both_allowances_recover(tmp_path):
    binary=tmp_path/'muse'
    receipt=tmp_path/'receipt.txt';calls=tmp_path/'calls.txt'
    program=f'''#!{sys.executable}
import sys,json,time
from pathlib import Path
calls=Path({str(calls)!r})
if sys.argv[1:]==['usage','--json']:
 n=int(calls.read_text()) if calls.exists() else 0
 calls.write_text(str(n+1))
 now=time.time()
 print(json.dumps({{'schemaVersion':1,'allowance':{{'tier':'test','source':'mint','asOfMs':int(now*1000),'window':{{'usedPercent':100 if n==0 else 0,'resetsAtMs':int((now+3600)*1000)}},'weekly':{{'usedPercent':100 if n<2 else 0,'resetsAtMs':int((now+86400)*1000)}}}}}}))
else:
 print('Usage limit reached',flush=True)
 message=input()
 Path({str(receipt)!r}).write_text(message)
 raise SystemExit(0 if message=='Continue' else 2)
'''
    binary.write_text(program);binary.chmod(0o755)
    config.AppConfig(poll_seconds=1).save()
    result=subprocess.run([sys.executable,'-m','recharge_ai_task.cli','run','--provider','muse',
                           '--muse',str(binary),'--goal','--grace','1'],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert receipt.read_text()=='Continue' and int(calls.read_text())>=4
    assert '/goal resume' not in result.stdout+result.stderr
