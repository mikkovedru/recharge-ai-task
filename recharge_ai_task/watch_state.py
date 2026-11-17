"""Atomic recovery checkpoints scoped to provider profiles and targets."""
import hashlib
import json
import os
import tempfile
from dataclasses import fields
from copy import deepcopy

from .config import config_dir


def state_path(config):
    identity = [config.codex_path, sorted({t.instance for t in config.targets()})]
    providers = {t.provider for t in config.targets()}
    if providers != {"codex"}:
        from .claude import claude_home
        from .session_catalog import muse_home
        profiles = {"claude": str(claude_home().resolve()), "muse": str(muse_home().resolve())}
        identity = [sorted({(t.provider, t.instance or profiles.get(t.provider, "")) for t in config.targets()}),
                    [(p, profiles.get(p), getattr(config, p + "_path")) for p in sorted(providers)]]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:20]
    return config_dir() / f"watch-state-{key}.json"


def to_dict(state):
    data = {f.name: getattr(state, f.name) for f in fields(state) if f.name != "progress"}
    data["delivered"] = sorted(state.delivered)
    data["seen_resets"] = sorted(state.seen_resets)[-32:]
    data["repeated_block"] = sorted(state.repeated_block)
    return deepcopy(data)


def save(path, state):
    data = to_dict(state)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def from_dict(data):
    from .watch import WatchState
    data = {f.name: data[f.name] for f in fields(WatchState) if f.name in data and f.name != "progress"}
    data["delivered"] = set(data.get("delivered", []))
    data["seen_resets"] = {tuple(row) for row in data.get("seen_resets", [])}
    data["repeated_block"] = {tuple(row) for row in data.get("repeated_block", [])}
    state = WatchState(**data)
    if state.in_flight:
        from .activity import record
        from .targets import Target
        identity = json.loads(state.in_flight[0])
        target = Target(identity[-3], identity[-1], state.in_flight[1], instance=identity[-2],
                        provider=identity[0] if len(identity) == 4 else "codex",
                        project_name=state.in_flight[2] if len(state.in_flight) > 2 else "")
        record(target, "automatic", "signals", "uncertain",
               "The previous worker stopped during delivery. Check this chat before sending again manually.")
        state.delivered.add(state.in_flight[0])
        state.in_flight = None
    return state


def load(path):
    from .watch import WatchState
    if not path.exists():
        return WatchState()
    try:
        return from_dict(json.loads(path.read_text()))
    except (ValueError, TypeError, KeyError) as exc:
        raise RuntimeError(f"Cannot read recovery checkpoint {path.name}: {exc}") from exc
