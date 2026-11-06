from dataclasses import replace
import threading

import pytest
from recharge_ai_task import quota, wrapper
from recharge_ai_task.pty_backend import StopEvent


def snapshot(**changes):
    data={'primary':{'usedPercent':100,'windowDurationMins':300,'resetsAt':10000},
          'credits':{'hasCredits':False,'unlimited':False},'rateLimitReachedType':None}
    data.update(changes)
    return quota.parse_quota(data)


@pytest.mark.parametrize('credits',[{'hasCredits':True,'unlimited':False},{'hasCredits':False,'unlimited':True}])
def test_added_credits_can_make_included_full_window_usable(credits):
    state=snapshot(credits=credits)
    assert not quota.quota_blocked(state) and state.exhausted_window() is None


@pytest.mark.parametrize('block',[{'rateLimitReachedType':'rate_limit_reached'},{'spendControlReached':True}])
def test_explicit_backend_blocks_win_over_available_credits(block):
    assert quota.quota_blocked(snapshot(credits={'hasCredits':True,'unlimited':True},**block))


def test_unspent_reset_credit_does_not_itself_recover_quota():
    assert quota.quota_blocked(snapshot(resetCredits={'availableCount':3}))
    assert quota.quota_blocked(snapshot(credits={'hasCredits':'true','unlimited':False}))


def test_check_wakeup_is_not_a_stop_request():
    stop=StopEvent()
    entered,done=threading.Event(),threading.Event()
    def wait():
        entered.set()
        assert not stop.wait(10)
        done.set()
    worker=threading.Thread(target=wait)
    worker.start()
    assert entered.wait(1)
    stop.wake()
    assert done.wait(1) and not stop.is_set()
    worker.join(1)
    stop.set()
    assert stop.wait(10)


def test_terminal_wrapper_notices_early_quota_recovery(monkeypatch):
    now=[100.0]
    limited=snapshot(rateLimitReachedType='rate_limit_reached')
    ready=replace(limited,primary=replace(limited.primary,used_percent=1),rate_limit_reached=False)
    states=iter([ready,ready])
    monkeypatch.setattr(wrapper,'fetch_quota',lambda _:next(states))
    monkeypatch.setattr(wrapper.time,'time',lambda:now[0])
    waits=[]
    def sleep(pty,stop,due):
        waits.append(due)
        now[0]=due
        return True
    monkeypatch.setattr(wrapper,'sleep_with_proxy',sleep)
    pty=type('Pty',(),{'isalive':lambda self:True})()
    assert wrapper.wait_for_quota_recovery(pty,StopEvent(),'codex',10060,10,initial=limited)
    assert now[0]==140 and waits==[130,140]


@pytest.mark.parametrize('poll',[7,45])
def test_terminal_recovery_uses_configured_polling_and_grace_deadline(monkeypatch,poll):
    now=[100.0];waits=[]
    ready=replace(snapshot(),primary=quota.RateWindow(1,300,10000))
    monkeypatch.setattr(wrapper,'fetch_quota',lambda _:ready)
    monkeypatch.setattr(wrapper.time,'time',lambda:now[0])
    def sleep(pty,stop,due):
        waits.append(due-now[0]);now[0]=due;return True
    monkeypatch.setattr(wrapper,'sleep_with_proxy',sleep)
    pty=type('Pty',(),{'isalive':lambda self:True})()
    assert wrapper.wait_for_quota_recovery(pty,StopEvent(),'codex',10060,10,initial=snapshot(),poll_seconds=poll)
    assert waits[0]==poll and all(0<value<=poll for value in waits)
    assert now[0]==100+poll+10


def test_cli_wrapper_receives_the_shared_polling_setting(monkeypatch):
    from recharge_ai_task import cli
    from recharge_ai_task.config import AppConfig
    AppConfig(poll_seconds=7).save()
    captured=[]
    monkeypatch.setattr(cli,'run_wrapper',lambda config:captured.append(config) or 0)
    assert cli.main(['run'])==0
    assert captured[0].poll_seconds==7
