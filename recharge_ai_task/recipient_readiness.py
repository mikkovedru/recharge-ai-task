"""Cached target eligibility for display; the sender still verifies live state."""
from dataclasses import dataclass, replace
from pathlib import Path

from .delivery_policy import Usage, effective_limit
from .status_display import continuation_allowed


@dataclass(frozen=True)
class ActionReadiness:
    action: str
    state: str
    reason: str
    issue: str = ""
    warning: str = ""

    @property
    def ready(self):
        return self.state == "ready"


@dataclass(frozen=True)
class RecipientReadiness:
    actions: tuple[ActionReadiness, ...]

    @property
    def ready(self):
        return any(action.ready for action in self.actions)


def recipient_readiness(target, config, usage, message, *, manual=False, ledger_error=""):
    """Preview each action independently; Goal handling never gates a message."""
    prompt, goal = target.signal_actions()
    prompt_limit = effective_limit(target, "prompt", config) if prompt else 0
    empty_message = prompt and not message.strip() and (prompt_limit is None or
        usage.get((target.key, "prompt"), Usage()).used < prompt_limit)
    if prompt and goal and not empty_message:
        goal_preview = recipient_readiness(replace(target, send_prompt=False, send_goal=True),
            config, usage, message, manual=manual, ledger_error=ledger_error)
        message_preview = recipient_readiness(replace(target, send_prompt=True, send_goal=False),
            config, usage, message, manual=manual, ledger_error=ledger_error)
        return RecipientReadiness(goal_preview.actions + message_preview.actions)
    actions = [key for key, enabled in (("goal", goal), ("prompt", prompt)) if enabled]
    if not actions:
        return RecipientReadiness(())
    notes = {}
    for action in actions:
        count = usage.get((target.key, action), Usage())
        if count.uncertain:
            notes[action] = f"{count.uncertain} earlier {action} action(s) are unconfirmed and count as used. Check the chat before retrying or resetting counts."

    def result(values):
        return RecipientReadiness(tuple(replace(value, warning=notes.get(value.action, "")) for value in values))

    def all_actions(state, reason, issue):
        return result([ActionReadiness(action, state, reason, issue) for action in actions])

    if ledger_error:
        return all_actions("uncertain", "Allowances unavailable — delivery blocked. " + ledger_error, "allowance")
    limits = {action: effective_limit(target, action, config) for action in actions}
    reached = {action for action, limit in limits.items() if limit is not None
               and usage.get((target.key, action), Usage()).used >= limit}
    if "goal" in reached:
        return all_actions("blocked", "Goal limit reached; reset counts or change the limit", "allowance")
    values = {}
    if "prompt" in reached:
        values["prompt"] = ActionReadiness("prompt", "blocked", "Message limit reached; reset counts or change the limit", "allowance")
    elif prompt and not message.strip():
        return all_actions("blocked", "Message is empty; enter a default or custom message", "message")

    eligible = [action for action in actions if action not in values]
    if not eligible:
        return result([values[action] for action in actions])

    def remaining(state, reason, issue):
        values.update({action: ActionReadiness(action, state, reason, issue) for action in eligible})
        return result([values[action] for action in actions])

    if target.kind == "session":
        if not target.endpoint or not target.cwd or not Path(target.endpoint).is_file() or not Path(target.cwd).is_dir():
            return remaining("blocked", "Local chat transcript or project directory is unavailable; refresh", "routing")
        if goal:
            return remaining("blocked", "Native Goal activation is only available for Codex chats", "routing")
    elif target.kind == "thread":
        if not target.endpoint:
            return remaining("blocked", "Desktop routing unavailable; open Codex and refresh", "routing")
        if goal and (not target.instance or Path(target.endpoint).resolve() != (Path(target.instance) / "ipc/ipc.sock").resolve()):
            return remaining("blocked", "Goal routing does not match this Codex profile; refresh", "routing")
    elif target.kind == "window":
        if goal:
            return remaining("blocked", "Goal requires a chat ID; disable Resume goal or choose a chat", "routing")
        if target.pid is None:
            return remaining("blocked", "Window process unavailable; refresh before sending", "routing")
    else:
        return remaining("blocked", "Unsupported target type", "routing")
    if target.status.startswith("Unavailable"):
        return remaining("uncertain", "Target unavailable at last refresh; open Codex and refresh", "routing")
    if goal:
        goal_status, task_status = target.goal_status, target.task_status
        if not goal_status or goal_status == "Unavailable":
            return remaining("uncertain", "Goal status unavailable; delivery needs live verification", "goal_status")
        if not continuation_allowed(goal_status, goal=True, manual=manual):
            reason = ("Paused — automatic recovery respects intentional pauses; Send now may resume" if goal_status == "Paused" else
                      f"{goal_status} — no Goal activation")
            values["goal"] = ActionReadiness("goal", "passive", reason, "goal_status")
        elif not task_status or task_status == "Unavailable":
            return remaining("uncertain", "Task status unavailable; delivery needs live verification", "task_status")
        elif not continuation_allowed(task_status, manual=manual):
            values["goal"] = ActionReadiness("goal", "passive", f"Task {task_status.lower()} — automatic Goal skipped", "task_status")
        elif goal_status == "Active":
            values["goal"] = ActionReadiness("goal", "passive", "Already active — no Goal activation needed", "goal_status")
        else:
            values["goal"] = ActionReadiness("goal", "ready", "Ready to verify/resume Goal")
    if prompt and "prompt" not in values:
        values["prompt"] = ActionReadiness("prompt", "ready", "Ready to send message")
    return result([values[action] for action in actions])
