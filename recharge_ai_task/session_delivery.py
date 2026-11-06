"""Continue exact saved CLI chats and verify native prompt acceptance."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

import psutil

from .codex_ipc import DeliveryUncertain
from .config import AppConfig, config_dir
from .session_catalog import validate_session

_lock = threading.RLock()
_jobs = {}


def active_session(target):
    with _lock:
        process = _jobs.get(target.key)
        if process is not None and process.poll() is None:
            return True
    owner = psutil.Process().username()
    for process in psutil.process_iter(["name"]):
        name = (process.info.get("name") or "").lower()
        if not name.startswith("claude" if target.provider == "claude" else "muse"):
            continue
        try:
            if process.username() != owner:
                continue
            args = process.cmdline()
            if any(arg in ("--version", "--help", "usage", "schema", "auth") for arg in args[1:]):
                continue
            ids = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg in ("--resume", "-r", "--session-id", "resume")]
            if target.id in ids:
                return True
            if not ids and Path(process.cwd()).resolve() == Path(target.cwd).resolve():
                return True  # An interactive owner with an unknown chat is unsafe to duplicate.
        except psutil.NoSuchProcess:
            continue
        except (psutil.AccessDenied, OSError):
            raise RuntimeError("Cannot verify an existing provider process; open its terminal before continuing")
    return False


def session_command(target, *, message=None):
    config = AppConfig.load()
    if target.provider == "claude":
        from .claude import discover_claude
        executable = discover_claude(config.claude_path)
        args = [executable, "--resume", target.id]
        if message is not None:
            args += ["--print", "--verbose", "--output-format", "stream-json", message]
        env = {**os.environ, "CLAUDE_CONFIG_DIR": target.instance}
    elif target.provider == "muse":
        from .muse import discover_muse
        executable = discover_muse(config.muse_path)
        args = ([executable, "resume", target.id] if message is None else
                [executable, "exec", "--session-id", target.id, "--json", message])
        env = {**os.environ, "XDG_DATA_HOME": str(Path(target.instance).parent), "MUSE_NO_AUTO_UPDATE": "1"}
    else:
        raise ValueError("Unsupported CLI session provider")
    # Saved general CLI arguments can name a different session or change its
    # permissions. Exact-chat delivery uses only the native resume arguments.
    return args, env


def open_session(target):
    validate_session(target)
    args, env = session_command(target)
    if sys.platform == "win32":
        subprocess.Popen(args, cwd=target.cwd, env=env, creationflags=0x00000010)
    else:
        for name, flags in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--"]),
                            ("konsole", ["-e"]), ("xterm", ["-e"])):
            terminal = shutil.which(name)
            if terminal:
                subprocess.Popen([terminal, *flags, *args], cwd=target.cwd, env=env,
                                 start_new_session=True)
                return
        raise RuntimeError("Install a terminal emulator to open this saved chat")


def _accepted(record, target, message):
    if target.provider == "muse":
        stream = record.get("stream") or {}
        payload = record.get("payload") or {}
        return (stream.get("kind") == "session" and stream.get("id") == target.id
                and record.get("payload_type") in ("turn.input.user", "run.lifecycle.started")
                and payload.get("prompt") == message)
    return (record.get("session_id") == target.id and record.get("type") == "result"
            and record.get("is_error") is False)


def _claim_session(target, directory):
    key = hashlib.sha256(target.key.encode()).hexdigest()
    descriptor = os.open(directory / (key + ".lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt
            os.write(descriptor, b" ")
            os.lseek(descriptor, 0, 0)
            msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(descriptor)
        raise RuntimeError("This saved chat is already being continued by another worker") from exc
    return descriptor


def continue_session(target, message, *, timeout=10):
    """Start the provider's native exact-session resume without changing permissions.

    Process creation alone is not success: require a native prompt record or a
    matching successful result. An uncertain launch is never retried automatically.
    """
    validate_session(target)
    if not Path(target.cwd).is_dir():
        raise RuntimeError("This chat's project directory is unavailable")
    with _lock:
        if active_session(target):
            raise RuntimeError("This provider already has a live session in this project; use its existing terminal")
        args, env = session_command(target, message=message)
        directory = config_dir() / "session-runs"
        directory.mkdir(mode=0o700, exist_ok=True)
        claim = _claim_session(target, directory)
        try:
            descriptor, filename = tempfile.mkstemp(prefix=time.strftime("%Y-%m-%d_") + target.provider + "-", suffix=".log", dir=directory)
        except Exception:
            os.close(claim)
            raise
        try:
            before = Path(target.endpoint).stat().st_size
            with os.fdopen(descriptor, "w", encoding="utf-8") as output:
                process = subprocess.Popen(args, cwd=target.cwd, env=env, stdin=subprocess.DEVNULL,
                    stdout=output, stderr=subprocess.STDOUT,
                    start_new_session=sys.platform != "win32",
                    **({"pass_fds": (claim,)} if sys.platform != "win32" else {}))
        except Exception:
            os.close(claim)
            raise
        _jobs[target.key] = process
    def finish():
        process.wait()
        os.close(claim)
        with _lock:
            if _jobs.get(target.key) is process:
                _jobs.pop(target.key, None)
    threading.Thread(target=finish, daemon=True).start()
    try:
        return _wait_acceptance(target, message, process, filename, before, timeout)
    except (DeliveryUncertain, RuntimeError):
        raise
    except Exception as exc:
        raise DeliveryUncertain(f"Continuation launched but acceptance could not be read. Check {filename} before retrying.") from exc


def _wait_acceptance(target, message, process, filename, before, timeout):
    deadline = time.monotonic() + timeout
    offset = 0
    exited = False
    while True:
        with open(filename, "r", encoding="utf-8", errors="replace") as stream:
            stream.seek(offset)
            while True:
                line = stream.readline()
                if not line or not line.endswith("\n"):
                    break
                offset = stream.tell()
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and _accepted(record, target, message):
                    return f"{target.provider.title()} accepted the message in saved chat {target.id}"
        if target.provider == "claude" and Path(target.endpoint).stat().st_size > before:
            # Claude's transcript is authoritative for the submitted user turn;
            # system/init on stdout only proves initialization, not acceptance.
            with Path(target.endpoint).open("rb") as stream:
                stream.seek(before)
                for line in stream:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if (isinstance(record, dict) and record.get("type") == "user" and record.get("sessionId") == target.id
                            and (record.get("message") or {}).get("content") == message):
                        return f"Claude accepted the message in saved chat {target.id}"
        if process.poll() is not None:
            if not exited:
                exited = True
                continue  # Read final flushed output once after process exit.
            raise RuntimeError(f"The native continuation exited before prompt acceptance. See {filename}")
        if time.monotonic() >= deadline:
            raise DeliveryUncertain(f"Native continuation started but acceptance is unconfirmed. Check {filename} before retrying.")
        time.sleep(.05)
