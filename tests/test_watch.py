"""Desktop quota-reset delivery state transitions, without real waits."""
from dataclasses import replace
import pytest

from recharge_ai_task.quota import Quota, RateWindow
from recharge_ai_task import watch
from recharge_ai_task.targets import Target
from recharge_ai_task.target_delivery import DeliveryResult

A = Target("thread", "a", "A")
B = Target("thread", "b", "B")
BLOCKED = Quota("test", RateWindow(100, 300, 100), None, True)
AVAILABLE = replace(BLOCKED, primary=RateWindow(0, 300, 200), rate_limit_reached=False)


def run_snapshots(monkeypatch, snapshots, *, selected=(A,), grace=0, outcomes=(), goal=False, recovery_calls=None, state=None):
    sequence = iter(snapshots)
    quota = [snapshots[-1]]
    now = [100.0]
    sent = []
    replies = iter(outcomes)
    waits = []
    class Stop:
        def is_set(self): return len(waits) >= len(snapshots)
        def wait(self, seconds):
            waits.append(seconds)
            now[0] += seconds
    def fetch(_):
        value = next(sequence, quota[0])
        if isinstance(value, Exception):
            raise value
        quota[0] = value
        return value
    def deliver(targets, text, **_):
        sent.append((targets[0].id, text, now[0]))
        success, retryable = next(replies, (True, True))
        return [DeliveryResult(targets[0], success, "result", retryable)]
    monkeypatch.setattr(watch, "discover_codex", lambda _: "codex")
    monkeypatch.setattr(watch, "fetch_quota", fetch)
    monkeypatch.setattr(watch, "deliver_targets", deliver)
    def recover(target, text, **kwargs):
        if recovery_calls is not None: recovery_calls.append(target.id)
        return deliver([target], text, **kwargs)[0]
    monkeypatch.setattr(watch, "recover_target", recover)
    monkeypatch.setattr(watch, "quota_stopped_targets", lambda _, **kwargs: (set(), []))
    monkeypatch.setattr(watch.time, "time", lambda: now[0])
    config = watch.WatchConfig(desktop_targets=selected, grace_seconds=grace, goal_mode=goal, state=state)
    assert watch.run_desktop_watch(config, Stop()) == 0
    return sent, waits


@pytest.mark.parametrize("snapshot,pending,wake_at,outcomes,phase", [
    (BLOCKED, False, 0, (), "waiting_quota"),
    (AVAILABLE, False, 0, (), "monitoring"),
    (RuntimeError("offline"), False, 0, (), "quota_unavailable"),
    (AVAILABLE, True, 110, (), "grace_period"),
    (AVAILABLE, True, 0, [(False, True)], "retry_pending"),
])
def test_overview_reports_actual_worker_wait(monkeypatch, snapshot, pending, wake_at, outcomes, phase):
    state = watch.WatchState(startup_checked=True, pending=pending, wake_at=wake_at)
    _, waits = run_snapshots(monkeypatch, [snapshot], outcomes=outcomes, state=state)
    assert {key: state.progress[key] for key in ("phase", "next_check_at", "checked_at")} == {"phase": phase, "next_check_at": 100 + waits[0],
                              "checked_at": None if isinstance(snapshot, Exception) else 100}


def test_desktop_watch_sends_after_confirmed_reset(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE], goal=True)
    assert [(target, text) for target, text, _ in sent] == [("a", "Continue")]


def test_no_signal_while_api_still_reports_exhaustion(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED] * 3)
    assert sent == []


def test_weekly_limit_must_also_reset(monkeypatch):
    both = replace(BLOCKED, secondary=RateWindow(100, 10080, 160))
    weekly = replace(AVAILABLE, secondary=both.secondary, rate_limit_reached=True)
    sent, waits = run_snapshots(monkeypatch, [both, weekly, AVAILABLE, AVAILABLE], grace=10)
    assert waits[0] == waits[1] == 5
    assert len(sent) == 1 and sent[0][2] == 120


def test_failed_target_retries_after_quota_becomes_available(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE, AVAILABLE],
        selected=(A, B), outcomes=[(True, True), (False, True), (True, True)], goal=True)
    assert [(target, text) for target, text, _ in sent] == [
        ("a", "Continue"), ("b", "Continue"), ("b", "Continue")]


def test_uncertain_target_is_not_repeated_after_reset(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE], outcomes=[(False, False)])
    assert len(sent) == 1


def test_quota_error_at_reset_does_not_send(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, RuntimeError("offline"), AVAILABLE])
    assert len(sent) == 1 and sent[0][2] >= 165


def test_new_reset_sends_once_again(monkeypatch):
    blocked_again = replace(BLOCKED, primary=RateWindow(100, 300, 200))
    available_again = replace(AVAILABLE, primary=RateWindow(0, 300, 300))
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE, blocked_again, available_again], goal=True)
    assert [(target, text) for target, text, _ in sent] == [("a", "Continue"), ("a", "Continue")]


def test_grace_period_is_retained_after_api_recovers(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED] + [AVAILABLE] * 8, grace=90)
    assert len(sent) == 1 and sent[0][2] == 195


def test_available_quota_without_observed_block_does_not_send(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [AVAILABLE, AVAILABLE])
    assert sent == []


def test_limit_flag_without_full_window_blocks_delivery(monkeypatch):
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, replace(AVAILABLE, rate_limit_reached=True), AVAILABLE])
    assert len(sent) == 1 and sent[0][2] == 120


def test_partial_stale_snapshot_does_not_rearm_completed_reset(monkeypatch):
    both = replace(BLOCKED, secondary=RateWindow(100, 10080, 160))
    weekly_stale = replace(AVAILABLE, secondary=both.secondary, rate_limit_reached=True)
    sent, _ = run_snapshots(monkeypatch, [both, AVAILABLE, weekly_stale, AVAILABLE, AVAILABLE])
    assert len(sent) == 1


def test_startup_recovers_only_quota_stopped_goals(monkeypatch):
    sent = []
    monkeypatch.setattr(watch, "discover_codex", lambda _: "codex")
    monkeypatch.setattr(watch, "fetch_quota", lambda _: AVAILABLE)
    monkeypatch.setattr(watch, "quota_stopped_targets", lambda _, **kwargs: ({B.key}, []))
    monkeypatch.setattr(watch, "recover_target", lambda target, text, **_: sent.append(target.id) or DeliveryResult(target, True, "Verified"))
    now, waits = [100.0], []
    class Stop:
        def is_set(self): return len(waits) >= 3
        def wait(self, seconds): waits.append(seconds); now[0] += seconds
    monkeypatch.setattr(watch.time, "time", lambda: now[0])
    watch.run_desktop_watch(watch.WatchConfig(desktop_targets=(A, B), goal_mode=True, grace_seconds=10), Stop())
    assert sent == ["b"] and waits[0] == 10


def test_each_reset_uses_native_recovery(monkeypatch):
    calls = []
    blocked_again = replace(BLOCKED, primary=RateWindow(100, 300, 200))
    available_again = replace(AVAILABLE, primary=RateWindow(0, 300, 300))
    sent, _ = run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE, blocked_again, available_again], goal=True, recovery_calls=calls)
    assert [text for _, text, _ in sent] == ["Continue", "Continue"]
    assert calls == ["a", "a"]


def test_cli_can_disable_native_recovery_and_describes_it(monkeypatch, capsys):
    from recharge_ai_task import cli
    from recharge_ai_task.config import AppConfig
    AppConfig(goal_mode=True).save()
    configs = []
    monkeypatch.setattr(cli, "run_desktop_watch", lambda config: configs.append(config) or 0)
    assert cli.main(["watch", "--no-goal"]) == 0
    assert not configs[-1].goal_mode
    assert cli.main(["watch", "--goal"]) == 0
    assert configs[-1].goal_mode
    with pytest.raises(SystemExit) as stopped:
        cli.main(["watch", "--help"])
    assert stopped.value.code == 0
    help_text = capsys.readouterr().out
    assert "native recovery" in help_text and "--no-goal" in help_text


def test_failed_startup_goal_check_retries_without_signalling_unknown_targets(monkeypatch):
    checks = [0]
    sent, waits = [], []
    def candidates(_, **kwargs):
        checks[0] += 1
        return (set(), ["Temporarily unavailable"]) if checks[0] == 1 else ({B.key}, [])
    monkeypatch.setattr(watch, "discover_codex", lambda _: "codex")
    monkeypatch.setattr(watch, "fetch_quota", lambda _: AVAILABLE)
    monkeypatch.setattr(watch, "quota_stopped_targets", candidates)
    monkeypatch.setattr(watch, "recover_target", lambda target, text, **_: sent.append(target.id) or DeliveryResult(target, True, "Verified"))
    class Stop:
        def is_set(self): return len(waits) >= 2
        def wait(self, seconds): waits.append(seconds)
    watch.run_desktop_watch(watch.WatchConfig(desktop_targets=(A, B), goal_mode=True, grace_seconds=0), Stop())
    assert checks == [2] and sent == ["b"]


@pytest.mark.parametrize("grace", [0, 10])
def test_early_reset_uses_observed_recovery_not_old_forecast(monkeypatch, grace):
    blocked = replace(BLOCKED, primary=RateWindow(100,300,10000))
    available = replace(blocked,primary=RateWindow(1,300,10000),rate_limit_reached=False)
    sent, waits = run_snapshots(monkeypatch,[blocked,available,available,available],grace=grace)
    assert len(sent)==1 and sent[0][2]==105+grace
    assert waits[0]==5


def test_added_credits_allow_recovery_with_full_included_window(monkeypatch):
    ready=replace(BLOCKED,primary=RateWindow(100,300,10000),rate_limit_reached=False,has_credits=True)
    sent,_=run_snapshots(monkeypatch,[replace(ready,has_credits=False,rate_limit_reached=True),ready,ready])
    assert len(sent)==1 and sent[0][2]==105


def test_flag_only_limit_arms_message_recovery(monkeypatch):
    blocked=replace(BLOCKED,primary=RateWindow(50,300,10000))
    ready=replace(blocked,rate_limit_reached=False)
    sent,_=run_snapshots(monkeypatch,[blocked,ready,ready])
    assert len(sent)==1


def test_second_exhaustion_after_refill_can_keep_the_reset_id(monkeypatch):
    blocked=replace(BLOCKED,primary=RateWindow(100,300,10000))
    ready=replace(blocked,primary=RateWindow(1,300,10000),rate_limit_reached=False)
    sent,_=run_snapshots(monkeypatch,[blocked,ready,ready,blocked,blocked,ready,ready])
    assert len(sent)==2


def test_reexhaustion_during_grace_restarts_grace_from_latest_recovery(monkeypatch):
    blocked=replace(BLOCKED,primary=RateWindow(100,300,10000))
    ready=replace(blocked,primary=RateWindow(1,300,10000),rate_limit_reached=False)
    state=watch.WatchState()
    sent,_=run_snapshots(monkeypatch,[blocked,ready,blocked,ready,ready],grace=10,state=state)
    assert len(sent)==1 and sent[0][2]==130
    assert state.recovered_at==120


def test_pending_action_counts_exclude_delivered_recipients(monkeypatch):
    a = replace(A, send_prompt=True, send_goal=False)
    b = replace(B, send_prompt=False, send_goal=True)
    c = replace(A, id="c", send_prompt=True, send_goal=True)
    state = watch.WatchState(startup_checked=True, pending=True, delivered={a.key})
    run_snapshots(monkeypatch, [RuntimeError("offline")], selected=(a,b,c), state=state)
    assert state.progress["pending_recipients"] == 2
    assert state.progress["pending_messages"] == 1
    assert state.progress["pending_goals"] == 2


def test_reset_between_polls_near_limit_sends_after_grace(monkeypatch):
    # A ten-second poll can miss 100% before the reset entirely.
    near = replace(AVAILABLE, primary=RateWindow(98, 300, 105))
    reset = replace(AVAILABLE, primary=RateWindow(0, 300, 500))
    sent, _ = run_snapshots(monkeypatch, [near, reset, reset], grace=10)
    assert len(sent) == 1 and sent[0][2] == 120


def test_early_refill_near_limit_without_observed_full_snapshot(monkeypatch):
    near = replace(AVAILABLE, primary=RateWindow(99, 300, 10000))
    refill = replace(near, primary=RateWindow(5, 300, 10000))
    sent, _ = run_snapshots(monkeypatch, [near, refill, refill])
    assert len(sent) == 1 and sent[0][2] == 110


def test_small_quota_correction_does_not_trigger_recovery(monkeypatch):
    near = replace(AVAILABLE, primary=RateWindow(96, 300, 10000))
    correction = replace(near, primary=RateWindow(94, 300, 10000))
    sent, _ = run_snapshots(monkeypatch, [near, correction])
    assert not sent


def test_worker_retries_only_message_after_verified_goal_success(monkeypatch):
    from recharge_ai_task import target_delivery as delivery
    from recharge_ai_task.config import AppConfig
    from recharge_ai_task.delivery_policy import UsageLedger
    target = replace(A, send_prompt=True, send_goal=True)
    AppConfig(goal_limit=1, prompt_limit=1).save()
    activations, prompts = [], []
    def recover(t, text, **kwargs):
        kwargs['actions'].perform('goal', lambda: activations.append(t.id))
        kwargs['actions'].confirm_goal()
        def fail():
            raise RuntimeError('Prompt rejected after Goal activation')
        try:
            kwargs['actions'].perform('prompt', fail)
        except RuntimeError as exc:
            return DeliveryResult(t, False, str(exc))
    monkeypatch.setattr(delivery, 'recover_target', recover)
    monkeypatch.setattr(delivery, '_send_thread', lambda t, text: prompts.append((t.id,text)))
    run_snapshots(monkeypatch, [BLOCKED, AVAILABLE, AVAILABLE], selected=(target,))
    assert activations == ['a'] and prompts == [('a','Continue')]
    usage = UsageLedger().snapshot()
    assert usage[(target.key,'goal')].used == usage[(target.key,'prompt')].used == 1


def test_checkpoint_preserves_recovery_and_prevents_duplicate_after_restart(monkeypatch):
    from recharge_ai_task import watch_state
    from recharge_ai_task.config import AppConfig
    config = AppConfig(desktop_targets=[A.to_dict()])
    path = watch_state.state_path(config)
    state = watch.WatchState()
    run_snapshots(monkeypatch, [BLOCKED], state=state)
    watch_state.save(path,state)
    restored = watch_state.load(path)
    sent, _ = run_snapshots(monkeypatch, [AVAILABLE], state=restored)
    assert len(sent) == 1
    watch_state.save(path,restored)
    sent, _ = run_snapshots(monkeypatch, [AVAILABLE], state=watch_state.load(path))
    assert not sent


def test_one_stale_near_limit_snapshot_does_not_replay_a_refill(monkeypatch):
    near = replace(AVAILABLE, primary=RateWindow(99,300,10000))
    refill = replace(near, primary=RateWindow(5,300,10000))
    sent,_ = run_snapshots(monkeypatch,[near,refill,near,refill,refill])
    assert len(sent)==1
    sent,_ = run_snapshots(monkeypatch,[near,refill,near,near,refill])
    assert len(sent)==2


def test_restored_in_flight_recipient_is_reported_uncertain_not_replayed(monkeypatch):
    from recharge_ai_task import watch_state
    from recharge_ai_task.activity import ActivityLog
    from recharge_ai_task.config import AppConfig
    path=watch_state.state_path(AppConfig(desktop_targets=[A.to_dict()]))
    state=watch.WatchState(startup_checked=True,pending=True,in_flight=(A.key,A.title))
    watch_state.save(path,state)
    restored=watch_state.load(path)
    sent,_=run_snapshots(monkeypatch,[AVAILABLE],state=restored)
    assert not sent and A.key in restored.delivered
    assert ActivityLog().read()[-1]['status']=='uncertain'


def test_pending_counts_respect_remaining_allowances(monkeypatch):
    from recharge_ai_task.config import AppConfig
    from recharge_ai_task.delivery_policy import UsageLedger
    target=replace(A,send_prompt=True,send_goal=False)
    AppConfig(prompt_limit=1).save()
    ledger=UsageLedger()
    attempt=ledger.reserve(target.key,'prompt',1);ledger.finish(attempt,'sent')
    state=watch.WatchState(startup_checked=True,pending=True)
    run_snapshots(monkeypatch,[RuntimeError('offline')],selected=(target,),state=state)
    assert state.progress['pending_recipients']==0
    assert state.progress['pending_messages']==0
    assert state.progress['selected_recipients']==0


def test_one_use_custom_does_not_replay_when_worker_restarts(monkeypatch):
    from recharge_ai_task.config import AppConfig
    from recharge_ai_task import target_delivery
    target=replace(A,send_prompt=True,send_goal=False,custom_prompt='Use once',custom_prompt_once='once-token')
    AppConfig(continue_prompt='Default',desktop_targets=[target.to_dict()]).save()
    sent=[]
    monkeypatch.setattr(target_delivery,'_send_thread',lambda t,text:sent.append(text))
    # Simulate completion during a prior recovery, then restart with a stale target.
    assert target_delivery.send_signals([target],'Default')[0].success
    state=watch.WatchState(startup_checked=True,pending=False,delivered={target.key})
    run_snapshots(monkeypatch,[AVAILABLE],selected=(target,),state=state)
    assert sent==['Use once']
    assert AppConfig.load().targets()[0].custom_prompt is None
