from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import pytest

from recharge_ai_task import target_delivery as delivery
from recharge_ai_task.config import AppConfig
from recharge_ai_task.targets import Target
from recharge_ai_task.delivery_policy import ActionBudget, LimitReached, UsageLedger, Usage, effective_limit
from recharge_ai_task.codex_ipc import DeliveryUncertain

T = Target('thread','one','Same',instance='profile',send_prompt=True,send_goal=False)


def test_defaults_and_per_recipient_overrides():
    config = AppConfig(prompt_limit=2,goal_limit=3)
    assert effective_limit(T,'prompt',config)==2
    assert effective_limit(replace(T,prompt_limit=0),'prompt',config)==0
    assert effective_limit(replace(T,prompt_limit=-1),'prompt',config) is None
    assert effective_limit(replace(T,prompt_limit=5),'prompt',config)==5
    with pytest.raises(ValueError):effective_limit(replace(T,prompt_limit=-2),'prompt',config)


def test_custom_message_limits_restart_and_independent_recipients(monkeypatch):
    AppConfig(prompt_limit=1).save()
    sent=[]
    monkeypatch.setattr(delivery,'_send_thread',lambda target,text:sent.append((target.id,text)))
    custom=replace(T,custom_prompt='Custom\nmessage')
    assert delivery.send_signals([custom],'Default',manual=True)[0].success
    assert delivery.send_signals([custom],'Default')[0].skipped
    other=replace(T,id='two')
    assert delivery.send_signals([other],'Default')[0].success
    assert sent==[('one','Custom\nmessage'),('two','Default')]
    assert UsageLedger().snapshot()[(T.key,'prompt')].used==1
    UsageLedger().reset([T.key])
    assert delivery.send_signals([custom],'Default')[0].success


def test_failure_releases_slot_but_uncertain_delivery_keeps_it(monkeypatch):
    AppConfig(prompt_limit=1).save()
    def fail(*args):raise RuntimeError('Rejected')
    monkeypatch.setattr(delivery,'_send_thread',fail)
    assert not delivery.send_signals([T],'Continue')[0].success
    assert UsageLedger().snapshot().get((T.key,'prompt'),Usage()).used==0
    def uncertain(*args):raise DeliveryUncertain('Unknown acknowledgement')
    monkeypatch.setattr(delivery,'_send_thread',uncertain)
    result=delivery.send_signals([T],'Continue')[0]
    assert not result.success and not result.retryable
    assert UsageLedger().snapshot()[(T.key,'prompt')]==Usage(1,1)
    assert delivery.send_signals([T],'Continue')[0].skipped


def test_concurrent_senders_cannot_exceed_allowance():
    ledger=UsageLedger()
    def reserve(_):
        try:return ledger.reserve(T.key,'prompt',1)
        except LimitReached:return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes=list(pool.map(reserve,range(12)))
    assert sum(value is not None for value in outcomes)==1
    assert UsageLedger().snapshot()[(T.key,'prompt')]==Usage(1,1)
    with pytest.raises(ValueError,match='in progress'):ledger.reset([T.key])
    attempt=next(value for value in outcomes if value is not None)
    ledger.finish(attempt,'sent')
    ledger.reset([T.key])
    assert not ledger.snapshot()


def test_combined_goal_cap_withholds_message_and_prompt_cap_allows_goal(monkeypatch):
    AppConfig(goal_limit=0).save()
    target=replace(T,send_goal=True)
    monkeypatch.setattr(delivery,'recover_target',lambda *args,**kw:pytest.fail('Goal exceeded limit'))
    assert delivery.send_signals([target],'Continue',manual=True)[0].skipped
    AppConfig(prompt_limit=0,goal_limit=1).save()
    calls=[]
    def recover(target,text,**kwargs):
        calls.append(kwargs['send_prompt'])
        kwargs['actions'].perform('goal',lambda:None)
        return delivery.DeliveryResult(target,True,'Goal activated')
    monkeypatch.setattr(delivery,'recover_target',recover)
    result=delivery.send_signals([target],'Continue',manual=True)[0]
    assert result.success and calls==[False] and 'message limit reached' in result.detail
    assert UsageLedger().snapshot()[(target.key,'goal')].used==1


def test_goal_success_survives_prompt_failure_without_repeating_goal(monkeypatch):
    AppConfig(goal_limit=1,prompt_limit=1).save()
    def recover(target,text,**kwargs):
        kwargs['actions'].perform('goal',lambda:None)
        def fail():raise RuntimeError('Prompt rejected')
        try:kwargs['actions'].perform('prompt',fail)
        except RuntimeError:return delivery.DeliveryResult(target,False,'Prompt rejected')
    monkeypatch.setattr(delivery,'recover_target',recover)
    target=replace(T,send_goal=True)
    assert not delivery.send_signals([target],'Continue',manual=True)[0].success
    usage=UsageLedger().snapshot()
    assert usage[(target.key,'goal')].used==1 and (target.key,'prompt') not in usage
    assert delivery.send_signals([target],'Continue',manual=True)[0].skipped


def test_goal_no_op_is_not_counted(monkeypatch):
    monkeypatch.setattr(delivery,'recover_target',lambda target,*args,**kw:delivery.DeliveryResult(target,True,'Already active'))
    assert delivery.send_signals([replace(T,send_prompt=False,send_goal=True)],'')[0].success
    assert not UsageLedger().snapshot()


def test_confirmed_send_with_accounting_failure_never_retries(monkeypatch):
    ledger=UsageLedger()
    budget=ActionBudget(ledger,T,AppConfig(prompt_limit=1))
    monkeypatch.setattr(ledger,'finish',lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(DeliveryUncertain):budget.perform('prompt',lambda:None)
    assert ledger.snapshot()[(T.key,'prompt')]==Usage(1,1)


def test_interrupted_attempt_stays_used_until_deliberate_reset():
    ledger=UsageLedger()
    attempt=ledger.reserve(T.key,'goal',1)
    # Simulate a sender that exited before saving the acknowledgement.
    with ledger.connection() as db:
        db.execute('UPDATE attempts SET owner_pid=NULL WHERE id=?',(attempt,))
    assert UsageLedger().snapshot()[(T.key,'goal')]==Usage(1,1)
    with pytest.raises(LimitReached):ledger.reserve(T.key,'goal',1)
    ledger.reset([T.key])
    assert not ledger.snapshot()


def test_allowance_storage_failure_sends_nothing(monkeypatch):
    monkeypatch.setattr(delivery,'UsageLedger',lambda:(_ for _ in ()).throw(OSError('read-only')))
    monkeypatch.setattr(delivery,'_send_thread',lambda *args:pytest.fail('Bypassed allowance storage'))
    result=delivery.send_signals([T],'Continue',manual=True)[0]
    assert not result.success and not result.retryable and 'allowances' in result.detail


@pytest.mark.parametrize('manual,goal_status,task_status,expected',[
    (False,'Paused','Idle','Goal: paused → Message'),
    (True,'Paused','Idle','Verify/resume Goal → Message'),
    (False,'Active','Running','Goal: task running/waiting → Message'),
    (True,'Active','Running','Goal: already active → Message'),
    (False,'Complete','Idle','Goal: complete → Message'),
    (True,'Blocked','Idle','Goal: blocked → Message'),
])
def test_plan_explains_manual_and_automatic_status_rules(manual,goal_status,task_status,expected):
    from recharge_ai_task.delivery_policy import planned_actions
    target=replace(T,send_goal=True,goal_status=goal_status,task_status=task_status)
    assert planned_actions(target,AppConfig(),{},'Continue',manual=manual)==expected


def test_empty_custom_message_does_not_fall_back_to_default(monkeypatch):
    monkeypatch.setattr(delivery,'_send_thread',lambda *args:pytest.fail('Empty custom message was sent'))
    result=delivery.send_signals([replace(T,custom_prompt='')],'Default',manual=True)[0]
    assert not result.success and not UsageLedger().snapshot()


def test_uncertain_send_and_storage_failure_stay_non_retryable(monkeypatch):
    ledger=UsageLedger()
    budget=ActionBudget(ledger,T,AppConfig(prompt_limit=1))
    monkeypatch.setattr(ledger,'finish',lambda *args:(_ for _ in ()).throw(OSError('disk full')))
    def uncertain():raise DeliveryUncertain('Lost acknowledgement')
    with pytest.raises(DeliveryUncertain):budget.perform('prompt',uncertain)
    assert ledger.usage(T.key,'prompt')==Usage(1,1)


def test_empty_ineligible_message_does_not_block_goal_or_watch():
    from recharge_ai_task.delivery_policy import invalid_messages
    target=replace(T,send_goal=True)
    assert invalid_messages([target],'',AppConfig(prompt_limit=0))==[]
    assert invalid_messages([target],'',AppConfig(goal_limit=0))==[]
    assert invalid_messages([target],'',AppConfig())==[target]
    assert invalid_messages([replace(target,custom_prompt='Custom')],'',AppConfig())==[]
