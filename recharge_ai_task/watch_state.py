"""Atomic recovery checkpoints scoped to provider profiles and recipients."""
import hashlib
import json
import os
import tempfile
from dataclasses import fields

from .config import config_dir


def state_path(config):
    identity = [config.codex_path, sorted({t.instance for t in config.targets()})]
    if config.provider == "claude":
        from .claude import claude_home
        identity = [config.provider, str(claude_home().resolve()), identity[1]]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
    return config_dir() / f"watch-state-{key}.json"


def save(path, state):
    data = {f.name: getattr(state, f.name) for f in fields(state) if f.name != "progress"}
    data["delivered"] = sorted(state.delivered)
    data["seen_resets"] = sorted(state.seen_resets)[-32:]
    data["repeated_block"] = sorted(state.repeated_block)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load(path):
    from .watch import WatchState
    if not path.exists():
        return WatchState()
    try:
        data = json.loads(path.read_text())
        data = {f.name: data[f.name] for f in fields(WatchState) if f.name in data and f.name != "progress"}
        data["delivered"] = set(data.get("delivered", []))
        data["seen_resets"] = {tuple(row) for row in data.get("seen_resets", [])}
        data["repeated_block"] = {tuple(row) for row in data.get("repeated_block", [])}
        state = WatchState(**data)
        if state.in_flight:
            # A crash can occur after remote acceptance and before checkpointing.
            # Keep that recipient uncertain instead of replaying unlimited actions.
            from .activity import record
            from .targets import Target
            record(Target("thread", "", state.in_flight[1], project_name=state.in_flight[2] if len(state.in_flight)>2 else ""), "automatic", "signals", "uncertain",
                   "The previous worker stopped during delivery. Check this chat before sending again manually.")
            state.delivered.add(state.in_flight[0])
            state.in_flight = None
        return state
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"Cannot read recovery checkpoint {path.name}: {exc}") from exc
