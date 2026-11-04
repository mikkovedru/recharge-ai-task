"""Display semantics shared by status cells, tooltips, and the message log."""

from math import ceil

COLORS = {"success": "#137333", "warning": "#8a6200", "error": "#b3261e"}
DARK_COLORS = {"success": "#73d99b", "warning": "#ffd166", "error": "#ff8a80"}


def status_colors(widget):
    if widget is None:
        return COLORS
    context = widget.get_style_context()
    found,color = context.lookup_color("theme_bg_color")
    if found:
        dark = .2126*color.red + .7152*color.green + .0722*color.blue < .5
    else:
        color = context.get_background_color(0)
        if color.alpha > .5:
            dark = .2126*color.red + .7152*color.green + .0722*color.blue < .5
        else:
            color = context.get_color(0)
            dark = .2126*color.red + .7152*color.green + .0722*color.blue > .7
    return DARK_COLORS if dark else COLORS


def watch_check_summary(runtime, now):
    """Describe the worker's next check without predicting task recovery."""
    if runtime is None:
        return "Unavailable", "The tray could not be reached."
    if runtime.get("stopping"):
        return "Stopping…", "Pending monitoring is being stopped."
    if runtime.get("restarting"):
        return "Updating…", "Applying saved monitoring settings."
    if runtime.get("watch_error"):
        return "Needs attention", "See the activity messages below."
    if runtime.get("watch_pause_reason"):
        return "Waiting", "Choose valid recipients and signal settings."
    if runtime.get("cli_running"):
        return "CLI mode", "Quota recovery is managed in the terminal."
    if not runtime.get("desktop_watch"):
        return "—", "Desktop monitoring is off."
    progress = runtime.get("watch_progress") or {}
    phase = progress.get("phase")
    if phase == "checking_quota":
        return "Checking…", "Reading current quota availability."
    if phase == "delivering":
        return "Sending…", "Delivering the selected signals."
    reasons = {"waiting_quota": "Waiting for quota; early resets and added usable credits are checked too.",
               "quota_unavailable": "Quota could not be read; checking again.",
               "grace_period": "Quota is available; retaining the grace period.",
               "retry_pending": "A confirmed delivery failure is waiting for retry.",
               "monitoring": "Watching for quota changes."}
    if phase == "grace_period" and isinstance(progress.get("recovery_at"),(int,float)):
        remaining=max(0,ceil(progress["recovery_at"]-now))
        hours,remainder=divmod(remaining,3600)
        minutes,seconds=divmod(remainder,60)
        countdown=f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
        return f"Send in {countdown}", "Quota recovered; grace is measured from observed availability, including early resets."
    due = progress.get("next_check_at")
    if phase not in reasons or not isinstance(due, (int, float)):
        return "Waiting…", "Waiting for a monitoring update."
    seconds = max(0, ceil(due - now))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    countdown = f"{hours:02}:{minutes:02}:{seconds:02}" if hours else f"{minutes:02}:{seconds:02}"
    return (f"In {countdown}" if due > now else "Due now"), reasons[phase]


def send_schedule_summary(runtime, now, grace_seconds=0):
    """Separate a forecast quota reset from a confirmed recovery send time."""
    from datetime import datetime

    zero = "0 messages · 0 Goal activations"
    if runtime is None:
        return "Schedule unavailable", "The tray could not be reached; no send time is confirmed.", zero
    for flag, title, detail in (
        ("stopping", "Stopping…", "Automatic sending is stopping."),
        ("restarting", "Updating…", "Applying saved settings; waiting for the replacement worker."),
        ("watch_error", "Monitoring needs attention", str(runtime.get("watch_error", ""))),
        ("watch_pause_reason", "Monitoring is waiting", str(runtime.get("watch_pause_reason", "")))):
        if runtime.get(flag):
            return title, detail, zero
    if not runtime.get("desktop_watch"):
        return "No send scheduled", "Desktop monitoring is off.", zero
    progress = runtime.get("watch_progress") or {}
    if not progress:
        return "Waiting for worker schedule", "No scheduling update received; restart an older tray build.", zero
    if progress.get("count_error"):
        return "Allowances unavailable", progress["count_error"], "Action counts unavailable"
    pending = progress.get("pending_cycle", bool(progress.get("pending_recipients")))
    prefix_key = "pending" if pending else "selected"
    recipients = progress.get(prefix_key + "_recipients", 0)
    if not recipients:
        return ("No eligible actions" if pending or "selected_recipients" in progress else "No send scheduled",
                "Check selected actions and remaining allowances." if pending or "selected_recipients" in progress else "Watching for quota recovery.", zero)
    counts = (f"{'Up to' if pending else 'Selected, up to'} {progress.get(prefix_key + '_messages', 0)} messages · "
              f"{progress.get(prefix_key + '_goals', 0)} Goal activations · {recipients} recipients")
    phase = progress.get("phase")
    updated = progress.get("updated_at")
    if isinstance(updated, (int, float)) and now > max(updated + 45, (progress.get("next_check_at") or updated) + 10):
        return "Worker update overdue", "Send time unconfirmed; waiting for monitoring to respond.", counts
    if phase == "delivering":
        return "Sending now", "Live status and allowance rules apply.", counts
    if phase == "quota_unavailable":
        return "Waiting for usable quota", "Quota could not be read; send time unconfirmed.", counts
    confirmed = progress.get("next_check_at") if phase == "retry_pending" else progress.get("recovery_at")
    forecast = progress.get("expected_reset_at")
    if pending and isinstance(confirmed, (int, float)):
        due, prefix = confirmed, "Retry" if phase == "retry_pending" else "Send"
    elif isinstance(forecast, (int, float)):
        due = forecast + progress.get("grace_seconds", grace_seconds)
        prefix = "Forecast" if pending else "Next reset forecast"
    else:
        return "Waiting for usable quota" if pending else "Watching quota", "Send time is not known yet.", counts
    remaining = max(0, ceil(due - now))
    hours, rest = divmod(remaining, 3600)
    minutes, seconds = divmod(rest, 60)
    timer = f"{hours:02}:{minutes:02}:{seconds:02}"
    when = datetime.fromtimestamp(due).strftime("%Y-%m-%d %H:%M:%S")
    detail = (f"In {timer}" if remaining else "Due; checking usable quota") if prefix in {"Send", "Retry"} else (
        f"In {timer} · may send earlier" if remaining else "Awaiting usable quota; forecast passed")
    if not pending:
        detail += " · sends require quota recovery"
    return f"{prefix}: {when}", detail, counts


TASK_STATES = {
    "Active": ("success", "Codex is working on a turn."),
    "Running": ("success", "Codex is working on a turn."),
    "Waiting for approval": ("warning", "A turn is active but needs your approval before continuing."),
    "Waiting for input": ("warning", "A turn is active but needs your reply before continuing."),
    "Idle": ("normal", "No turn is currently running."),
    "Error": ("error", "Codex reports a task error, which can also follow quota exhaustion. This does not block selected messages or resumable goals."),
    "Not loaded": ("normal", "The saved chat is not loaded in the queried backend."),
    "Unavailable": ("warning", "The current state could not be read; this does not mean idle."),
}
GOAL_STATES = {
    "Error": ("error", "Codex reports a goal error. Native Goal activation can still be attempted after quota recovers; it must be verified live."),
    "Active": ("success", "The goal is enabled and may continue automatically; check Task status for current activity."),
    "Paused": ("warning", "The goal is intentionally paused. Manual Goal signals may resume it; quota recovery leaves it paused."),
    "Usage limited": ("warning", "The goal stopped because account quota was exhausted. Goal signals can resume it when quota recovers."),
    "Budget limited": ("error", "The goal reached its own token budget. A continuation signal does not override this limit."),
    "Blocked": ("error", "The goal cannot make progress without user input or an external change."),
    "Complete": ("normal", "Codex marked the goal achieved. A continuation signal does not reopen it."),
    "No goal": ("normal", "This chat has no saved goal."),
    "Unavailable": ("warning", "The goal state could not be read; this does not mean there is no goal."),
}


def status_level(value, *, goal=False):
    states = GOAL_STATES if goal else TASK_STATES
    # A task may simultaneously need approval and input.
    parts = value.split(" / ")
    levels = [states.get(part, ("warning", ""))[0] for part in parts]
    return next((level for level in ("error", "warning", "success") if level in levels), "normal")


def status_tooltip(value, *, goal=False):
    states = GOAL_STATES if goal else TASK_STATES
    detail = states.get(value,("normal","Unrecognized status: allowed by default."))[1]
    automatic = "Continue" if continuation_allowed(value,goal=goal) else "Skip / unavailable"
    manual = "Continue" if continuation_allowed(value,goal=goal,manual=True) else "Skip / unavailable"
    return (f"{'Goal' if goal else 'Task'} statuses\n{value}: {detail}\n"
            f"Automatic Goal: {automatic}\nSend now Goal: {manual}\n"
            "Other nonempty new statuses are allowed. Message-only does not use these gates.")


def continuation_allowed(value, *, goal=False, manual=False):
    from .recovery_rules import goal_allowed, task_allowed
    if value == "Unavailable" or goal and value == "No goal":
        return False
    if goal:
        raw = {"Active":"active", "Paused":"paused", "Blocked":"blocked", "Usage limited":"usageLimited",
               "Budget limited":"budgetLimited", "Complete":"complete", "Error":"error"}.get(value,value)
        return goal_allowed(raw,manual=manual)
    raw = "active" if value in {"Active","Running"} or value.startswith("Waiting for") else value
    return task_allowed(raw,manual=manual)


def status_rows(*, goal=False):
    states = GOAL_STATES if goal else TASK_STATES
    rows = [(value, continuation_allowed(value,goal=goal), continuation_allowed(value,goal=goal,manual=True), detail)
            for value, (_level,detail) in states.items()]
    rows.append(("Other / new statuses",True,True,"Nonempty unrecognized statuses are allowed by default. Native verification still applies."))
    return sorted(rows,key=lambda row:(not row[1],row[0]))
