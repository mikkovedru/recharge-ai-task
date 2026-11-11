"""Google Gemini and Antigravity CLI wrapping with explicit terminal reset times."""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import time

from .parser import LimitWatcher, parse_absolute_time, strip_ansi

CLI_NAMES = {"gemini": "gemini", "antigravity": "agy"}
LABELS = {"gemini": "Google Gemini CLI", "antigravity": "Google Antigravity CLI"}


def limitation(provider):
    usage = "/stats" if provider == "gemini" else "/usage"
    return (
        f"{LABELS[provider]} is supported in a wrapped interactive terminal: "
        f"recharge-ai-task run --provider {provider}. Continuation requires a stopped "
        "quota/usage-limit message with an explicit supported reset time and an available prompt. "
        "Native retries, model fallback and choice dialogs stay in control; typing cancels the wait. "
        f"Use {usage} inside the provider for its usage view. Shared dashboard quota, desktop chat "
        "delivery and Codex Goal recovery are unavailable for this integration."
    )


def discover_google_cli(provider, explicit=None):
    name = CLI_NAMES[provider]
    candidate = explicit or os.environ.get(provider.upper() + "_CLI_PATH")
    if candidate:
        path = shutil.which(candidate) or str(Path(candidate).expanduser())
        if Path(path).is_file():
            return path
        raise FileNotFoundError(f"{LABELS[provider]} executable not found: {candidate}")
    found = shutil.which(name)
    if found:
        return found
    directories = [Path.home() / ".local/bin"]
    if provider == "gemini" and os.environ.get("APPDATA"):
        directories.append(Path(os.environ["APPDATA"]) / "npm")
    if provider == "antigravity" and os.environ.get("LOCALAPPDATA"):
        directories.append(Path(os.environ["LOCALAPPDATA"]) / "agy/bin")
    for directory in directories:
        for filename in (name, name + ".exe", name + ".cmd"):
            path = directory / filename
            if path.is_file():
                return str(path)
    raise FileNotFoundError(f"Install {LABELS[provider]} ({name}) or pass --{provider} PATH.")


def fetch_google_quota(provider):
    # Interactive /stats and /usage are not a stable machine-readable quota API.
    raise RuntimeError(limitation(provider))


def validate_interactive_args(provider, args):
    headless = {"-p", "--prompt", "--print", "--output-format", "--input-format", "--acp", "--experimental-acp", "--remote-agent"}
    if any(arg.split("=", 1)[0] in headless or
           (arg.startswith("-p") and not arg.startswith("--")) for arg in args):
        raise ValueError(f"{LABELS[provider]} wrapping requires a local interactive terminal; headless, ACP and remote-agent modes cannot receive continuation prompts.")


_LIMIT = re.compile(r"usage[ _-]+limit|rate[ _-]+limit|quota\s+(?:exhausted|exceeded|reached)|(?:exhausted|exceeded).{0,80}(?:capacity|quota)|resource[ _-]+exhausted", re.I)
_UNIT = r"(?:weeks?|days?|hours?|hrs?|minutes?|mins?|seconds?|secs?|[wdhms])"
_DURATION = rf"(?:\d+(?:\.\d+)?\s*{_UNIT}\s*)+"
_RESET = re.compile(rf"(?:try again|please retry|retry|resets?|will reset|available again)\s+(?:in|after)\s+({_DURATION})", re.I)
_ABSOLUTE = re.compile(r"(?:try again|resets?)\s+at\s+([^\r\n]+)", re.I)
_NATIVE = re.compile(r"\bretrying\b|\bretry\s+(?:attempt|#|\d)|\battempt\s*#?\s*\d+|\bswitch(?:ing)?\s+to\b|\bkeep trying\b|\bpress (?:enter|return)\b|\bselect (?:a |another )?model\b", re.I)


class GoogleLimitWatcher(LimitWatcher):
    """Never infer a reset from a bare 429, or submit into a native choice dialog."""
    def __init__(self):
        super().__init__()
        self.native_retry = False
        self.last_banner = None
        self.last_result = None

    def reset(self):
        super().reset()
        self.last_banner = self.last_result = None

    def feed(self, chunk):
        self._buf = (self._buf + strip_ansi(chunk))[-20000:]
        limits = list(_LIMIT.finditer(self._buf))
        native = list(_NATIVE.finditer(self._buf))
        if native and (not limits or native[-1].start() > limits[-1].start()):
            self.native_retry = True
            return None
        if not limits:
            return None
        banner = self._buf[limits[-1].start():]
        match = _RESET.search(banner)
        if match:
            raw = match.group(1).strip()
            factors = {'w': 604800, 'd': 86400, 'h': 3600, 'm': 60, 's': 1}
            seconds = sum(float(amount) * factors[unit[0].lower()]
                          for amount, unit in re.findall(rf"(\d+(?:\.\d+)?)\s*({_UNIT})", raw, re.I))
            if seconds <= 0:
                return None
            signature = banner[:match.end()]
            reset_at = time.time() + seconds
        else:
            match = _ABSOLUTE.search(banner)
            if not match:
                return None
            raw = match.group(1).strip().rstrip(' .)')
            try:
                reset_at = parse_absolute_time(raw).timestamp()
            except ValueError:
                return None
            signature = banner[:match.end()]
        # Output following the same banner must not push its timer into the future.
        if signature != self.last_banner:
            self.last_banner = signature
            self.last_result = (reset_at, raw)
        self.native_retry = False
        return self.last_result
