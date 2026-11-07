from dataclasses import replace
from recharge_ai_task.activity import ActivityLog, display_event
from recharge_ai_task.config import AppConfig
from recharge_ai_task.targets import Target
from recharge_ai_task import target_delivery as delivery
from recharge_ai_task.codex_ipc import DeliveryUncertain

T = Target('thread','private-id','Chat title', send_prompt=True, send_goal=False, custom_prompt='Custom\nmessage')


def test_history_records_actual_message_attempt_and_acceptance(monkeypatch):
    monkeypatch.setattr(delivery,'_send_thread',lambda *_:None)
    result = delivery.send_signals([T],'Default',manual=True)[0]
    events = ActivityLog().read()
    assert result.completed_actions == ('prompt',)
    assert [(e['action'],e['status']) for e in events] == [('prompt','attempting'),('prompt','accepted'),('signals','verified')]
    assert all(e['source']=='manual' for e in events)
    assert events[0]['message']=='Custom\nmessage'
    assert 'Custom\nmessage' in display_event(events[1])[0]
    assert not ActivityLog().read(events[-1]['id'])


def test_failed_uncertain_and_limited_actions_are_distinct(monkeypatch):
    AppConfig(prompt_limit=1).save()
    def fail(*_):raise RuntimeError('Rejected')
    monkeypatch.setattr(delivery,'_send_thread',fail)
    assert not delivery.send_signals([T],'Default')[0].success
    assert any(e['status']=='failed' and e['action']=='prompt' for e in ActivityLog().read())
    def uncertain(*_):raise DeliveryUncertain('Acceptance unknown')
    monkeypatch.setattr(delivery,'_send_thread',uncertain)
    assert not delivery.send_signals([T],'Default')[0].retryable
    assert any(e['status']=='uncertain' and e['action']=='prompt' for e in ActivityLog().read())
    assert delivery.send_signals([T],'Default')[0].skipped
    assert ActivityLog().read()[-2]['status']=='skipped'
    assert 'limit' in ActivityLog().read()[-2]['detail']


def test_both_actions_record_goal_before_actual_prompt(monkeypatch):
    def recover(target,text,**kwargs):
        kwargs['actions'].perform('goal',lambda:None)
        kwargs['actions'].confirm_goal()
        kwargs['actions'].perform('prompt',lambda:None)
        return delivery.DeliveryResult(target,True,'Native goal activation verified; continuation accepted')
    monkeypatch.setattr(delivery,'recover_target',recover)
    delivery.send_signals([replace(T,send_goal=True)],'Default')
    events=ActivityLog().read()
    assert [(e['action'],e['status']) for e in events] == [
        ('goal','attempting'),('goal','accepted'),('goal','verified'),('prompt','attempting'),('prompt','accepted'),('signals','verified')]


def test_old_history_schema_is_migrated_without_losing_records():
    import sqlite3
    from recharge_ai_task.config import config_dir
    path=config_dir()/'delivery.sqlite'
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE activity(id INTEGER PRIMARY KEY AUTOINCREMENT,created REAL,title TEXT,source TEXT,action TEXT,status TEXT,detail TEXT,message TEXT)")
        db.execute("INSERT INTO activity(created,title,source,action,status,detail,message) VALUES (1,'Old chat','automatic','goal','failed','Old failure','')")
    history=ActivityLog()
    history.record(replace(T,project_name='Obsbot Camera Control'),'automatic','goal','failed','No Goal action sent')
    rows=history.read()
    assert len(rows)==2 and rows[0]['detail']=='Old failure'
    assert 'Project: not available' in display_event(rows[0])[0]
    assert 'Project: Obsbot Camera Control' in display_event(rows[1])[0]
    assert ActivityLog().read()==rows


def test_provider_attribution_survives_restart_and_equal_chat_titles():
    history=ActivityLog()
    for provider in ('codex','claude','muse'):
        target=replace(T,provider=provider)
        history.record(target,'manual','prompt','failed','Fixture failure')
    rows=ActivityLog().read()
    assert [row['provider'] for row in rows]==['codex','claude','muse']
    for row,caption in zip(rows,('Codex','Claude','Muse')):
        assert display_event(row)[0].startswith('['+caption+'] Manual')


def test_old_history_keeps_unknown_provider_instead_of_guessing_codex():
    import sqlite3
    from recharge_ai_task.config import config_dir
    with sqlite3.connect(config_dir()/'delivery.sqlite') as db:
        db.execute("CREATE TABLE activity(id INTEGER PRIMARY KEY,created REAL,title TEXT,source TEXT,action TEXT,status TEXT,detail TEXT,message TEXT,project_name TEXT)")
        db.execute("INSERT INTO activity VALUES (1,1,'Shared','automatic','prompt','failed','Old failure','','Project')")
    row=ActivityLog().read()[0]
    assert row['provider']=='' and display_event(row)[0].startswith('[Provider unknown]')
    assert row['detail']=='Old failure'
