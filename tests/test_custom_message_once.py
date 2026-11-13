"""A custom message is reserved once across processes, failures and resets."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from recharge_ai_task import target_delivery as delivery
from recharge_ai_task.config import AppConfig
from recharge_ai_task.codex_ipc import DeliveryUncertain
from recharge_ai_task.delivery_policy import UsageLedger, effective_message
from recharge_ai_task.targets import Target

T = Target('thread','once','Once',instance='/profile',endpoint='/profile/ipc/ipc.sock',
           send_prompt=True,send_goal=False,custom_prompt='Custom once',custom_prompt_once='token-one')


def setup(monkeypatch, target=T):
    AppConfig(continue_prompt='Default',desktop_targets=[target.to_dict()]).save()
    UsageLedger()
    sent=[]
    monkeypatch.setattr(delivery,'_send_thread',lambda target,text:sent.append(text))
    return sent


def test_accepted_custom_reverts_to_default_even_for_stale_worker_and_restart(monkeypatch):
    sent=setup(monkeypatch)
    assert delivery.send_signals([T],'Default')[0].success
    assert AppConfig.load().targets()[0].custom_prompt is None
    assert AppConfig.load().targets()[0].custom_prompt_once==''
    assert delivery.send_signals([T],'Default',manual=True)[0].success
    assert sent==['Custom once','Default']
    assert effective_message(T,'Default')=='Default'


def test_definite_failure_keeps_custom_for_retry(monkeypatch):
    sent=setup(monkeypatch)
    monkeypatch.setattr(delivery,'_send_thread',lambda *a:(_ for _ in ()).throw(RuntimeError('Rejected')))
    assert not delivery.send_signals([T],'Default')[0].success
    assert AppConfig.load().targets()[0].custom_prompt=='Custom once'
    monkeypatch.setattr(delivery,'_send_thread',lambda t,text:sent.append(text))
    assert delivery.send_signals([T],'Default')[0].success
    assert sent==['Custom once']


def test_limit_skip_does_not_consume_custom(monkeypatch):
    setup(monkeypatch)
    target=replace(T,prompt_limit=0)
    assert delivery.send_signals([target],'Default')[0].skipped
    assert UsageLedger().once_state(T.key,T.custom_prompt_once) is None
    assert effective_message(T,'Default')=='Custom once'


def test_unconfirmed_send_is_not_replayed_as_custom(monkeypatch):
    sent=setup(monkeypatch)
    def uncertain(t,text):
        sent.append(text)
        raise DeliveryUncertain('Lost acknowledgement')
    monkeypatch.setattr(delivery,'_send_thread',uncertain)
    result=delivery.send_signals([T],'Default')[0]
    assert not result.success and result.uncertain
    assert AppConfig.load().targets()[0].custom_prompt is None
    monkeypatch.setattr(delivery,'_send_thread',lambda t,text:sent.append(text))
    assert delivery.send_signals([T],'Default')[0].success
    assert sent==['Custom once','Default']


def test_concurrent_senders_claim_custom_atomically(monkeypatch):
    sent=setup(monkeypatch)
    from recharge_ai_task.activity import ActivityLog
    ActivityLog()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:delivery.send_signals([T],'Default')[0],range(2)))
    assert all(r.success for r in results)
    assert sorted(sent)==['Custom once','Default']


def test_newer_draft_is_not_erased_when_previous_send_completes(monkeypatch):
    sent=setup(monkeypatch)
    newer=replace(T,custom_prompt='New draft',custom_prompt_once='token-two')
    def send(t,text):
        sent.append(text)
        AppConfig(continue_prompt='Default',desktop_targets=[newer.to_dict()]).save()
    monkeypatch.setattr(delivery,'_send_thread',send)
    assert delivery.send_signals([T],'Default')[0].success
    assert AppConfig.load().targets()[0]==newer
    assert sent==['Custom once']


def test_count_reset_does_not_rearm_custom_or_reuse_attempt_identity(monkeypatch):
    sent=setup(monkeypatch)
    assert delivery.send_signals([T],'Default')[0].success
    UsageLedger().reset([T.key])
    monkeypatch.setattr(delivery,'_send_thread',lambda *a:(_ for _ in ()).throw(RuntimeError('Rejected default')))
    assert not delivery.send_signals([T],'Default')[0].success
    assert UsageLedger().once_state(T.key,T.custom_prompt_once)=='sent'
    assert effective_message(T,'Default')=='Default'


def test_abandoned_pending_claim_remains_consumed_after_reset(monkeypatch):
    setup(monkeypatch)
    ledger=UsageLedger()
    ledger.reserve_prompt(T,None,'Custom once','Default')
    with ledger.connection() as db:
        db.execute('UPDATE attempts SET owner_pid=NULL')
        db.execute('UPDATE custom_once SET owner_pid=NULL')
    assert AppConfig.load().targets()[0].custom_prompt is None
    ledger.reset([T.key])
    assert ledger.once_state(T.key,T.custom_prompt_once)=='uncertain'
    assert effective_message(T,'Default')=='Default'


def test_skipped_goal_fallback_uses_the_reserved_message(monkeypatch):
    target=replace(T,send_goal=True)
    sent=setup(monkeypatch,target)
    monkeypatch.setattr(delivery,'recover_target',lambda target,*a,**kw:delivery.DeliveryResult(target,True,'No goal',skipped=True))
    assert delivery.send_signals([target],'Default')[0].success
    assert delivery.send_signals([target],'Default')[0].success
    assert sent==['Custom once','Default']


def test_empty_default_is_not_sent_after_custom_was_used(monkeypatch):
    sent=setup(monkeypatch)
    assert delivery.send_signals([T],'Default')[0].success
    assert not delivery.send_signals([T],'')[0].success
    assert sent==['Custom once']


def test_rearming_same_text_uses_a_new_token(monkeypatch):
    sent=setup(monkeypatch)
    assert delivery.send_signals([T],'Default')[0].success
    newer=replace(T,custom_prompt_once='new-token')
    assert delivery.send_signals([newer],'Default')[0].success
    assert sent==['Custom once','Custom once']


def test_independent_processes_reserve_custom_once(monkeypatch,tmp_path):
    import json,os,subprocess,sys
    setup(monkeypatch)
    from recharge_ai_task.activity import ActivityLog
    ActivityLog()
    path=tmp_path/'messages.jsonl'
    source=r'''
import json,os,sys
from recharge_ai_task import target_delivery as delivery
from recharge_ai_task.targets import Target
target=Target.from_dict(json.loads(sys.argv[1]))
def send(target,text):
    fd=os.open(sys.argv[2],os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:os.write(fd,(json.dumps(text)+'\n').encode())
    finally:os.close(fd)
delivery._send_thread=send
sys.stdin.readline()
result=delivery.send_signals([target],'Default')[0]
print(json.dumps({'success':result.success,'detail':result.detail}),flush=True)
'''
    processes=[subprocess.Popen([sys.executable,'-c',source,json.dumps(T.to_dict()),str(path)],
                               stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    try:
        for process in processes:process.stdin.write('go\n');process.stdin.flush()
        for process in processes:
            process.stdin.close();process.stdin=None
            out,err=process.communicate(timeout=10)
            assert process.returncode==0,err
            assert json.loads(out)['success'],out
        assert sorted(json.loads(line) for line in path.read_text().splitlines())==['Custom once','Default']
    finally:
        for process in processes:
            if process.poll() is None:process.kill();process.wait()


def test_goal_failure_still_sends_and_consumes_custom(monkeypatch):
    target=replace(T,send_goal=True)
    sent=setup(monkeypatch,target)
    monkeypatch.setattr(delivery,'recover_target',lambda target,*a,**kw:delivery.DeliveryResult(target,False,'Goal failed'))
    assert not delivery.send_signals([target],'Default')[0].success
    assert sent==['Custom once']
    assert UsageLedger().once_state(T.key,T.custom_prompt_once)=='sent'
    assert effective_message(target,'Default')=='Default'


def test_accepted_message_stays_consumed_if_final_goal_check_fails(monkeypatch):
    target=replace(T,send_goal=True)
    setup(monkeypatch,target)
    sent=[]
    def recover(target,text,**kw):
        budget=kw['actions']
        budget.perform('prompt',lambda:sent.append(budget.message))
        return delivery.DeliveryResult(target,False,'Final Goal verification failed',retryable=False,uncertain=True)
    monkeypatch.setattr(delivery,'recover_target',recover)
    assert not delivery.send_signals([target],'Default')[0].success
    assert sent==['Custom once'] and AppConfig.load().targets()[0].custom_prompt is None
