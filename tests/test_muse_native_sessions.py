"""Optional no-network integration against the installed Muse Code echo provider."""
import os
from pathlib import Path
import subprocess
import time
import uuid

import pytest
from recharge_ai_task import session_catalog as catalog, session_delivery as delivery, muse

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_NATIVE_MUSE_TESTS')!='1',reason='Opt-in installed Muse Code echo integration')


def test_native_saved_session_is_discovered_and_resumed_with_same_id(tmp_path,monkeypatch):
    binary=muse.discover_muse()
    data=tmp_path/'data';project=tmp_path/'project';project.mkdir()
    for key,value in {'XDG_DATA_HOME':data,'XDG_CONFIG_HOME':tmp_path/'config','XDG_CACHE_HOME':tmp_path/'cache','MUSE_NO_AUTO_UPDATE':'1'}.items():monkeypatch.setenv(key,str(value))
    session_id=str(uuid.uuid4())
    flags=['--provider','echo','--disable-reminders','--no-foreign-personal-context']
    result=subprocess.run([binary,'exec',*flags,'--workspace',str(project),'--session-id',session_id,'--json','First fixture message'],cwd=project,text=True,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    inventory=catalog.discover_sessions('muse')
    assert len(inventory.targets)==1
    target=inventory.targets[0]
    assert target.id==session_id and target.cwd==str(project) and target.title=='First fixture message'
    original=delivery.session_command
    def command(target,**kwargs):
        args,env=original(target,**kwargs)
        return [*args[:2],*flags,*args[2:]],env
    monkeypatch.setattr(delivery,'session_command',command)
    assert 'accepted' in delivery.continue_session(target,'Second fixture message')
    deadline=time.monotonic()+15
    while target.key in delivery._jobs and time.monotonic()<deadline:time.sleep(.05)
    assert target.key not in delivery._jobs
    assert 'Second fixture message' in Path(target.endpoint).read_text()
    assert len(catalog.discover_sessions('muse').targets)==1  # No fork or second session.
