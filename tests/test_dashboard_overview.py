"""Overview messages distinguish monitoring, quota checks and recovery."""
import pytest

from recharge_ai_task.status_display import watch_check_summary


@pytest.mark.parametrize("runtime,value,detail", [
    (None, "Unavailable", "tray could not be reached"),
    ({}, "—", "monitoring is off"),
    ({"desktop_watch": True, "stopping": True}, "Stopping…", "being stopped"),
    ({"desktop_watch": True, "restarting": True}, "Updating…", "Applying saved"),
    ({"desktop_watch": True, "watch_error": "offline"}, "Needs attention", "activity messages"),
    ({"watch_pause_reason": "empty"}, "Waiting", "valid recipients"),
    ({"cli_running": True}, "CLI mode", "terminal"),
    ({"desktop_watch": True}, "Waiting…", "monitoring update"),
    ({"desktop_watch": True, "watch_progress": {"phase": "checking_quota"}}, "Checking…", "quota availability"),
    ({"desktop_watch": True, "watch_progress": {"phase": "delivering"}}, "Sending…", "selected signals"),
])
def test_overview_does_not_confuse_monitoring_with_task_activity(runtime, value, detail):
    actual, explanation = watch_check_summary(runtime, 100)
    assert actual == value
    assert detail in explanation


@pytest.mark.parametrize("phase,explanation", [
    ("waiting_quota", "Waiting for quota"),
    ("quota_unavailable", "could not be read"),
    ("grace_period", "grace period"),
    ("retry_pending", "delivery failure"),
    ("monitoring", "Watching for quota changes"),
])
def test_countdown_uses_worker_deadline_and_keeps_reason(phase, explanation):
    runtime = {"desktop_watch": True,
               "watch_progress": {"phase": phase, "next_check_at": 130}}
    assert watch_check_summary(runtime, 100.1)[0] == "In 00:30"
    assert watch_check_summary(runtime, 115)[0] == "In 00:15"
    assert watch_check_summary(runtime, 135)[0] == "Due now"
    assert explanation in watch_check_summary(runtime, 135)[1]


def test_stopped_watch_does_not_display_an_old_countdown():
    runtime = {"desktop_watch": False,
               "watch_progress": {"phase": "waiting_quota", "next_check_at": 150}}
    assert watch_check_summary(runtime, 100) == ("—", "Desktop monitoring is off.")



def test_recovery_countdown_uses_send_deadline_not_next_poll():
    runtime={"desktop_watch":True,"watch_progress":{"phase":"grace_period","next_check_at":115,"recovery_at":160}}
    value,reason=watch_check_summary(runtime,100)
    assert value=="Send in 01:00" and "observed availability" in reason
    runtime["watch_progress"]["recovery_at"]=3761
    assert watch_check_summary(runtime,100)[0]=="Send in 01:01:01"


def test_send_forecast_switches_to_observed_recovery_and_clears_when_stopped():
    from recharge_ai_task.status_display import send_schedule_summary
    progress = dict(phase="waiting_quota", pending_recipients=3,
                    pending_messages=2, pending_goals=3, expected_reset_at=500)
    runtime = dict(desktop_watch=True, watch_progress=progress)
    title, timer, counts = send_schedule_summary(runtime, 100, 60)
    assert title.startswith("Forecast:") and "00:07:40" in timer and "earlier" in timer
    assert counts == "Up to 2 messages · 3 Goal activations · 3 recipients"
    progress.update(phase="grace_period", recovery_at=180)
    title, timer, _ = send_schedule_summary(runtime, 130, 60)
    assert title.startswith("Send:") and timer == "In 00:00:50"
    progress.update(phase="retry_pending", next_check_at=220)
    assert send_schedule_summary(runtime, 200)[1] == "In 00:00:20"
    progress["phase"] = "quota_unavailable"
    assert "unconfirmed" in send_schedule_summary(runtime, 200)[1]
    progress["phase"] = "delivering"
    assert send_schedule_summary(runtime, 181)[0] == "Sending now"
    runtime["stopping"] = True
    assert send_schedule_summary(runtime, 181)[0] == "Stopping…"
    assert send_schedule_summary(runtime, 181)[2] == "0 messages · 0 Goal activations"


def test_schedule_uses_worker_grace_and_shows_selected_plan_while_monitoring():
    from recharge_ai_task.status_display import send_schedule_summary
    progress = dict(phase="monitoring", updated_at=100, next_check_at=130,
                    selected_recipients=2, selected_messages=1, selected_goals=2,
                    pending_cycle=False, expected_reset_at=500, grace_seconds=120)
    runtime = dict(desktop_watch=True,watch_progress=progress)
    title,timer,counts = send_schedule_summary(runtime,100,0)
    assert title.startswith('Next reset forecast:') and '00:08:40' in timer
    assert counts == 'Selected, up to 1 messages · 2 Goal activations · 2 recipients'
    assert send_schedule_summary(runtime,110,0)[1] != timer
    assert send_schedule_summary(runtime,200,0)[0] == 'Worker update overdue'
    assert send_schedule_summary(None,200)[0] == 'Schedule unavailable'
    runtime['watch_progress'] = None
    assert send_schedule_summary(runtime,200)[0] == 'Waiting for worker schedule'
