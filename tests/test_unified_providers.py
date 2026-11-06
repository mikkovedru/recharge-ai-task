"""Local metadata, exact-session acceptance and independent provider recovery."""
from dataclasses import replace
import json
from pathlib import Path
import sys
import threading
import time
import uuid

import pytest

from recharge_ai_task import providers, session_catalog as catalog, session_delivery as delivery
from recharge_ai_task import cli, watch, watch_state, claude, muse, quota, tray_control
from recharge_ai_task.config import AppConfig
from recharge_ai_task.targets import Target, Inventory
from recharge_ai_task.codex_ipc import DeliveryUncertain


def saved(tmp_path, provider, *, session_id=None):
    session_id = session_id or str(uuid.uuid4())
    project = tmp_path / 'project'; project.mkdir(exist_ok=True)
    root = tmp_path / provider
    if provider == 'claude':
        path = root / 'projects' / '-encoded-project' / (session_id + '.jsonl')
        records = [dict(type='user', sessionId=session_id, cwd=str(project),
                        timestamp='2026-11-07T10:00:00Z', message={'content':'Build a useful app'})]
    else:
        path = root / 'sessions' / '2026' / '11' / '07' / session_id / 'session.jsonl'
        base = dict(schema_version=1, stream={'kind':'session','id':session_id}, recorded_at=1794045600000000)
        records = [dict(base, payload_type='runtime.session.metadata',
                        payload={'kind':'metadata','record':{'workspace_root':str(project),'provider_id':'meta'}}),
                   dict(base, payload_type='runtime.session', payload={'event':{'kind':'started','prompt':'Build a useful app'}})]
    path.parent.mkdir(parents=True)
    path.write_text(''.join(json.dumps(record)+'\n' for record in records))
    return catalog.read_session(path, provider, root)


@pytest.mark.parametrize('provider', ['claude','muse'])
def test_real_log_shapes_metadata_identity_and_partial_last_record(tmp_path, monkeypatch, provider):
    target = saved(tmp_path, provider)
    assert target.title == 'Build a useful app'
    assert target.last_active_at > 0 and target.task_status == 'Saved'
    assert target.signal_actions(True) == (True, False)
    path = Path(target.endpoint)
    with path.open('a') as stream:stream.write('{partial')
    if provider == 'claude':monkeypatch.setenv('CLAUDE_CONFIG_DIR', target.instance)
    else:monkeypatch.setenv('XDG_DATA_HOME', str(Path(target.instance).parent))
    # The fixture root for Muse is <data>/muse, like the native CLI.
    if provider == 'muse':
        assert Path(target.instance).name == 'muse'
    inventory = catalog.discover_sessions(provider)
    assert [t.key for t in inventory.targets] == [target.key]
    assert catalog.validate_session(target).title == target.title


def test_metadata_refresh_uses_rename_and_never_includes_sidechains(tmp_path, monkeypatch):
    target = saved(tmp_path, 'claude'); path = Path(target.endpoint)
    with path.open('a') as stream:
        stream.write(json.dumps(dict(type='custom-title', sessionId=target.id,customTitle='Renamed chat'))+'\n')
        stream.write(json.dumps(dict(type='user',sessionId=target.id,isSidechain=True,cwd='/wrong',message={'content':'Subagent'}))+'\n')
    assert catalog.read_session(path,'claude',Path(target.instance)).title == 'Renamed chat'
    assert catalog.validate_session(target).cwd == target.cwd
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', target.instance)
    hidden=path.parent/'subagents';hidden.mkdir()
    (hidden/(str(uuid.uuid4())+'.jsonl')).write_text(path.read_text())
    assert len(catalog.discover_sessions('claude').targets)==1


def test_untrusted_symlinks_and_changed_project_are_not_continued(tmp_path, monkeypatch):
    target=saved(tmp_path,'claude');path=Path(target.endpoint)
    monkeypatch.setenv('CLAUDE_CONFIG_DIR',target.instance)
    link=path.with_name(str(uuid.uuid4())+'.jsonl');link.symlink_to(path)
    assert len(catalog.discover_sessions('claude').targets)==1
    with pytest.raises(ValueError):catalog.validate_session(replace(target,endpoint=str(link)))
    with pytest.raises(ValueError):catalog.validate_session(replace(target,cwd='/wrong'))


def test_large_tool_logs_do_not_require_scanning_whole_transcript(tmp_path):
    target=saved(tmp_path,'claude');path=Path(target.endpoint)
    with path.open('a') as stream:
        stream.write(json.dumps({'type':'tool','data':'x'*1_000_000})+'\n')
        stream.write(json.dumps({'type':'custom-title','customTitle':'Latest name'})+'\n')
    assert catalog.read_session(path,'claude',target.instance).title=='Latest name'


def test_installed_detection_includes_native_apps_and_local_data(tmp_path, monkeypatch):
    monkeypatch.setattr(providers,'codex_home',lambda:tmp_path/'codex')
    monkeypatch.setattr(claude,'claude_home',lambda:tmp_path/'claude')
    monkeypatch.setattr(catalog,'muse_home',lambda:tmp_path/'muse')
    (tmp_path/'muse').mkdir()
    def missing(*_):raise FileNotFoundError('not installed')
    monkeypatch.setattr(quota,'discover_codex',missing)
    monkeypatch.setattr(claude,'discover_claude',missing)
    monkeypatch.setattr(muse,'discover_muse',missing)
    monkeypatch.setattr(providers,'discover_windows',lambda p:[Target('window','42','Claude',provider=p)] if p=='claude' else [])
    assert providers.installed_providers()=={'claude':None,'muse':None}
    monkeypatch.setattr(muse,'discover_muse',lambda *_:'/native/muse')
    assert providers.installed_providers()['muse']=='/native/muse'


def test_discovery_aggregates_providers_and_isolates_one_failure(monkeypatch):
    monkeypatch.setattr(providers,'installed_providers',lambda:{p:p for p in ('codex','claude','muse')})
    def discover(provider):
        if provider=='claude':raise PermissionError('fixture inaccessible')
        t=Target('session','same','Same',provider=provider)
        return Inventory([t,t])
    monkeypatch.setattr(providers,'discover_targets',discover)
    inventory=providers.discover_all_targets()
    assert inventory.providers==('codex','claude','muse')
    assert {t.provider for t in inventory.targets}=={'codex','muse'}
    assert len(inventory.targets)==2 and 'Claude' in inventory.warnings[0]


def test_filter_and_terminal_default_do_not_change_recipients_or_watch_identity(tmp_path):
    targets=[saved(tmp_path,p) for p in ('claude','muse')]
    config=AppConfig(desktop_targets=[t.to_dict() for t in targets]);config.save()
    before=(watch_state.state_path(config),tray_control.watch_settings(config))
    config.provider='muse';config.chat_provider_filter='claude';config.save()
    loaded=AppConfig.load()
    assert {t.provider for t in loaded.targets()}=={'claude','muse'}
    assert before==(watch_state.state_path(loaded),tray_control.watch_settings(loaded))
    assert loaded.chat_provider_filter=='claude'


@pytest.mark.parametrize('provider', ['claude','muse'])
def test_resume_command_keeps_exact_identity_profile_and_default_permissions(tmp_path, monkeypatch, provider):
    target=saved(tmp_path,provider)
    module=claude if provider=='claude' else muse
    monkeypatch.setattr(module,'discover_'+provider,lambda _:'/native/'+provider)
    AppConfig(provider='codex',claude_args=['--dangerously-skip-permissions','--resume','wrong'],muse_args=['--yolo']).save()
    args,env=delivery.session_command(target,message='Continue')
    assert args[0]=='/native/'+provider and target.id in args and args[-1]=='Continue'
    assert not any(arg in args for arg in ('--yolo','--dangerously-skip-permissions','wrong'))
    assert env['CLAUDE_CONFIG_DIR' if provider=='claude' else 'XDG_DATA_HOME']==(target.instance if provider=='claude' else str(Path(target.instance).parent))
    opened,_=delivery.session_command(target)
    assert opened==(['/native/claude','--resume',target.id] if provider=='claude' else ['/native/muse','resume',target.id])


@pytest.mark.parametrize('provider', ['claude','muse'])
@pytest.mark.parametrize('response', ['accepted','wrong_id','initialization_only','failed'])
def test_delivery_requires_native_prompt_acceptance(tmp_path, monkeypatch, provider, response):
    target=saved(tmp_path,provider)
    native=tmp_path/'native.py'
    record=({'type':'result','session_id':target.id,'is_error':False} if provider=='claude' else
            {'stream':{'kind':'session','id':target.id},'payload_type':'turn.input.user','payload':{'prompt':'Continue'}})
    if response=='wrong_id':
        if provider=='claude':record['session_id']='wrong'
        else:record['stream']['id']='wrong'
    if response=='initialization_only':record={'type':'system','subtype':'init','session_id':target.id}
    native.write_text('import json,time\n'+('print('+repr(json.dumps(record))+',flush=True)\ntime.sleep(.5)\n' if response!='failed' else 'raise SystemExit(1)\n'))
    monkeypatch.setattr(delivery,'session_command',lambda *_args,**kw:([sys.executable,str(native)],{}))
    monkeypatch.setattr(delivery,'active_session',lambda _:False)
    if response=='accepted':assert 'accepted' in delivery.continue_session(target,'Continue',timeout=.1)
    elif response=='failed':
        with pytest.raises(RuntimeError,match='exited'):delivery.continue_session(target,'Continue',timeout=1)
    else:
        with pytest.raises(DeliveryUncertain):delivery.continue_session(target,'Continue',timeout=.1)


def test_claude_initialization_is_only_accepted_after_exact_transcript_turn(tmp_path,monkeypatch):
    target=saved(tmp_path,'claude');native=tmp_path/'native.py'
    native.write_text('import json\nwith open('+repr(target.endpoint)+',"a") as f:f.write(json.dumps('+repr({'type':'user','sessionId':target.id,'message':{'content':'Continue'}})+')+"\\n")\n')
    monkeypatch.setattr(delivery,'session_command',lambda *_args,**kw:([sys.executable,str(native)],{}))
    monkeypatch.setattr(delivery,'active_session',lambda _:False)
    assert 'accepted' in delivery.continue_session(target,'Continue')


def test_active_session_guard_and_cross_process_lock(tmp_path,monkeypatch):
    target=saved(tmp_path,'claude')
    monkeypatch.setattr(delivery,'active_session',lambda _:True)
    monkeypatch.setattr(delivery,'session_command',lambda *a,**k:pytest.fail('Launched active chat'))
    with pytest.raises(RuntimeError,match='live session'):delivery.continue_session(target,'Continue')
    directory=tmp_path/'locks';directory.mkdir()
    descriptor=delivery._claim_session(target,directory)
    try:
        with pytest.raises(RuntimeError,match='another worker'):delivery._claim_session(target,directory)
    finally:
        import os
        os.close(descriptor)


def test_cli_defaults_all_and_explicit_filter_preserves_other_recipients(monkeypatch,capsys):
    targets=[Target('session','same','Same',provider=p,send_prompt=True,send_goal=False) for p in ('claude','muse')]
    monkeypatch.setattr(providers,'discover_all_targets',lambda:Inventory(targets))
    from recharge_ai_task import targets as target_module
    monkeypatch.setattr(target_module,'discover_targets',lambda p:Inventory([t for t in targets if t.provider==p]))
    AppConfig(desktop_targets=[t.to_dict() for t in targets]).save()
    assert cli.main(['targets','--json'])==0
    assert len(json.loads(capsys.readouterr().out)['targets'])==2
    with pytest.raises(SystemExit):cli.main(['targets','--select','same'])
    assert cli.main(['targets','--select',targets[1].key])==0
    assert [t.provider for t in AppConfig.load().targets()]==['muse']
    assert cli.main(['targets','--provider','claude','--select','same'])==0
    assert {t.provider for t in AppConfig.load().targets()}=={'claude','muse'}
    assert AppConfig.load().provider=='codex'


def test_mixed_watch_runs_independent_cycles_and_restores_each_provider(monkeypatch,tmp_path):
    stop=watch.StopEvent();state=watch.WatchState();entered=[];lock=threading.Lock()
    original=watch.run_desktop_watch
    def child(config,event):
        with lock:entered.append(config.provider)
        assert {t.provider for t in config.desktop_targets}=={config.provider}
        config.state.delivered.add(config.provider+'-accepted')
        config.state.progress={'phase':'quota_unavailable' if config.provider=='claude' else 'monitoring',
            'quota_error':'login required' if config.provider=='claude' else '',
            'selected_recipients':1,'selected_messages':1,'next_check_at':time.time()+30}
        config.checkpoint(config.state)
        while not event.is_set():event.wait(.01)
        return 0
    def dispatch(config,event=None):
        return original(config,event) if config.provider=='all' else child(config,event)
    monkeypatch.setattr(watch,'run_desktop_watch',dispatch)
    selected=tuple(Target('session',p,p,provider=p) for p in ('codex','claude','muse'))
    path=tmp_path/'state.json'
    config=watch.WatchConfig(provider='all',desktop_targets=selected,state=state,checkpoint=lambda s:watch_state.save(path,s))
    thread=threading.Thread(target=lambda:dispatch(config,stop));thread.start()
    try:
        deadline=time.monotonic()+3
        while len(state.provider_states)<3 and time.monotonic()<deadline:time.sleep(.01)
        assert set(entered)=={'codex','claude','muse'}
        assert state.progress['selected_recipients']==3
        assert state.progress['providers']['claude']['quota_error']=='login required'
        restored=watch_state.load(path)
        assert set(restored.provider_states)==set(entered)
        for p in entered:assert watch_state.from_dict(restored.provider_states[p]).delivered=={p+'-accepted'}
        stop.wake()
    finally:
        stop.set();thread.join(3)
        assert not thread.is_alive()


def test_single_watch_uses_recipient_provider_not_default_terminal(monkeypatch):
    original=watch.run_desktop_watch;seen=[]
    def dispatch(config,event=None):
        if config.provider!='all':seen.append(config.provider);return 0
        return original(config,event)
    monkeypatch.setattr(watch,'run_desktop_watch',dispatch)
    dispatch(watch.WatchConfig(provider='all',desktop_targets=(Target('session','id','Muse',provider='muse'),)))
    assert seen==['muse']


def test_real_mixed_watch_recovers_codex_and_muse_while_claude_login_fails(monkeypatch):
    available=quota.Quota('test',quota.RateWindow(20,300,int(time.time()+100)),None,False)
    blocked=replace(available,primary=replace(available.primary,used_percent=100),rate_limit_reached=True)
    counters={'codex':0,'muse':0};sent=[];stop=watch.StopEvent();state=watch.WatchState()
    def fetch(provider):
        counters[provider]+=1
        return blocked if counters[provider]==1 else available
    monkeypatch.setattr(watch,'discover_codex',lambda _:'fixture')
    monkeypatch.setattr(watch,'fetch_quota',lambda _:fetch('codex'))
    monkeypatch.setattr(muse,'fetch_muse_quota',lambda _:fetch('muse'))
    monkeypatch.setattr(claude,'fetch_claude_quota',lambda:(_ for _ in ()).throw(RuntimeError('login missing')))
    from recharge_ai_task.target_delivery import DeliveryResult
    def send(targets,*args,**kwargs):
        sent.extend(t.provider for t in targets)
        if len(sent)==2:stop.set()
        return [DeliveryResult(t,True,'accepted',completed_actions=('prompt',)) for t in targets]
    monkeypatch.setattr(watch,'send_signals',send)
    targets=tuple(Target('session',p,p,provider=p,instance=str(catalog.muse_home()) if p=='muse' else '',send_prompt=True,send_goal=False) for p in ('codex','claude','muse'))
    AppConfig(desktop_targets=[t.to_dict() for t in targets]).save()
    timer=threading.Timer(5,stop.set);timer.start()
    try:
        assert watch.run_desktop_watch(watch.WatchConfig(provider='all',desktop_targets=targets,state=state,poll_seconds=1,grace_seconds=0),stop)==0
        assert sorted(sent)==['codex','muse']
        assert state.progress['providers']['claude']['quota_error']=='login missing'
        assert all(state.provider_states[p]['delivered'] for p in ('codex','muse'))
    finally:timer.cancel()


def test_nested_checkpoint_recovers_provider_identity_and_no_duplicate_send(tmp_path, monkeypatch):
    from recharge_ai_task import activity
    events=[]
    monkeypatch.setattr(activity,"record",lambda target,*args:events.append((target,args)))
    target=saved(tmp_path,'muse')
    child=watch.WatchState(in_flight=(target.key,target.title,target.project_name),pending=True)
    parent=watch.WatchState(provider_states={'muse':watch_state.to_dict(child)})
    path=tmp_path/'nested.json';watch_state.save(path,parent)
    restored=watch_state.from_dict(watch_state.load(path).provider_states['muse'])
    assert target.key in restored.delivered and restored.in_flight is None
    assert events[-1][0].key==target.key and events[-1][1][2]=='uncertain'


def test_unavailable_display_does_not_hide_installed_cli_data(tmp_path,monkeypatch):
    monkeypatch.setattr(providers,'codex_home',lambda:tmp_path/'codex')
    monkeypatch.setattr(claude,'claude_home',lambda:tmp_path/'claude')
    monkeypatch.setattr(catalog,'muse_home',lambda:tmp_path/'muse')
    (tmp_path/'muse').mkdir()
    def missing(*_):raise FileNotFoundError('missing')
    monkeypatch.setattr(quota,'discover_codex',missing)
    monkeypatch.setattr(claude,'discover_claude',missing)
    monkeypatch.setattr(muse,'discover_muse',missing)
    monkeypatch.setattr(providers,'discover_windows',lambda *_:(_ for _ in ()).throw(RuntimeError('No display')))
    assert providers.installed_providers()=={'muse':None}


def test_child_checkpoint_is_an_independent_snapshot():
    child=watch.WatchState(completed_actions={'chat':['prompt']},previous_windows={'weekly':[99,42]})
    snapshot=watch_state.to_dict(child)
    child.completed_actions['other']=['goal'];child.previous_windows['weekly'][0]=0
    assert snapshot['completed_actions']=={'chat':['prompt']}
    assert snapshot['previous_windows']=={'weekly':[99,42]}


def test_automatic_recovery_never_uses_another_profiles_quota(tmp_path,monkeypatch):
    target=saved(tmp_path,'muse')
    monkeypatch.setattr(catalog,'muse_home',lambda:tmp_path/'another-account'/'muse')
    monkeypatch.setattr(muse,'fetch_muse_quota',lambda _:quota.Quota('test',quota.RateWindow(20,300,int(time.time()+60)),None,False))
    monkeypatch.setattr(watch,'send_signals',lambda *a,**kw:pytest.fail('Sent against the wrong account quota'))
    class Stop(watch.StopEvent):
        def wait(self,seconds):self.set();return True
    state=watch.WatchState(pending=True,startup_checked=True)
    watch.run_desktop_watch(watch.WatchConfig(provider='muse',desktop_targets=(replace(target,send_prompt=True,send_goal=False),),state=state),Stop())
    assert target.key in state.delivered
    from recharge_ai_task.activity import ActivityLog
    assert 'quota was not checked' in ActivityLog().read()[-1]['detail']


@pytest.mark.parametrize('name,args,other_user,same_project,active',[
    ('claude',['claude','--resume','selected'],False,False,True),
    ('claude',['claude','--resume','another'],False,True,False),
    ('claude',['claude'],False,True,True),
    ('claude',['claude'],False,False,False),
    ('claude',['claude','--resume','selected'],True,True,False),
    ('claude',['claude','--version'],False,True,False),
    ('muse',['muse','resume','selected'],False,True,False),
])
def test_active_owner_detection_respects_provider_user_session_and_project(tmp_path,monkeypatch,name,args,other_user,same_project,active):
    from types import SimpleNamespace
    target=Target('session','selected','Selected',provider='claude',cwd=str(tmp_path/'project'))
    process=SimpleNamespace(info={'name':name},username=lambda:'other' if other_user else 'fixture-user',
        cmdline=lambda:args,cwd=lambda:target.cwd if same_project else str(tmp_path/'another-project'))
    monkeypatch.setattr(delivery.psutil,'Process',lambda:SimpleNamespace(username=lambda:'fixture-user'))
    monkeypatch.setattr(delivery.psutil,'process_iter',lambda *_:[process])
    assert delivery.active_session(target) is active
