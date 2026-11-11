"""Google terminal providers must remain isolated and respect native retry ownership."""
from pathlib import Path
import subprocess
import sys
import time

import pytest
from recharge_ai_task import cli, google_ai, providers, targets, watch, wrapper
from recharge_ai_task.config import AppConfig, PROVIDERS


@pytest.mark.parametrize('provider,name', [('gemini','gemini'),('antigravity','agy')])
def test_google_discovery_and_settings(tmp_path, monkeypatch, provider, name):
    executable=tmp_path/name
    executable.touch()
    monkeypatch.setenv(provider.upper()+'_CLI_PATH',str(executable))
    assert google_ai.discover_google_cli(provider)==str(executable)
    with pytest.raises(FileNotFoundError):
        google_ai.discover_google_cli(provider,str(tmp_path/'missing'))
    assert cli.main(['configure','--provider',provider,'--'+provider,str(executable)])==0
    stored=AppConfig.load()
    assert stored.provider==provider and getattr(stored,provider+'_path')==str(executable)
    setattr(stored,provider+'_args',['--model','chosen']);stored.codex_args=['codex-only'];stored.save()
    captured=[]
    monkeypatch.setattr(cli,'run_wrapper',lambda config:captured.append(config) or 0)
    assert cli.main(['run'])==0
    assert getattr(captured[0],provider+'_args')==['--model','chosen']
    assert cli.main(['run','--provider',provider,'--','--model','other'])==0
    assert getattr(captured[1],provider+'_args')==['--model','other']
    assert wrapper._continue_prompt(captured[1],True)=='Continue'
    assert PROVIDERS[-1]=='opencode'


@pytest.mark.parametrize('provider', ['gemini','antigravity'])
def test_google_never_falls_back_to_codex_or_fake_desktop_targets(monkeypatch,capsys,provider):
    monkeypatch.setattr(cli,'discover_codex',lambda *_:pytest.fail('Codex fallback'))
    monkeypatch.setattr(targets,'discover_windows',lambda *_:pytest.fail('Desktop identity guessed'))
    assert cli.main(['quota','--provider',provider])==1
    assert 'wrapped interactive terminal' in capsys.readouterr().err
    inventory=targets.discover_targets(provider)
    assert not inventory.targets and 'Shared dashboard quota' in inventory.warnings[0]
    assert watch.run_desktop_watch(watch.WatchConfig(provider=provider))==1
    assert 'wrapped interactive terminal' in capsys.readouterr().err


@pytest.mark.parametrize('banner',[
    'Individual quota reached. Resets in 139h4m36s.',
    'Usage limit reached for gemini-pro. Your quota will reset after 2h 30m.',
    'You have exhausted your capacity on this model. Please retry in 34.5 seconds.',
    'Quota exceeded. Try again in 1 minute.',
])
def test_google_explicit_reset_duration_and_stable_deadline(banner):
    watcher=google_ai.GoogleLimitWatcher()
    before=time.time()
    result=watcher.feed('\x1b[31m'+banner+'\x1b[0m\n')
    assert result and result[0]>before
    assert watcher.feed('ordinary terminal redraw\n')==result


def test_google_split_chunks_and_decimal_duration():
    watcher=google_ai.GoogleLimitWatcher()
    assert watcher.feed('You have exhausted your capacity. Please retry in ') is None
    result=watcher.feed('1.5 seconds\n')
    assert 1.3<result[0]-time.time()<=1.5
    watcher.reset()
    assert watcher.feed('Individual quota reached. Resets in 1h')
    assert watcher.feed('20m30s.\n')[0]-time.time()>4800


@pytest.mark.parametrize('banner',[
    'API error 429: resource exhausted',
    'Quota available. Resets in 5 seconds.',
    'Usage limit reached. Try again at someday.',
    'Network request failed. Retry in 1 second.',
    'Quota exceeded. Retry in 0 seconds.',
    'Usage limit reached. Resets in an hour.',
])
def test_ambiguous_errors_never_schedule_google_continuation(banner):
    assert google_ai.GoogleLimitWatcher().feed(banner) is None


@pytest.mark.parametrize('native', ['Retrying in 1s attempt #1','Switch to gemini-flash','Keep trying','Press Enter to retry'])
def test_google_native_retries_fallback_and_choice_dialogs_take_precedence(native):
    watcher=google_ai.GoogleLimitWatcher()
    assert watcher.feed('Usage limit reached. Resets in 1s.\n'+native) is None
    assert watcher.native_retry
    assert watcher.feed('\nA later explicit usage limit reached. Resets in 2s.\n')
    assert not watcher.native_retry


@pytest.mark.parametrize('provider', ['gemini','antigravity'])
@pytest.mark.parametrize('args', [['-p','task'],['--prompt=task'],['--print','task'],['--output-format','json'],['--acp'],['--remote-agent']])
def test_google_headless_and_remote_modes_are_rejected(provider,args):
    with pytest.raises(ValueError,match='local interactive terminal'):
        google_ai.validate_interactive_args(provider,args)
    google_ai.validate_interactive_args(provider,['--model','chosen','-i','interactive task'])


@pytest.mark.skipif(sys.platform=='win32',reason='POSIX PTY fixture')
@pytest.mark.parametrize('provider', ['gemini','antigravity'])
@pytest.mark.parametrize('native', [False,True])
def test_google_real_pty_continuation_and_native_retry(tmp_path,provider,native):
    executable=tmp_path/google_ai.CLI_NAMES[provider]
    receipt=tmp_path/'receipt'
    executable.write_text(f'''#!{sys.executable}
import select,sys
from pathlib import Path
print('Individual quota reached. Resets in 1s.',flush=True)
if {native!r}:
 print('Retrying in 1s attempt #1',flush=True)
 ready,_,_=select.select([sys.stdin],[],[],2)
 Path({str(receipt)!r}).write_text('unexpected' if ready else 'native retry only')
else:
 Path({str(receipt)!r}).write_text(input())
''')
    executable.chmod(0o755)
    result=subprocess.run([sys.executable,'-m','recharge_ai_task.cli','run','--provider',provider,'--'+provider,str(executable),'--goal','--grace','0'],capture_output=True,text=True,timeout=8)
    assert result.returncode==0,result.stderr
    assert receipt.read_text()==('native retry only' if native else 'Continue')
    assert '/goal resume' not in result.stdout+result.stderr


@pytest.mark.parametrize('provider', ['gemini','antigravity'])
def test_google_tray_uses_own_executable_arguments_and_no_codex_goal(monkeypatch,provider):
    monkeypatch.setenv('PYSTRAY_BACKEND','dummy')
    from recharge_ai_task import tray
    config=AppConfig(provider=provider)
    setattr(config,provider+'_path','/custom/'+provider)
    setattr(config,provider+'_args',['--model','chosen']);config.save()
    calls=[]
    class Process:
        def poll(self): return None
    monkeypatch.setattr(tray,'_resolve_cli_exe',lambda:['recharge-ai-task'])
    monkeypatch.setattr(tray,'_console_command',lambda args:args)
    monkeypatch.setattr(tray.subprocess,'Popen',lambda args,**kw:calls.append(args) or Process())
    app=tray.TrayApp()
    monkeypatch.setattr(app,'_watch_process',lambda:None)
    app.start_goal()
    assert calls==[['recharge-ai-task','run','--provider',provider,'--no-goal','--'+provider,'/custom/'+provider,'--','--model','chosen']]


def test_google_pending_continuation_cancelled_by_manual_input():
    import threading
    entered=threading.Event();entered.set()
    class Pty:
        def isalive(self): return True
        def read(self,_): pytest.fail('Manual input must cancel before another read')
    assert wrapper.wait_for_opencode_reset(Pty(),wrapper.StopEvent(),sys.maxsize,
                                           google_ai.GoogleLimitWatcher(),0,entered) is None
