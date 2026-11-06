"""Muse Code terminal limits and subscription allowance through its own CLI."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

from .parser import LimitWatcher, strip_ansi
from .quota import Quota, RateWindow


DESKTOP_LIMITATION = (
    "Muse Code continuation runs in a wrapped terminal. Start Muse Code CLI here "
    "or run recharge-ai-task-cli run --provider muse. Consumer Muse app/browser "
    "chats have no supported continuation bridge in this integration."
)


def discover_muse(explicit=None):
    candidate = explicit or os.environ.get("MUSE_CLI_PATH")
    if candidate:
        path = shutil.which(candidate) or str(Path(candidate).expanduser())
        if Path(path).is_file():
            return path
        raise FileNotFoundError(f"Muse Code executable not found: {candidate}")
    path = shutil.which("muse")
    if path:
        return path
    for path in (Path.home() / ".local/bin/muse", Path.home() / ".local/bin/muse.exe"):
        if path.is_file():
            return str(path)
    raise FileNotFoundError("Install Meta Muse Code or pass --muse PATH.")


def parse_usage(value, *, now=None, not_before=None):
    """Read the allowance-v1 JSON produced by Muse Code 1.4.13+.

    A missing allowance or stale observation never proves recovery. Millisecond
    timestamps are kept separate from the application's Unix-second windows.
    """
    now = time.time() if now is None else now
    if not isinstance(value, dict) or type(value.get("schemaVersion")) is not int or value["schemaVersion"] != 1:
        raise RuntimeError("Unsupported Muse usage response. Install Muse Code 1.4.13 or later.")
    allowance = value.get("allowance")
    if not isinstance(allowance, dict):
        if value.get("reason") == "api_key":
            raise RuntimeError("Muse API-key billing has no subscription allowance. Use muse login with a subscription account.")
        raise RuntimeError("Muse returned no subscription allowance. Check muse usage and muse login; no recovery assumed.")
    observed = allowance.get("asOfMs")
    if type(observed) not in (int, float) or not math.isfinite(observed) or not now - 120 <= observed / 1000 <= now + 30:
        raise RuntimeError("Muse allowance observation is missing or stale; no recovery assumed. Check muse usage.")
    if not_before is not None and observed < int(not_before * 1000):
        raise RuntimeError("Muse allowance predates this usage limit; waiting for a new observation.")

    def window(key, duration):
        item = allowance.get(key)
        if not isinstance(item, dict):
            raise RuntimeError(f"Muse usage is missing its {key} allowance; no recovery assumed.")
        used, reset = item.get("usedPercent"), item.get("resetsAtMs")
        mins = item.get("windowDurationMins", duration)
        if (type(used) not in (int, float) or not math.isfinite(used) or used < 0
                or type(reset) is not int or not 0 < reset < 253402300800000
                or type(mins) is not int or mins <= 0):
            raise RuntimeError(f"Muse usage has an invalid {key} allowance; no recovery assumed.")
        return RateWindow(float(used), mins, reset // 1000, "Session" if key == "window" else "Weekly")

    primary, secondary = window("window", 300), window("weekly", 10080)
    tier = allowance.get("tier")
    if not isinstance(tier, str) or not tier.strip():
        raise RuntimeError("Muse usage is missing its subscription tier; no recovery assumed.")
    return Quota("Muse " + tier, primary, secondary, primary.used_percent >= 100 or secondary.used_percent >= 100)


def fetch_muse_quota(muse_path=None, timeout=15, *, not_before=None):
    executable = discover_muse(muse_path)
    try:
        result = subprocess.run([executable, "usage", "--json"], capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=timeout,
                                env={**os.environ, "MUSE_NO_AUTO_UPDATE": "1"})
    except subprocess.TimeoutExpired:
        raise RuntimeError("Muse usage timed out; no recovery assumed.") from None
    if result.returncode:
        # Do not forward arbitrary subprocess output or provider credentials.
        raise RuntimeError("Cannot read Muse allowance. Run muse login, then muse usage --json. Muse Code 1.4.13+ is required.")
    try:
        value = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError("Muse usage returned invalid JSON; no recovery assumed.") from None
    return parse_usage(value, not_before=not_before)


class MuseLimitWatcher(LimitWatcher):
    def feed(self, chunk):
        self._buf = (self._buf + strip_ansi(chunk))[-20000:]
        match = re.search(
            r"(?:^|[\r\n])[ \t│╰─⎿]*(?:(?:error|agent loop failed):\s*)?"
            r"(?:usage limit reached|usage limit exceeded|subscription (?:usage )?limit reached|tier[_ ]limit)\b",
            self._buf, re.I,
        )
        if match:
            # Muse's native banner does not promise a reset timestamp. Read the
            # subscription allowance instead of inventing a timer from it.
            return None, match[0].strip()
        return None
