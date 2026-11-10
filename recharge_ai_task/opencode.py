"""OpenCode interactive terminal integration, independent of model-provider quota."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil

from .parser import LimitWatcher, strip_ansi

LIMITATION = (
    "OpenCode is supported in a wrapped interactive terminal: "
    "recharge-ai-task run --provider opencode. Recovery requires an explicit "
    "'try again in/at' reset message. OpenCode's own automatic retries remain "
    "in control. Shared quota checks and desktop chat delivery are unavailable "
    "because quota depends on the model provider selected in OpenCode."
)


def discover_opencode(explicit=None):
    candidate = explicit or os.environ.get("OPENCODE_CLI_PATH")
    if candidate:
        path = shutil.which(candidate) or str(Path(candidate).expanduser())
        if Path(path).is_file():
            return path
        raise FileNotFoundError(f"OpenCode executable not found: {candidate}")
    path = shutil.which("opencode")
    if path:
        return path
    for directory in (Path.home() / ".opencode/bin", Path.home() / ".local/bin"):
        for name in ("opencode", "opencode.exe"):
            path = directory / name
            if path.is_file():
                return str(path)
    raise FileNotFoundError("Install OpenCode or pass --opencode PATH.")


def fetch_opencode_quota():
    raise RuntimeError(LIMITATION)


class OpenCodeLimitWatcher(LimitWatcher):
    """Use explicit reset messages; never add prompts during native retries."""
    def __init__(self):
        super().__init__()
        self.native_retry = False

    def feed(self, chunk):
        text = strip_ansi(chunk)
        if re.search(r"\bretrying\b|\bretry\s+(?:attempt|#|\d)|\battempt\s*#?\s*\d+", (self._buf + text)[-20000:], re.I):
            self.native_retry = True
            self.reset()
            return None
        # Keep retry ownership until a fresh, explicit stopped-limit banner.
        if self.native_retry and not re.search(r"(?:usage|rate)[ _]limit.*try again", text, re.I | re.S):
            return None
        try:
            detected = super().feed(chunk)
        except ValueError:
            # Partial PTY chunks and provider-specific time formats aren't a timer.
            return None
        if detected:
            self.native_retry = False
        return detected
