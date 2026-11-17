"""Observed terminal recovery is scoped to live processes and never account quota."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
from recharge_ai_task.terminal_status import TerminalObservation, live_observations, observation_lines
from recharge_ai_task.config import config_dir


def test_independent_sessions_dead_process_and_pid_reuse():
    first=TerminalObservation('gemini');second=TerminalObservation('gemini');other=TerminalObservation('opencode')
    try:
        first.update('waiting',time.time()+61)
        second.update('continued')
        records=live_observations('gemini')
        assert len(records)==2 and len(live_observations('opencode'))==1
        lines='\n'.join(observation_lines(records,time.time()))
        assert 'not shared account quota' in lines and 'remaining' in lines and '1 continuations sent' in lines
        record=json.loads(first.path.read_text());record['process_started']-=100
        first.path.write_text(json.dumps(record))
        assert len(live_observations('gemini'))==1
        second.path.write_text('{broken')
        assert not live_observations('gemini')
    finally:
        for item in (first,second,other):item.close()
    assert not live_observations('opencode')


def test_symlink_record_is_ignored(tmp_path):
    item=TerminalObservation('opencode')
    data=item.path.read_bytes();item.close()
    target=tmp_path/'elsewhere';target.write_bytes(data)
    item.path.symlink_to(target)
    assert not live_observations('opencode')
    item.path.unlink()


@pytest.mark.parametrize('provider', ['gemini','antigravity','opencode'])
def test_actual_wrapper_publishes_wait_and_continuation_then_cleans_up(tmp_path,provider):
    binary=tmp_path/'provider.py'
    receipt=tmp_path/'receipt'
    binary.write_text(f'#!{sys.executable}\nimport time\nfrom pathlib import Path\nprint("Usage limit reached; try again in 2 seconds",flush=True)\nmessage=input()\nPath({str(receipt)!r}).write_text(message)\ntime.sleep(1)\n')
    binary.chmod(0o755)
    process=subprocess.Popen([sys.executable,'-m','recharge_ai_task.cli','run','--provider',provider,'--'+provider,sys.executable,'--grace','0','--',str(binary)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    seen=set()
    deadline=time.monotonic()+8
    try:
        while time.monotonic()<deadline and process.poll() is None:
            for record in live_observations(provider):seen.add(record['state'])
            time.sleep(.02)
        out,err=process.communicate(timeout=2)
        assert process.returncode==0,err
        assert {'waiting','continued'}<=seen,seen
        assert receipt.read_text()=='Continue'
        assert not live_observations(provider)
    finally:
        if process.poll() is None:process.kill();process.wait()


def test_unavailable_observation_store_does_not_interrupt_terminal(monkeypatch):
    from recharge_ai_task import terminal_status
    def unavailable(*args,**kwargs):raise PermissionError('read-only profile')
    item=TerminalObservation('opencode')
    monkeypatch.setattr(terminal_status.tempfile,'NamedTemporaryFile',unavailable)
    item.update('waiting',time.time()+30)
    item.close()
    monkeypatch.setattr(terminal_status.psutil,'Process',lambda *args: (_ for _ in ()).throw(terminal_status.psutil.AccessDenied()))
    item=TerminalObservation('gemini')
    assert item.path is None
    item.update('running');item.close()
