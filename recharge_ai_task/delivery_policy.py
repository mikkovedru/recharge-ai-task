"""Per-recipient policies and durable, process-safe continuation allowances."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import os
import sys
import time

from .config import config_dir
from .codex_ipc import DeliveryUncertain


class LimitReached(RuntimeError):
    pass


def effective_limit(target, action, config):
    override = getattr(target, action + "_limit")
    value = getattr(config, action + "_limit") if override is None else override
    if value is None or value == -1:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"Invalid {action} limit")
    return value


def effective_message(target, default):
    return default if target.custom_prompt is None else target.custom_prompt


@dataclass(frozen=True)
class Usage:
    used: int = 0
    uncertain: int = 0

    def describe(self, limit):
        remaining = "unlimited" if limit is None else f"{max(0, limit - self.used)} left of {limit}"
        return f"{self.used} used · {remaining}" + (f" · {self.uncertain} unconfirmed" if self.uncertain else "")


class UsageLedger:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else config_dir() / "delivery.sqlite"
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, target TEXT NOT NULL, action TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', created REAL NOT NULL, owner_pid INTEGER)")
            if "owner_pid" not in {row[1] for row in db.execute("PRAGMA table_info(attempts)")}:
                db.execute("ALTER TABLE attempts ADD COLUMN owner_pid INTEGER")
            db.execute("CREATE INDEX IF NOT EXISTS attempts_target ON attempts(target,action,state)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=2)
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _usage(db, key, action):
        used, uncertain = db.execute("SELECT COUNT(*), COALESCE(SUM(state IN ('pending','uncertain')),0) FROM attempts WHERE target=? AND action=? AND state!='failed'", (key, action)).fetchone()
        return Usage(used, uncertain)

    def usage(self, key, action):
        with self.connection() as db:
            return self._usage(db, key, action)

    def snapshot(self):
        with self.connection() as db:
            return {(key, action): Usage(used, uncertain) for key, action, used, uncertain in db.execute(
                "SELECT target,action,COUNT(*),SUM(state IN ('pending','uncertain')) FROM attempts WHERE state!='failed' GROUP BY target,action")}

    def reserve(self, key, action, limit):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if limit is not None and self._usage(db, key, action).used >= limit:
                raise LimitReached(f"{action.title()} limit reached")
            return db.execute("INSERT INTO attempts(target,action,state,created,owner_pid) VALUES (?,?, 'pending', ?,?)", (key, action, time.time(), os.getpid())).lastrowid

    def finish(self, attempt, state, detail=""):
        with self.connection() as db:
            db.execute("UPDATE attempts SET state=?,detail=? WHERE id=?", (state, detail, attempt))

    def reset(self, keys):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            for key in keys:
                owners = db.execute("SELECT owner_pid FROM attempts WHERE target=? AND state='pending'", (key,)).fetchall()
                if any(self._owner_alive(pid) for (pid,) in owners):
                    raise ValueError("A delivery is still in progress. Wait for it to finish before resetting counts.")
                db.execute("DELETE FROM attempts WHERE target=?", (key,))

    @staticmethod
    def _owner_alive(pid):
        if not pid:
            return False
        if sys.platform == "win32":
            import ctypes
            kernel = ctypes.windll.kernel32
            kernel.OpenProcess.restype = ctypes.c_void_p
            handle = kernel.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
            finally:
                kernel.CloseHandle(ctypes.c_void_p(handle))
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True


class ActionBudget:
    def __init__(self, ledger, target, config):
        self.ledger, self.target, self.config = ledger, target, config

    def limit(self, action):
        return effective_limit(self.target, action, self.config)

    def available(self, action):
        usage = self.ledger.usage(self.target.key, action)
        limit = self.limit(action)
        return limit is None or usage.used < limit

    def perform(self, action, operation):
        attempt = self.ledger.reserve(self.target.key, action, self.limit(action))
        try:
            result = operation()
        except DeliveryUncertain as exc:
            self._finish(attempt, "uncertain", str(exc))
            raise
        except BaseException as exc:
            # A hard process stop leaves the reserved slot pending. A normal
            # definitive rejection releases it; uncertain outcomes keep it used.
            if isinstance(exc, Exception):
                self._finish(attempt, "failed", str(exc))
            raise
        if hasattr(result, "success") and (not result.success or result.skipped):
            state = "uncertain" if not result.success and not result.retryable else "failed"
            self._finish(attempt, state, result.detail)
        else:
            self._finish(attempt, "sent")
        return result

    def _finish(self, attempt, state, detail=""):
        try:
            self.ledger.finish(attempt, state, detail)
        except Exception as exc:
            raise DeliveryUncertain("Delivery outcome could not be saved; allowance remains reserved. Check this chat before retrying.") from exc


def status_advice(target, *, manual=False):
    """Explain cached status; delivery rechecks the native state before Goal."""
    prompt, goal = target.signal_actions()
    if not goal:
        return "Message delivery attempted regardless of task/goal status" if prompt else "No actions selected"
    if target.kind != "thread":
        return "Goal requires a chat ID"
    if target.goal_status in {"Blocked", "Budget limited", "Complete", "No goal"}:
        return f"Goal skipped: {target.goal_status.lower()}" + ("; message still selected" if prompt else "")
    if not manual and target.goal_status == "Paused":
        return "Automatic Goal skips intentional pauses" + ("; message still selected" if prompt else "")
    if not manual and (target.task_status == "Running" or target.task_status.startswith("Waiting for")):
        return "Automatic Goal skips running/waiting tasks" + ("; message still selected" if prompt else "")
    if target.goal_status == "Active":
        return "Goal already active; no activation needed" + ("; message will be sent after verification" if prompt else "")
    return "Goal state verified live before activation" + (" → then send message" if prompt else "")


def planned_actions(target, config, usage, message, *, manual=False):
    """Readable preview from the latest snapshot; native delivery rechecks it."""
    prompt, goal = target.signal_actions()
    pl, gl = effective_limit(target, "prompt", config), effective_limit(target, "goal", config)
    if goal and gl is not None and usage.get((target.key, "goal"), Usage()).used >= gl:
        return "Withheld: Goal limit reached"
    message_blocked = prompt and pl is not None and usage.get((target.key, "prompt"), Usage()).used >= pl
    prompt = prompt and not message_blocked
    if prompt and not message.strip():
        return "Withheld: message is empty"
    reason = ""
    if goal:
        if target.goal_status in {"Blocked", "Budget limited", "Complete", "No goal"}:
            reason = target.goal_status.lower()
        elif not manual and target.goal_status == "Paused":
            reason = "paused"
        elif not manual and (target.task_status == "Running" or target.task_status.startswith("Waiting for")):
            reason = "task running/waiting"
        elif target.goal_status == "Active":
            reason = "already active"
    if goal and not reason:
        plan = "Verify/resume Goal" + (" → Message" if prompt else "")
    elif goal:
        plan = f"Goal: {reason}" + (" → Message" if prompt else " (no activation)")
    else:
        plan = "Message" if prompt else "No delivery"
    return plan + ("; message limit reached" if message_blocked else "")


def invalid_messages(targets, default, config):
    """Empty drafts only block actions that still have a message allowance."""
    candidates = [t for t in targets if t.signal_actions()[0] and not effective_message(t, default).strip()]
    if not candidates:
        return []
    usage = UsageLedger().snapshot()
    invalid = []
    for target in candidates:
        pl, gl = effective_limit(target, "prompt", config), effective_limit(target, "goal", config)
        if pl is not None and usage.get((target.key, "prompt"), Usage()).used >= pl:
            continue
        if target.signal_actions()[1] and gl is not None and usage.get((target.key, "goal"), Usage()).used >= gl:
            continue
        invalid.append(target)
    return invalid
