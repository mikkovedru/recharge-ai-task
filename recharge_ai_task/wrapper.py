"""PTY wrapper that auto-continues Codex, Claude and Muse Code after quota resets."""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass

from .i18n import t
from .parser import LimitWatcher, resolve_reset_at
from .pty_backend import StopEvent, forward_stdin, sleep_with_proxy, spawn_pty
from .quota import discover_codex, fetch_quota, looks_like_codex_cli, exhausted_windows, quota_blocked


@dataclass
class WrapperConfig:
    codex_path: str | None = None
    codex_args: list[str] | None = None
    continue_prompt: str = "Continue"
    goal_mode: bool = False
    grace_seconds: int = 60
    enter_presses: int = 1
    key_delay: float = 0.12
    poll_seconds: int = 30
    provider: str = "codex"
    claude_path: str | None = None
    claude_args: list[str] | None = None
    muse_path: str | None = None
    muse_args: list[str] | None = None


def _log(message: str) -> None:
    sys.stderr.write(message + "\n")
    sys.stderr.flush()


def _submit(pty, text: str, enter_presses: int, key_delay: float, *, carriage_return=False) -> None:
    pty.write(text)
    time.sleep(key_delay)
    for _ in range(max(1, enter_presses)):
        pty.write("\r" if carriage_return or sys.platform == "win32" else "\n")
        time.sleep(key_delay)


def _continue_prompt(config: WrapperConfig, first_goal_resume: bool) -> str:
    if config.provider == "codex" and config.goal_mode and first_goal_resume:
        return "/goal resume"
    return config.continue_prompt


def wait_for_quota_recovery(pty, stop, codex, fallback_at, grace_seconds, initial=None, poll_seconds=30):
    """Poll while proxying terminal output, including early resets/refills."""
    interval = max(1, poll_seconds)
    recovered_at = None
    snapshot = initial
    last_error = None
    while not stop.is_set() and pty.isalive():
        try:
            quota = snapshot if snapshot is not None else fetch_quota(codex)
            last_error = None
        except Exception as exc:
            if str(exc) != last_error:
                _log(f"[recharge-ai-task-cli] Quota check unavailable: {exc}; retaining terminal-time fallback.")
            last_error = str(exc)
            if time.time() >= fallback_at:
                return True
            if not sleep_with_proxy(pty, stop, min(fallback_at, time.time() + interval)):
                return False
            snapshot = None
            continue
        now = time.time()
        if quota_blocked(quota):
            recovered_at = None
            due = now + interval
        else:
            if recovered_at is None:
                recovered_at = now
                _log("[recharge-ai-task-cli] Quota is available now; starting the recovery grace period.")
            due = recovered_at + grace_seconds
            if now >= due:
                return True
            due = min(due, now + interval)
        if not sleep_with_proxy(pty, stop, due):
            return False
        snapshot = None
    return False


def wait_for_claude_reset(pty, stop, wake_at, watcher, grace_seconds=0, user_input=None):
    """Observe native recovery/cancellation even when printed in a later read.

    None means Claude owns the wait or the user cancelled it; False means exit.
    """
    settled_at = time.monotonic() + .3
    previous_reset = watcher.reset_at
    while not stop.is_set() and pty.isalive():
        if user_input is not None and user_input.is_set():
            watcher.reset()
            _log("[recharge-ai-task-cli] Manual terminal input cancelled Recharge's pending continuation.")
            return None
        try:
            data = pty.read(4096)
        except EOFError:
            return False
        if data:
            sys.stdout.write(data)
            sys.stdout.flush()
            detected = watcher.feed(data)
            if watcher.native_owned:
                _log("[recharge-ai-task-cli] Claude owns or cancelled automatic continuation; no extra prompt queued.")
                return None
            if detected and detected[0] != previous_reset:
                wake_at = max(time.time(), detected[0]) + grace_seconds
                previous_reset = detected[0]
        if time.time() >= wake_at and time.monotonic() >= settled_at:
            return True
        stop.wait(.05)
    return False


def wait_for_muse_recovery(pty, stop, executable, config, user_input):
    """Require fresh, usable session AND weekly allowance, then keep the grace."""
    from .muse import fetch_muse_quota
    next_check = 0
    limit_observed_at = time.time()
    recovered_at = None
    last_error = None
    while not stop.is_set() and pty.isalive():
        if user_input.is_set():
            _log("[recharge-ai-task-cli] Manual input cancelled Muse continuation.")
            return None
        now = time.monotonic()
        if now >= next_check:
            try:
                quota = fetch_muse_quota(executable, not_before=limit_observed_at)
                last_error = None
            except Exception as exc:
                recovered_at = None
                if str(exc) != last_error:
                    _log(f"[recharge-ai-task-cli] {exc}")
                last_error = str(exc)
            else:
                now = time.monotonic()
                if quota_blocked(quota):
                    recovered_at = None
                elif recovered_at is None:
                    recovered_at = now
                    _log("[recharge-ai-task-cli] Muse allowance is available; starting the recovery grace period.")
            if user_input.is_set():
                return None
            now = time.monotonic()
            if recovered_at is not None and now >= recovered_at + config.grace_seconds:
                return True
            next_check = now + max(1, config.poll_seconds)
            if recovered_at is not None:
                next_check = min(next_check, recovered_at + config.grace_seconds)
        try:
            data = pty.read(4096)
        except EOFError:
            return False
        if data:
            sys.stdout.write(data)
            sys.stdout.flush()
        stop.wait(.05)
    return False


def run_wrapper(config: WrapperConfig) -> int:
    if config.provider == "claude":
        from .claude import discover_claude, ClaudeLimitWatcher
        codex = discover_claude(config.claude_path)
        args = config.claude_args or []
    elif config.provider == "muse":
        from .muse import discover_muse
        codex = discover_muse(config.muse_path)
        args = config.muse_args or []
    elif config.provider == "codex":
        codex = discover_codex(config.codex_path)
        args = config.codex_args or []
    else:
        raise ValueError("Unknown AI provider")
    argv = [codex, *args]
    cmdline = " ".join(argv)

    _log(f"[recharge-ai-task-cli] {t('cli.running')}: {cmdline}")

    rows, cols = 24, 120
    try:
        from shutil import get_terminal_size

        size = get_terminal_size(fallback=(rows, cols))
        rows, cols = size.lines, size.columns
    except Exception:
        pass

    try:
        pty = spawn_pty(argv, (rows, cols))
    except FileNotFoundError:
        _log(f"[recharge-ai-task-cli] {t('cli.not_found')}")
        return 1

    if config.provider == "muse":
        from .muse import MuseLimitWatcher
        watcher = MuseLimitWatcher()
    else:
        watcher = ClaudeLimitWatcher() if config.provider == "claude" else LimitWatcher()
    stop = StopEvent()
    user_input = threading.Event()
    goal_resume_pending = config.goal_mode
    limit_lock = threading.Lock()
    waiting_for_reset = False

    def reader() -> None:
        while not stop.is_set() and pty.isalive():
            try:
                data = pty.read(4096)
            except EOFError:
                break
            if not data:
                continue
            sys.stdout.write(data)
            sys.stdout.flush()
            detected = watcher.feed(data)
            if detected:
                handle_limit(detected)

    def handle_limit(detected: tuple[int, str]) -> None:
        nonlocal goal_resume_pending, waiting_for_reset
        with limit_lock:
            if waiting_for_reset or stop.is_set() or not pty.isalive():
                return
            waiting_for_reset = True

        parsed_reset_at, raw = detected
        user_input.clear()
        if config.provider == "muse":
            _log("[recharge-ai-task-cli] Muse usage limit reached; checking subscription allowance.")
            watcher.reset()
            try:
                ready = wait_for_muse_recovery(pty, stop, codex, config, user_input)
                if ready and not user_input.is_set() and not stop.is_set() and pty.isalive():
                    _submit(pty, config.continue_prompt, config.enter_presses, config.key_delay, carriage_return=True)
                    _log(f"[recharge-ai-task-cli] {t('cli.auto_continue_sent')}")
            finally:
                with limit_lock:
                    waiting_for_reset = False
            return
        quota_reset_at = None
        quota = None
        quota_enabled = config.provider == "codex" and looks_like_codex_cli(codex)
        if quota_enabled:
            try:
                quota = fetch_quota(codex)
                exhausted = exhausted_windows(quota)
                if exhausted:
                    quota_reset_at = max(window.resets_at for window in exhausted)
            except Exception as exc:
                _log(f"[recharge-ai-task-cli] {t('cli.quota_fallback_failed', error=exc)}")

        try:
            wake_at, source = resolve_reset_at(
                parsed_reset_at=parsed_reset_at,
                quota_resets_at=quota_reset_at,
                grace_seconds=config.grace_seconds,
            )
        except RuntimeError as exc:
            _log(f"[recharge-ai-task-cli] {exc}")
            with limit_lock:
                waiting_for_reset = False
            return
        prompt = _continue_prompt(config, goal_resume_pending)
        if config.goal_mode and goal_resume_pending:
            goal_resume_pending = False

        wake_local = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(wake_at))
        _log(
            f"[recharge-ai-task-cli] {t('cli.limit_detected', raw=raw, source=source, prompt=prompt, time=wake_local)}"
        )
        if config.provider != "claude":
            watcher.reset()

        try:
            if config.provider == "claude":
                ready = wait_for_claude_reset(pty, stop, wake_at, watcher, config.grace_seconds, user_input)
                if ready is None:
                    return
            else:
                ready = (wait_for_quota_recovery(pty, stop, codex, wake_at, config.grace_seconds, initial=quota, poll_seconds=config.poll_seconds)
                         if quota_enabled else sleep_with_proxy(pty, stop, wake_at))
            if not ready:
                _log(f"[recharge-ai-task-cli] {t('cli.exited_before_continue')}")
                stop.set()
                return

            if config.provider == "claude":
                watcher.reset()
            _submit(pty, prompt, config.enter_presses, config.key_delay, carriage_return=config.provider == "claude")
            _log(f"[recharge-ai-task-cli] {t('cli.auto_continue_sent')}")
        finally:
            with limit_lock:
                waiting_for_reset = False

    class InputProxy:
        def isalive(self):
            return pty.isalive()

        def write(self, data):
            user_input.set()
            pty.write(data)

    stdin_pty = InputProxy() if config.provider in ("claude", "muse") else pty
    stdin_thread = threading.Thread(target=forward_stdin, args=(stdin_pty, stop), daemon=True)
    reader_thread = threading.Thread(target=reader, daemon=True)

    stdin_thread.start()
    reader_thread.start()

    try:
        while pty.isalive() and not stop.is_set():
            time.sleep(0.2)
    except KeyboardInterrupt:
        stop.set()

    stop.set()
    reader_thread.join(timeout=2)
    stdin_thread.join(timeout=1)

    try:
        return pty.exitstatus or 0
    except Exception:
        return 0
