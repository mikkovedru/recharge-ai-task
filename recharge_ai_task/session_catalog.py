"""Read local Claude Code and Muse Code chat metadata without starting a model."""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import uuid

from .targets import Target, Inventory

_cache = {}


def muse_home():
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))).expanduser() / "muse"


def _title(value):
    return " ".join(value.split())[:160] if isinstance(value, str) else ""


def _timestamp(value):
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        return result if result > 0 else None
    except (ValueError, TypeError, AttributeError):
        return None


def _records(path):
    # Session files can contain gigabytes of tool output. Metadata lives near
    # the start; recent names/status live at the end. Never scan entire logs.
    with path.open("rb") as stream:
        head = stream.read(256 * 1024)
        stream.seek(0, 2)
        size = stream.tell()
        if size > len(head):
            stream.seek(max(len(head), size - 256 * 1024))
            tail = stream.read().split(b"\n", 1)[-1]
        else:
            tail = b""
    for line in (head + b"\n" + tail).splitlines():
        try:
            value = json.loads(line)
        except (ValueError, UnicodeError):
            continue  # Includes a partially written last record.
        if isinstance(value, dict):
            yield value


def read_session(path, provider, home):
    path, home = Path(path), Path(home)
    session_id = path.stem if provider == "claude" else path.parent.name
    try:
        uuid.UUID(session_id)
    except ValueError:
        return None
    stat = path.stat()
    cache_key = (provider, str(home), str(path))
    signature = (stat.st_ino, stat.st_size, stat.st_mtime_ns)
    cached = _cache.get(cache_key)
    if cached and cached[0] == signature:
        return cached[1]
    title = prompt = cwd = ""
    updated = None
    status = "Saved local session"
    for record in _records(path):
        if provider == "claude":
            if record.get("sessionId", session_id) != session_id or record.get("isSidechain"):
                continue
            if isinstance(record.get("cwd"), str):
                cwd = record["cwd"]
            updated = _timestamp(record.get("timestamp")) or updated
            if record.get("type") in ("custom-title", "summary"):
                title = _title(record.get("customTitle") or record.get("summary")) or title
            if record.get("type") == "user" and not record.get("isMeta") and not prompt:
                content = (record.get("message") or {}).get("content")
                if isinstance(content, list):
                    content = " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
                prompt = _title(content)
        else:
            payload = record.get("payload")
            if not isinstance(payload, dict):
                continue
            stream = record.get("stream") or {}
            if stream.get("kind") != "session" or stream.get("id") != session_id:
                continue
            stamp = record.get("recorded_at")
            if type(stamp) is int and 0 < stamp < 253402300800000000:
                updated = max(updated or 0, stamp / 1_000_000)
            if record.get("payload_type") == "runtime.session.metadata":
                metadata = payload.get("record") or {}
                cwd = metadata.get("workspace_root") or cwd
                title = _title(metadata.get("title") or metadata.get("name")) or title
            if record.get("payload_type") in ("session.renamed", "runtime.session.name", "runtime.session.name_assigned"):
                title = _title(payload.get("name") or payload.get("title")) or title
            event = payload.get("event") or {}
            if not prompt:
                prompt = _title(payload.get("prompt") or event.get("prompt"))
    if not cwd:
        return None  # Do not guess project paths by decoding directory names.
    result = Target("session", session_id, title or prompt or session_id,
                    instance=str(home.resolve()), endpoint=str(path.resolve()), cwd=cwd,
                    status=status, task_status="Saved", goal_status="Unavailable",
                    last_active_at=updated, provider=provider, project_name=Path(cwd).name)
    if len(_cache) > 10000:
        _cache.clear()
    _cache[cache_key] = (signature, result)
    return result


def discover_sessions(provider):
    if provider == "claude":
        from .claude import claude_home
        home = claude_home()
        paths = (home / "projects").glob("*/*.jsonl")
    elif provider == "muse":
        home = muse_home()
        paths = (home / "sessions").glob("*/*/*/*/session.jsonl")
    else:
        raise ValueError("Unsupported local session provider")
    result = Inventory()
    for path in paths:
        try:
            if path.is_symlink() or not path.resolve().is_relative_to(home.resolve()):
                continue
            target = read_session(path, provider, home)
            if target:
                result.targets.append(target)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            result.warnings.append(f"{provider.title()} session metadata unavailable: {exc}")
    return result


def validate_session(target):
    path = Path(target.endpoint)
    root = Path(target.instance)
    expected = root / ("projects" if target.provider == "claude" else "sessions")
    if not path.resolve().is_relative_to(expected.resolve()) or path.is_symlink():
        raise ValueError("Session transcript does not belong to its provider profile")
    fresh = read_session(path, target.provider, root)
    if fresh is None or fresh.id != target.id or fresh.cwd != target.cwd:
        raise ValueError("Session identity or project changed; refresh the chat list")
    return fresh


def quota_profile_matches(target):
    """Automatic Code delivery must use the profile whose quota was observed."""
    if target.kind != "session":
        return True
    if target.provider == "claude":
        from .claude import claude_home
        expected = claude_home()
    elif target.provider == "muse":
        expected = muse_home()
    else:
        return True
    return bool(target.instance) and Path(target.instance).resolve() == expected.resolve()
