"""Quota watcher for ChatGPT Codex desktop app (no PTY)."""

from __future__ import annotations

import logging
import sys
import time
from dataclasses import dataclass, field

from .desktop_input import DEFAULT_WINDOW_TITLES
from .targets import Target
from .activity import target_label
from .target_delivery import deliver_targets, recover_target, send_signals
from .goal_control import quota_stopped_targets
from .i18n import t
from .quota import discover_codex, fetch_quota, exhausted_windows, quota_blocked
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


def _poll_interval(used_percent: float, default: int) -> int:
    if used_percent >= 100:
        return min(default, 5)
    if used_percent >= 95:
        return min(default, 10)
    if used_percent >= 80:
        return min(default, 20)
    return default


def _log_status(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    _log.info(message)


def run_desktop_watch(config: WatchConfig, stop: StopEvent | None = None) -> int:
    stop = stop or StopEvent()
    codex = discover_codex(config.codex_path)
    targets = tuple(t for t in config.desktop_targets if any(t.signal_actions(config.goal_mode)))
    if not targets:
        _log_status("Choose signal targets first: recharge-ai-task-cli targets --gui")
        return 1
    state = config.state if config.state is not None else WatchState()
    checked_at = None
    available = None

    def observation(phase, next_check_at=None):
        pending = [t for t in targets if t.key not in state.delivered] if state.pending else []
        actions = [t.signal_actions(config.goal_mode) for t in pending]
        return {"phase": phase, "checked_at": checked_at,
                "next_check_at": next_check_at, "quota_available": available,
                "recovered_at": state.recovered_at,
                "recovery_at": state.wake_at if state.pending and available else None,
                "expected_reset_at": state.expected_reset_at,
                "pending_recipients": len(pending),
                "pending_messages": sum(prompt for prompt, _goal in actions),
                "pending_goals": sum(goal for _prompt, goal in actions)}

    def wait(seconds, phase):
        # Counts are estimates: live statuses and allowances are checked at send.
        state.progress = observation(phase, time.time() + seconds)
        stop.wait(seconds)

    _log_status(t("watch.started"))

    while not stop.is_set():
        state.progress = observation("checking_quota")
        try:
            quota = fetch_quota(codex)
        except Exception as exc:
            available = None
            _log_status(t("cli.quota_fallback_failed", error=exc))
            wait(60, "quota_unavailable")
            continue

        checked_at = time.time()

        exhausted = exhausted_windows(quota)
        available = not quota_blocked(quota)
        used = max(quota.primary.used_percent, quota.secondary.used_percent if quota.secondary else 0)

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
                state.pending = True
            if state.pending:
                state.waiting_for_quota = True
                state.recovered_at = None
                state.wake_at = 0
            _log_status("Quota is unavailable; polling for recovery, including early resets and added credits.")
            wait(max(1, min(15, _poll_interval(used, config.poll_seconds))), "waiting_quota")
            continue

        state.repeated_block.clear()
        state.repeated_block_count = 0
        if state.waiting_for_quota:
            state.waiting_for_quota = False
            state.recovered_at = checked_at
            state.wake_at = checked_at + config.grace_seconds
            _log_status("Quota is available now; the recovery grace period starts from this check.")

        if not state.startup_checked and not state.pending:
            state.startup_checked = True
            goal_targets = [t for t in targets if t.signal_actions(config.goal_mode)[1]]
            if goal_targets:
                candidates, errors = quota_stopped_targets(goal_targets, stop=stop)
                state.startup_checked = not errors
                for error in errors:
                    _log_status(error)
                if candidates:
                    state.delivered = {target.key for target in targets} - candidates
                    state.pending = True
                    state.recovered_at = checked_at
                    state.wake_at = checked_at + config.grace_seconds
                    _log_status("Quota is available; recovering selected quota-stopped goals after the grace period.")

        if not state.pending:
            _log_status(t("watch.polling", percent=used))
            wait(_poll_interval(used, config.poll_seconds), "monitoring")
            continue

        remaining = state.wake_at - time.time()
        if remaining > 0:
            wait(min(15, remaining), "grace_period")
            continue

        state.progress = observation("delivering")
        for target in targets:
            if stop.is_set():
                break
            if target.key in state.delivered:
                continue
            if target.send_goal is not None or target.send_prompt is not None:
                result = send_signals([target], config.continue_prompt,
                    enter_presses=config.enter_presses, key_delay=config.key_delay)[0]
            elif config.goal_mode:
                result = recover_target(target, config.continue_prompt,
                    enter_presses=config.enter_presses, key_delay=config.key_delay)
            else:
                result = deliver_targets([target], config.continue_prompt,
                    enter_presses=config.enter_presses, key_delay=config.key_delay)[0]
            if result.success or not result.retryable:
                state.delivered.add(target.key)
            _log_status(f"{target_label(target)} [{target.id}]: {result.detail}")
            state.progress = observation("delivering")

        state.pending = any(target.key not in state.delivered for target in targets)
        wait(30, "retry_pending" if state.pending else "monitoring")

    return 0
