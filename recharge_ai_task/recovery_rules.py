"""Explicit exclusions for continuation; new nonempty statuses default to allow."""
GOAL_ERROR_STATUSES = {"error", "systemError"}
GOAL_PROTECTED = {"blocked", "budgetLimited", "budget_limited", "complete"}


def valid_status(value):
    return isinstance(value, str) and bool(value.strip())


def goal_allowed(status, *, manual=False):
    return valid_status(status) and status not in GOAL_PROTECTED and (manual or status != "paused")


def task_allowed(status, *, manual=False):
    return valid_status(status) and (manual or status != "active")


def activation_verified(status):
    # Native UI acknowledgement and identity checks remain required. A newly
    # introduced backend status does not invalidate that acknowledgement.
    stopped = {"paused", "blocked", "usageLimited", "usage_limited", "budgetLimited", "budget_limited"}
    return valid_status(status) and status not in stopped
