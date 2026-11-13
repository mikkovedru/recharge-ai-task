"""Independent provider quota, timing and allowance presentation."""
from dataclasses import replace
import pytest
from recharge_ai_task.config import AppConfig
from recharge_ai_task.delivery_policy import Usage
from recharge_ai_task.provider_monitor import provider_status, observations, statistics
from recharge_ai_task.quota import Quota,RateWindow
from recharge_ai_task.targets import Target


def status(provider='codex',**kwargs):
    params=dict(targets=[],config=AppConfig(),usage={},now=1000)
    params.update(kwargs)
    return provider_status(provider,**params)


def test_provider_schedules_and_statistics_never_use_another_provider():
    codex=Target('thread','same','Same',send_prompt=True,send_goal=False)
    claude=replace(codex,provider='claude')
    rows={'codex':dict(phase='grace_period',updated_at=1000,next_check_at=1010,recovery_at=1015,pending_cycle=True,pending_recipients=1,pending_messages=1,pending_goals=0),
          'claude':dict(phase='waiting_quota',updated_at=1000,next_check_at=1030,expected_reset_at=2000,pending_cycle=True,pending_recipients=1,pending_messages=1,pending_goals=0)}
    runtime=dict(desktop_watch=True,watch_progress={'providers':rows})
    config=AppConfig(grace_seconds=20)
    data=dict(targets=[codex,claude],config=config,runtime=runtime,
              usage={(codex.key,'prompt'):Usage(3,0),(claude.key,'prompt'):Usage(7,1)})
    first=status('codex',**data);second=status('claude',**data)
    assert first['recovery'].startswith('Send:') and '00:00:15' in first['countdown']
    assert second['recovery'].startswith('Forecast:') and '00:17:00' in second['countdown']
    assert first['counts']['used_messages']==3 and second['counts']['used_messages']==7
    assert first['counts']['recipients']==second['counts']['recipients']==1
    assert second['state']=='warning'
    assert status('muse',runtime=runtime)['check']=='Not monitored'


@pytest.mark.parametrize('enabled,state',[(True,'error'),(False,'warning')])
def test_login_error_retains_stale_quota_but_does_not_claim_availability(enabled,state):
    target=Target('session','id','Chat',provider='muse',send_prompt=enabled,send_goal=False)
    data=status('muse',targets=[target] if enabled else [],error='muse login required',
                quota=Quota('Muse Pro',RateWindow(42,300,1300),None,False),checked_at=900)
    assert data['state']==state and data['plan']=='Muse Pro'
    assert data['windows'][0][1]==42
    assert 'Last known quota' in data['freshness'] and data['availability']=='Quota unavailable'


def test_missing_quota_never_becomes_fake_zero_and_inactive_provider_is_filterable():
    data=status('claude',installed=False)
    assert data['state']=='off' and data['windows']==[] and data['plan']=='Unavailable'
    assert data['check']=='Not detected' and 'No successful' in data['freshness']


def test_stale_observations_and_flag_only_limits_are_visible():
    quota=Quota('Plus',RateWindow(20,300,1300),None,False)
    assert status(quota=quota,checked_at=1)['state']=='warning'
    blocked=status(quota=replace(quota,rate_limit_reached=True),checked_at=999)
    assert blocked['state']=='warning' and blocked['availability']=='Quota exhausted'


def test_unknown_statistics_are_not_reported_as_verified_zero():
    assert 'unavailable' in status(usage_error='ledger locked')['stats']


def test_legacy_worker_observation_is_only_codex_by_default():
    progress={'phase':'monitoring'}
    runtime={'desktop_watch':True,'watch_progress':progress}
    assert observations(runtime)=={'codex':progress}
    runtime['watch_settings']={'provider':'claude'}
    assert observations(runtime)=={'claude':progress}


def test_goal_with_no_remaining_allowance_keeps_message_count():
    target=Target('thread','id','Chat',send_prompt=True,send_goal=True,goal_limit=1)
    counts=statistics([target],AppConfig(),{(target.key,'goal'):Usage(1,0)})
    assert counts['messages']==1 and counts['goals']==0


def test_near_limit_warning_matches_quota_threshold_colors():
    quota=Quota('Plus',RateWindow(85,300,1300),None,False)
    data=status(quota=quota,checked_at=999)
    assert data['state']=='warning' and data['availability']=='Quota available'


def test_local_history_does_not_falsely_mark_provider_installed(monkeypatch):
    from recharge_ai_task import providers
    from recharge_ai_task.targets import Inventory
    monkeypatch.setattr(providers,'installed_providers',lambda:{'claude':None,'muse':'fixture-muse'})
    monkeypatch.setattr(providers,'discover_windows',lambda *_:[])
    monkeypatch.setattr(providers,'discover_targets',lambda provider:Inventory([Target('session','id','History',provider=provider)]))
    inventory=providers.discover_all_targets()
    assert inventory.providers==('claude','muse')
    assert inventory.installed_providers==('muse',)
    assert {t.provider for t in inventory.targets}=={'claude','muse'}


def test_terminal_only_status_does_not_invent_quota_or_recipient_statistics():
    data=status('opencode',installed=True,error='not a shared quota API')
    assert data['terminal_only'] and data['state']=='off'
    assert data['command']=='recharge-ai-task run --provider opencode'
    assert 'model provider' in data['notices'] and not data['error']
    assert 'counts' not in data and 'windows' not in data
