"""Cached previews must follow allowance ordering and native Goal gating."""
from dataclasses import replace

import pytest

from recharge_ai_task.config import AppConfig
from recharge_ai_task.delivery_policy import Usage
from recharge_ai_task.recipient_readiness import recipient_readiness
from recharge_ai_task.targets import Target

T = Target('thread', 'fixture', 'Fixture', instance='/fixture', endpoint='/fixture/ipc/ipc.sock',
           task_status='Idle', goal_status='Usage limited', send_prompt=True, send_goal=True)


def preview(target=T, config=None, usage=None, message='Continue', **kwargs):
    return {a.action: a for a in recipient_readiness(target, config or AppConfig(), usage or {}, message, **kwargs).actions}


@pytest.mark.parametrize('status', ['Paused', 'Blocked', 'Budget limited', 'Complete', 'No goal'])
def test_skipped_goal_keeps_independent_message_eligible(status):
    actions = preview(replace(T, goal_status=status))
    assert actions['goal'].state == 'passive'
    assert actions['prompt'].ready


@pytest.mark.parametrize('task', ['Running', 'Waiting for input', 'Waiting for approval', 'Waiting for approval / Waiting for input'])
def test_running_goal_is_automatic_only_gate(task):
    target = replace(T, task_status=task)
    automatic, manual = preview(target), preview(target, manual=True)
    assert automatic['goal'].state == 'passive' and automatic['prompt'].ready
    assert manual['goal'].ready and manual['prompt'].ready


def test_paused_goal_can_resume_manually():
    target = replace(T, goal_status='Paused', send_prompt=False)
    assert not recipient_readiness(target, AppConfig(), {}, '').ready
    assert recipient_readiness(target, AppConfig(), {}, '', manual=True).ready


@pytest.mark.parametrize('field', ['task_status', 'goal_status'])
def test_unreadable_goal_status_does_not_withhold_message(field):
    actions = preview(replace(T, **{field: 'Unavailable'}))
    assert actions['goal'].state == 'uncertain' and actions['goal'].issue == field
    assert actions['prompt'].ready
    assert preview(replace(T, send_goal=False, **{field: 'Unavailable'}))['prompt'].ready


@pytest.mark.parametrize('status', ['Error', 'systemError', 'Future status'])
def test_errors_and_new_statuses_still_allow_recovery(status):
    assert all(a.ready for a in preview(replace(T, task_status=status, goal_status=status)).values())


def test_goal_limit_does_not_withhold_message():
    actions = preview(replace(T, goal_status='No goal'), AppConfig(goal_limit=0))
    assert actions['goal'].state == 'blocked' and actions['goal'].issue == 'allowance'
    assert actions['prompt'].ready


def test_message_limit_does_not_withhold_a_resumable_goal():
    actions = preview(config=AppConfig(prompt_limit=0))
    assert actions['prompt'].state == 'blocked' and actions['goal'].ready
    assert all(a.state == 'blocked' for a in preview(config=AppConfig(), message=' ').values())
    assert preview(config=AppConfig(prompt_limit=0), message=' ')['goal'].ready


def test_active_goal_is_not_an_activation_but_message_remains_eligible():
    actions = preview(replace(T, goal_status='Active'))
    assert actions['goal'].state == 'passive' and actions['prompt'].ready
    assert not recipient_readiness(replace(T, goal_status='Active', send_prompt=False), AppConfig(), {}, '').ready


def test_uncertain_attempts_explain_consumed_allowance_without_inventing_a_gate():
    target = replace(T, send_goal=False)
    usage = {(T.key, 'prompt'): Usage(1, 1)}
    action = preview(target, AppConfig(prompt_limit=1), usage)['prompt']
    assert action.state == 'blocked' and 'unconfirmed' in action.warning
    action = preview(target, AppConfig(prompt_limit=2), usage)['prompt']
    assert action.ready and action.warning
    assert all(a.state == 'uncertain' for a in preview(ledger_error='Disk unreadable').values())


@pytest.mark.parametrize('target', [replace(T, endpoint=''),
                                   replace(T, kind='window'), replace(T, kind='other')])
def test_missing_or_invalid_routing_is_explained(target):
    assert all(a.state == 'blocked' and a.issue == 'routing' for a in preview(target).values())


def test_saved_unavailable_recipient_is_unverified_and_no_actions_are_passive():
    assert all(a.state == 'uncertain' for a in preview(replace(T, status='Unavailable — saved selection')).values())
    assert not recipient_readiness(replace(T, send_prompt=False, send_goal=False), AppConfig(), {}, '').ready


@pytest.mark.parametrize('manual', [False, True])
def test_stopped_by_quota_is_ready_to_resume_without_becoming_active(manual):
    target = replace(T, goal_status='Stopped by quota', send_prompt=False)
    readiness = preview(target, manual=manual)
    assert readiness['goal'].ready
    assert target.goal_status == 'Stopped by quota'


def test_goal_profile_mismatch_only_blocks_goal():
    actions = preview(replace(T, endpoint='/wrong/ipc.sock'))
    assert actions['goal'].state == 'blocked' and actions['goal'].issue == 'routing'
    assert actions['prompt'].ready
