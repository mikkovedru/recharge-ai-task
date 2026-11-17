"""Independent provider quota watches and selected-chat recovery."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field, replace

from .desktop_input import DEFAULT_WINDOW_TITLES
from .targets import Target
from .activity import target_label
from .target_delivery import DeliveryResult, deliver_targets, recover_target, send_signals
from .goal_control import quota_stopped_targets
from .i18n import t
from .quota import discover_codex, fetch_quota, exhausted_windows, quota_blocked, quota_to_snapshot, quota_windows
from .pty_backend import StopEvent

_log = logging.getLogger("recharge-ai-task.watch")


@dataclass
class WatchState:
    """Delivery accounting retained when an active watch applies new settings."""
    startup_checked: bool = False
    delivered: set[str] = field(default_factory=set)
    seen_resets: set[tuple[int, int]] = field(default_factory=set)
    pending: bool = False
    wake_at: float = 0
    progress: dict = field(default_factory=dict)
    waiting_for_quota: bool = False
    recovered_at: float | None = None
    expected_reset_at: float | None = None
    repeated_block: set[tuple[int, int]] = field(default_factory=set)
    repeated_block_count: int = 0
    previous_windows: dict = field(default_factory=dict)
    near_limit_windows: dict = field(default_factory=dict)
    completed_actions: dict = field(default_factory=dict)
    in_flight: tuple | None = None
    provider_states: dict = field(default_factory=dict)
    awaiting_initial_block: bool = False


@dataclass
class WatchConfig:
    codex_path: str | None = None
    continue_prompt: str = "Continue"
    goal_mode: bool = False
    grace_seconds: int = 60
    enter_presses: int = 1
    key_delay: float = 0.12
    poll_seconds: int = 30
    desktop_window_titles: tuple[str, ...] = DEFAULT_WINDOW_TITLES
    desktop_targets: tuple[Target, ...] = ()
    state: WatchState | None = None
    checkpoint: object = None
    provider: str = "codex"
    muse_path: str | None = None


def _log_status(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    _log.info(message)


def run_desktop_watch(config: WatchConfig, stop: StopEvent | None = None) -> int:
    stop = stop or StopEvent()
    def status(message):
        _log_status(f"[{config.provider.title()}] {message}")
    if config.provider == "all":
        return _run_provider_watches(config, stop)
    if config.provider in ("gemini", "antigravity", "opencode"):
        if config.provider == "opencode":
            from .opencode import LIMITATION
        else:
            from .google_ai import limitation
            LIMITATION = limitation(config.provider)
        status(LIMITATION)
        return 1
    if config.provider not in ("codex", "claude", "muse"):
        raise ValueError("Unknown AI provider")
    codex = None
    targets = tuple(t for t in config.desktop_targets if t.provider == config.provider and any(t.signal_actions(config.goal_mode)))
    if not targets:
        status("Choose signal targets first: recharge-ai-task targets --gui")
        return 1
    state = config.state if config.state is not None else WatchState()
    checked_at = None
    available = None
    last_quota = None
    quota_error = ""
    interval = max(1, config.poll_seconds)

    def remaining_target(target):
        done = state.completed_actions.get(target.key, [])
        prompt, goal = target.signal_actions(config.goal_mode)
        return replace(target, send_prompt=prompt and "prompt" not in done,
                       send_goal=goal and "goal" not in done)

    def checkpoint():
        if config.checkpoint:
            config.checkpoint(state)

    def counts(selected):
        from .config import AppConfig
        from .delivery_policy import UsageLedger, Usage, effective_limit
        settings, usage = AppConfig.load(), UsageLedger().snapshot()
        messages = goals = recipients = 0
        for target in selected:
            prompt, goal = target.signal_actions(config.goal_mode)
            def allowed(action):
                limit = effective_limit(target, action, settings)
                return limit is None or usage.get((target.key, action), Usage()).used < limit
            prompt = prompt and allowed("prompt")
            goal_available = not goal or allowed("goal")
            goal = goal and goal_available
            recipients += bool(prompt or goal)
            messages += bool(prompt)
            goals += bool(goal)
        return recipients, messages, goals

    def observation(phase, next_check_at=None):
        pending_cycle = state.pending and not state.awaiting_initial_block
        pending = [remaining_target(t) for t in targets if t.key not in state.delivered] if pending_cycle else []
        error = ""
        try:
            recipients, messages, goals = counts(pending)
            selected_recipients, selected_messages, selected_goals = counts(targets)
        except Exception as exc:
            recipients = messages = goals = selected_recipients = selected_messages = selected_goals = 0
            error = f"Cannot read delivery allowances: {exc}"
        return {"phase": phase, "updated_at": time.time(), "checked_at": checked_at,
                "next_check_at": next_check_at, "quota_available": available,
                "recovered_at": state.recovered_at,
                "recovery_at": state.wake_at if pending_cycle and available else None,
                "expected_reset_at": state.expected_reset_at, "grace_seconds": config.grace_seconds,
                "pending_cycle": pending_cycle, "pending_recipients": recipients,
                "pending_messages": messages, "pending_goals": goals,
                "selected_recipients": selected_recipients, "selected_messages": selected_messages,
                "selected_goals": selected_goals, "count_error": error, "poll_seconds": interval,
                "quota_snapshot": quota_to_snapshot(last_quota) if last_quota is not None else None, "quota_error": quota_error}

    def wait(seconds, phase):
        state.progress = observation(phase, time.time() + seconds)
        checkpoint()
        stop.wait(seconds)

    status(t("watch.started"))

    while not stop.is_set():
        state.progress = observation("checking_quota")
        try:
            if config.provider == "claude":
                from .claude import fetch_claude_quota
                quota = fetch_claude_quota()
            elif config.provider == "muse":
                from .muse import fetch_muse_quota
                quota = fetch_muse_quota(config.muse_path)
            else:
                if codex is None:
                    codex = discover_codex(config.codex_path)
                quota = fetch_quota(codex)
        except Exception as exc:
            available = None
            quota_error = str(exc)
            status(t("cli.quota_fallback_failed", error=exc))
            wait(interval, "quota_unavailable")
            continue

        last_quota = quota
        quota_error = ""
        checked_at = time.time()

        exhausted = exhausted_windows(quota)
        available = not quota_blocked(quota)
        windows = quota_windows(quota)
        used = max(w.used_percent for w in windows)
        if state.awaiting_initial_block:
            if available:
                # Automatic startup must not resume a saved cycle or a stopped
                # Goal if quota recovered before this worker's first check.
                wait(interval, "monitoring")
                continue
            state.awaiting_initial_block = False
            state.startup_checked = True
            state.pending = False
            state.delivered.clear()
            state.completed_actions.clear()
            state.seen_resets.clear()
        missed_keys = set()
        near_windows = {}
        for window in windows:
            duration = window.label or str(window.window_duration_mins)
            previous = state.previous_windows.get(duration)
            near = state.near_limit_windows.get(duration, [window.resets_at, 0])
            if window.used_percent >= 95:
                near_windows[duration] = [window.resets_at, near[1] + 1 if near[0] == window.resets_at else 1]
            if previous and previous[0] >= 95 and window.used_percent < 95:
                rolled = window.resets_at > previous[1] and previous[1] <= checked_at
                refilled = previous[0] - window.used_percent >= 5
                key = (window.window_duration_mins, previous[1])
                # One stale near-limit frame must not replay a completed refill.
                if (rolled or refilled) and (key not in state.seen_resets or near[1] >= 2):
                    missed_keys.add(key)
        state.previous_windows = {w.label or str(w.window_duration_mins): [w.used_percent, w.resets_at] for w in windows}
        state.near_limit_windows = near_windows
        if available and missed_keys and not state.pending:
            state.seen_resets.update(missed_keys)
            state.pending = True
            state.delivered.clear()
            state.completed_actions.clear()
            state.waiting_for_quota = True
            status("Quota recovered between polls near the limit; scheduling selected signals.")
        if not state.pending:
            future = [w.resets_at for w in windows if w.resets_at > checked_at]
            state.expected_reset_at = min(future, default=None)

        if not available:
            state.startup_checked = True
            # A flag-only limit is a real block even before percentages reach
            # 100. Reset-credit inventory alone never counts as availability.
            keys = {(w.window_duration_mins, w.resets_at) for w in exhausted}
            if not keys:
                keys = {(-1, quota.primary.resets_at)}
            state.expected_reset_at = max((w.resets_at for w in exhausted), default=None)
            if keys == state.repeated_block:
                state.repeated_block_count += 1
            else:
                state.repeated_block, state.repeated_block_count = keys, 1
            # A second exhaustion after an early refill may keep the same reset
            # ID. Require two current-window observations so one stale frame
            # cannot replay an already completed recovery.
            repeated_current = (not state.pending and state.recovered_at is not None
                and any(reset > checked_at for _duration, reset in keys)
                and state.repeated_block_count >= 2)
            if keys - state.seen_resets or repeated_current:
                state.seen_resets.update(keys)
                state.delivered.clear()
                state.completed_actions.clear()
                state.pending = True
            if state.pending:
                state.waiting_for_quota = True
                state.recovered_at = None
                state.wake_at = 0
            status("Quota is unavailable; polling for recovery, including early resets and added credits.")
            wait(interval, "waiting_quota")
            continue

        state.repeated_block.clear()
        state.repeated_block_count = 0
        if state.waiting_for_quota:
            state.waiting_for_quota = False
            state.recovered_at = checked_at
            state.wake_at = checked_at + config.grace_seconds
            status("Quota is available now; the recovery grace period starts from this check.")

        if not state.startup_checked and not state.pending:
            state.startup_checked = True
            goal_targets = [t for t in targets if t.signal_actions(config.goal_mode)[1]]
            if goal_targets:
                candidates, errors = quota_stopped_targets(goal_targets, stop=stop)
                state.startup_checked = not errors
                for error in errors:
                    status(error)
                if candidates:
                    state.delivered = {target.key for target in targets} - candidates
                    state.pending = True
                    state.recovered_at = checked_at
                    state.wake_at = checked_at + config.grace_seconds
                    status("Quota is available; recovering selected quota-stopped goals after the grace period.")

        if not state.pending:
            status(t("watch.polling", percent=max(0, min(100, 100-used))))
            wait(interval, "monitoring")
            continue

        remaining = state.wake_at - time.time()
        if remaining > 0:
            wait(min(interval, remaining), "grace_period")
            continue

        state.progress = observation("delivering")
        for target in targets:
            if stop.is_set():
                break
            if target.key in state.delivered:
                continue
            state.in_flight = (target.key, target.title, target.project_name)
            checkpoint()
            try:
                from .session_catalog import quota_profile_matches
                if not quota_profile_matches(target):
                    from .activity import record
                    detail = "This saved chat belongs to another provider profile; its quota was not checked. Restore that profile or choose a currently discovered chat."
                    record(target, "automatic", "signals", "failed", detail)
                    result = DeliveryResult(target, False, detail, retryable=False)
                elif target.send_goal is not None or target.send_prompt is not None:
                    result = send_signals([remaining_target(target)], config.continue_prompt,
                        enter_presses=config.enter_presses, key_delay=config.key_delay)[0]
                elif config.goal_mode and config.provider == "codex":
                    result = recover_target(target, config.continue_prompt,
                        enter_presses=config.enter_presses, key_delay=config.key_delay)
                else:
                    result = deliver_targets([target], config.continue_prompt,
                        enter_presses=config.enter_presses, key_delay=config.key_delay)[0]
            except Exception as exc:
                from .activity import record
                record(target, "automatic", "signals", "failed", str(exc))
                result = DeliveryResult(target, False, str(exc))
            completed = set(state.completed_actions.get(target.key, [])) | set(result.completed_actions)
            state.completed_actions[target.key] = sorted(completed)
            if result.success or not result.retryable:
                state.delivered.add(target.key)
            state.in_flight = None
            checkpoint()
            status(f"{target_label(target)} [{target.id}]: {result.detail}")
            state.progress = observation("delivering")

        state.pending = any(target.key not in state.delivered for target in targets)
        if not state.pending:
            state.expected_reset_at = min((w.resets_at for w in windows if w.resets_at > checked_at), default=None)
        wait(interval, "retry_pending" if state.pending else "monitoring")

    return 0


def _run_provider_watches(config, stop):
    """Keep quota cycles, failures and restart accounting independent per provider."""
    import threading
    from . import watch_state
    providers = sorted({t.provider for t in config.desktop_targets})
    if not providers:
        _log_status("Choose signal targets first: recharge-ai-task targets --gui")
        return 1
    # Preserve legacy single-provider checkpoint contents when upgrading.
    state = config.state if config.state is not None else WatchState()
    if len(providers) == 1 and not state.provider_states:
        return run_desktop_watch(replace(config, provider=providers[0], state=state), stop)
    lock = threading.RLock()
    children, events, threads, errors = {}, {}, [], {}

    def publish():
        observations = {p: dict(child.progress) for p, child in children.items()}
        rows = list(observations.values())
        phases = [row.get("phase", "checking_quota") for row in rows]
        priority = ("delivering", "grace_period", "retry_pending", "waiting_quota", "quota_unavailable", "checking_quota", "monitoring")
        progress = {"providers": observations, "phase": next((p for p in priority if p in phases), "checking_quota"),
                    "updated_at": time.time(), "grace_seconds": config.grace_seconds,
                    "quota_available": all(row.get("quota_available") is True for row in rows),
                    "pending_cycle": any(row.get("pending_cycle") for row in rows),
                    "count_error": "; ".join(str(row["count_error"]) for row in rows if row.get("count_error"))}
        for field in ("pending_recipients", "pending_messages", "pending_goals", "selected_recipients", "selected_messages", "selected_goals"):
            progress[field] = sum(row.get(field, 0) for row in rows)
        for field in ("next_check_at", "recovery_at", "expected_reset_at", "checked_at"):
            progress[field] = min((row[field] for row in rows if isinstance(row.get(field), (int, float))), default=None)
        state.progress = progress

    def checkpoint(provider, child):
        with lock:
            state.provider_states = {**state.provider_states, provider: watch_state.to_dict(child)}
            publish()
            if config.checkpoint:
                config.checkpoint(state)

    for provider in providers:
        saved = state.provider_states.get(provider)
        children[provider] = watch_state.from_dict(saved) if saved else WatchState()
        if state.awaiting_initial_block and not saved:
            children[provider].awaiting_initial_block = True
        events[provider] = StopEvent()
    def worker(provider):
        try:
            child_config = replace(config, provider=provider, state=children[provider],
                desktop_targets=tuple(t for t in config.desktop_targets if t.provider == provider),
                checkpoint=lambda child: checkpoint(provider, child))
            code = run_desktop_watch(child_config, events[provider])
            if code:
                raise RuntimeError(f"Worker exited with code {code}")
        except Exception as exc:
            with lock:
                errors[provider] = str(exc)
                children[provider].progress = {"phase": "quota_unavailable", "quota_error": str(exc), "updated_at": time.time()}
                publish()
            _log.exception("%s watch failed", provider)
    for provider in providers:
        thread = threading.Thread(target=worker, args=(provider,), daemon=True)
        threads.append(thread)
        thread.start()
    try:
        while not stop.is_set() and any(thread.is_alive() for thread in threads):
            if stop.wait_woken(.25):
                for event in events.values():
                    event.wake()
            with lock:
                publish()
    finally:
        for event in events.values():
            event.set()
        for thread in threads:
            thread.join()
        with lock:
            publish()
    return 1 if errors else 0
