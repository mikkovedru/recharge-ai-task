"""Shared, bounded delivery history for tray, CLI and dashboard processes."""
import logging
import sqlite3
import time

from .config import config_dir

_log = logging.getLogger("recharge-ai-task.activity")


class ActivityLog:
    def __init__(self):
        self.path = config_dir() / "delivery.sqlite"
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT, created REAL NOT NULL,
                title TEXT NOT NULL, source TEXT NOT NULL, action TEXT NOT NULL,
                status TEXT NOT NULL, detail TEXT NOT NULL, message TEXT NOT NULL,
                project_name TEXT NOT NULL DEFAULT '')""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(activity)")}
            if "provider" not in columns:
                try:
                    db.execute("ALTER TABLE activity ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    if "provider" not in {row[1] for row in db.execute("PRAGMA table_info(activity)")}:
                        raise
            if "project_name" not in columns:
                try:
                    db.execute("ALTER TABLE activity ADD COLUMN project_name TEXT NOT NULL DEFAULT ''")
                except sqlite3.OperationalError:
                    if "project_name" not in {row[1] for row in db.execute("PRAGMA table_info(activity)")}:
                        raise

    def record(self, target, source, action, status, detail="", message=""):
        with sqlite3.connect(self.path, timeout=2) as db:
            db.execute("INSERT INTO activity(created,title,source,action,status,detail,message,project_name,provider) VALUES (?,?,?,?,?,?,?,?,?)",
                       (time.time(), target.title, source, action, status, detail[:4000], message[:16000], target.project_name or "", target.provider))
            db.execute("DELETE FROM activity WHERE id <= (SELECT MAX(id)-1000 FROM activity)")

    def read(self, after=0, limit=200):
        with sqlite3.connect(self.path, timeout=2) as db:
            db.row_factory = sqlite3.Row
            if not after:
                rows = db.execute("SELECT * FROM (SELECT * FROM activity ORDER BY id DESC LIMIT ?) ORDER BY id", (limit,))
            else:
                rows = db.execute("SELECT * FROM activity WHERE id>? ORDER BY id LIMIT ?", (after, limit))
            return [dict(row) for row in rows]


def record(target, source, action, status, detail="", message=""):
    # Logging trouble must not replace the actual delivery result.
    try:
        ActivityLog().record(target, source, action, status, detail, message)
    except Exception:
        _log.exception("Could not record delivery activity")


def target_label(target):
    provider = {"claude": "Claude · ", "muse": "Muse Code · "}.get(target.provider, "")
    return f"{provider}{target.title} [Project: {target.project_name or 'not available'}]"


def display_event(event):
    action = {"prompt": "Message", "goal": "Goal", "signals": "Signals"}.get(event["action"], event["action"])
    status = event["status"]
    project = event.get("project_name") or "not available"
    provider = {"codex": "Codex", "claude": "Claude", "muse": "Muse", "gemini": "Gemini", "antigravity": "Antigravity", "opencode": "OpenCode"}.get(event.get("provider"), "Provider unknown")
    text = f"[{provider}] {event['source'].title()} · {event['title']} [Project: {project}] · {action}: {status}"
    if event["detail"]:
        text += " — " + event["detail"]
    if event["message"]:
        text += "\nMessage text: " + event["message"]
    level = "error" if status in {"failed", "uncertain"} else "warning" if status == "skipped" else "success" if status in {"accepted", "verified"} else "normal"
    return text, level
