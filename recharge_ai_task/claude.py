"""Claude Code discovery, terminal limits and read-only subscription usage."""
from __future__ import annotations

import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .parser import LimitWatcher, parse_duration, strip_ansi
from .quota import Quota, RateWindow


def claude_home():
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))).expanduser()


def discover_claude(explicit=None):
    candidate = explicit or os.environ.get("CLAUDE_CLI_PATH")
    if candidate:
        path = shutil.which(candidate) or str(Path(candidate).expanduser())
        if Path(path).is_file():
            return path
        raise FileNotFoundError(f"Claude executable not found: {candidate}")
    path = shutil.which("claude")
    if path:
        return path
    for path in (Path.home() / ".local/bin/claude", Path.home() / ".local/bin/claude.exe",
                 Path(os.environ.get("APPDATA", "")) / "npm/claude.cmd"):
        if path.is_file():
            return str(path)
    raise FileNotFoundError("Install Claude Code or pass --claude PATH.")


def parse_reset_time(text, now=None):
    """Resolve Claude's clock, dated and duration resets in the displayed zone."""
    now = now or dt.datetime.now().astimezone()
    text = text.strip()
    zone = re.search(r"\(([^)]+)\)", text)
    if zone:
        try:
            now = now.astimezone(ZoneInfo(zone[1]))
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Unrecognized Claude reset timezone") from exc
        text = text[:zone.start()].strip()
    if text.lower().startswith("in "):
        return int((now + parse_duration(text[3:])).timestamp())
    text = re.sub(r"\s+", " ", text).strip().rstrip(" .")
    text = re.sub(r"\s+at\s+", " ", text, flags=re.I)
    for fmt in ("%I:%M%p", "%I%p", "%I:%M %p", "%I %p", "%H:%M",
                "%b %d, %I:%M%p", "%b %d, %I%p", "%b %d %I:%M%p", "%b %d %I%p",
                "%b %d %I:%M %p", "%b %d %I %p", "%Y-%m-%d %H:%M",
                "%b %d, %Y %I:%M%p", "%a %I:%M%p", "%a %I%p"):
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%a" in fmt:
            weekday = time.strptime(text.split()[0], "%a").tm_wday
            date = now.date() + dt.timedelta(days=(weekday - now.weekday()) % 7)
            parsed = parsed.replace(year=date.year, month=date.month, day=date.day)
        elif "%b" not in fmt and "%Y" not in fmt:
            parsed = parsed.replace(year=now.year, month=now.month, day=now.day)
        elif "%Y" not in fmt:
            parsed = parsed.replace(year=now.year)
        parsed = parsed.replace(tzinfo=now.tzinfo)
        if parsed <= now:
            if "%a" in fmt:
                parsed += dt.timedelta(days=7)
            elif "%b" in fmt and "%Y" not in fmt:
                parsed = parsed.replace(year=now.year + 1)
            elif "%Y" not in fmt:
                parsed += dt.timedelta(days=1)
        return int(parsed.timestamp())
    raise ValueError("Unrecognized Claude reset time")


class ClaudeLimitWatcher(LimitWatcher):
    def __init__(self):
        super().__init__()
        self.native_owned = False
        self.reset_at = None
        self._reset_raw = ""

    def reset(self):
        super().reset()
        self.reset_at = None
        self._reset_raw = ""

    def feed(self, chunk):
        self._buf = (self._buf + strip_ansi(chunk))[-20000:]
        # New Claude versions can own recovery. Do not enqueue a second turn.
        if re.search(r"continuing (?:automatically|shortly)|automatic continue cancelled", self._buf, re.I):
            self.native_owned = True
            self.reset()
            return None
        matches = list(re.finditer(r"(?:you[’']ve hit your (?:\w+ )?limit|usage limit reached|usage limit|rate limit)"
                                  r"[^\r\n]*?(?:resets?(?: at)?|try again at|try again in)\s+([^\r\n·]+)", self._buf, re.I))
        match = matches[-1] if matches else None
        if match:
            raw = match[1].strip()
            if raw == self._reset_raw and self.reset_at is not None:
                return self.reset_at, raw
            try:
                reset = parse_reset_time(("in " if "try again in" in match[0].lower() else "") + raw)
            except ValueError:
                # A PTY can split a clock or timezone across reads. Keep buffering.
                return None
            self.native_owned = False
            self._reset_raw, self.reset_at = raw, reset
            return reset, raw
        return None


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward the user's bearer credential to another URL.


def parse_usage(data, plan="Claude subscription"):
    if not isinstance(data, dict):
        raise RuntimeError("Claude usage returned an invalid response")
    windows = []
    for key, value in data.items():
        if key != "five_hour" and not key.startswith("seven_day"):
            continue
        if value is None:
            continue
        try:
            used = float(value["utilization"])
            if not math.isfinite(used) or used < 0:
                raise ValueError()
            raw_reset = value["resets_at"]
            reset = dt.datetime.fromisoformat(raw_reset.replace("Z", "+00:00")) if raw_reset is not None else None
            if (reset is None and used != 0) or (reset is not None and reset.tzinfo is None):
                raise ValueError()
            windows.append(RateWindow(used, 300 if key == "five_hour" else 10080,
                                      int(reset.timestamp()) if reset else 0, label=key.replace("_", " ").capitalize()))
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise RuntimeError(f"Claude usage has an invalid {key} window") from exc
    if not windows:
        raise RuntimeError("Claude usage contains no readable quota windows; no recovery assumed")
    return Quota(plan, windows[0], windows[1] if len(windows) > 1 else None,
                 any(w.used_percent >= 100 for w in windows), additional=tuple(windows[2:]))


def fetch_claude_quota(timeout=15):
    """Read Claude's private /usage backend; never refresh or persist credentials."""
    try:
        data = json.loads((claude_home() / ".credentials.json").read_text(encoding="utf-8"))
        oauth = data["claudeAiOauth"]
        token = oauth["accessToken"]
        if not isinstance(token, str) or not token.strip():
            raise ValueError()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError("Claude usage requires a Claude Code subscription login. Run claude auth login on this machine.") from exc
    expires = oauth.get("expiresAt")
    if isinstance(expires, (int, float)) and expires <= time.time() * 1000:
        raise RuntimeError("Claude login expired. Open Claude Code or run claude auth login to refresh it.")
    request = Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20", "Accept": "application/json"})
    try:
        with build_opener(_NoRedirect()).open(request, timeout=timeout) as response:
            result = json.loads(response.read(1024 * 1024))
    except HTTPError as exc:
        help_text = "Run claude auth login again." if exc.code in (401, 403) else "Usage service unavailable; retry later."
        raise RuntimeError(f"Claude quota HTTP {exc.code}. {help_text}") from None
    except (URLError, OSError, ValueError):
        raise RuntimeError("Cannot read Claude usage; check the connection and Claude Code login.") from None
    return parse_usage(result, "Claude " + str(oauth.get("subscriptionType") or "subscription"))
