"""Persistent user settings."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from ._migration import LEGACY_CONTINUE_PROMPT, environment_value, import_settings
from .desktop_input import DEFAULT_WINDOW_TITLES

Mode = Literal["cli", "desktop"]
PROVIDER_LABELS = {"codex": "OpenAI Codex", "claude": "Anthropic Claude", "muse": "Meta Muse Code", "opencode": "OpenCode"}
PROVIDERS = tuple(PROVIDER_LABELS)


def config_dir() -> Path:
    explicit = environment_value("CONFIG_DIR")
    root = Path(explicit).expanduser() if explicit else Path.home() / ".recharge-ai-task"
    root.mkdir(parents=True, exist_ok=True)
    if not explicit:
        import_settings(root)
    return root


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class AppConfig:
    mode: Mode = "cli"
    goal_mode: bool = True
    grace_seconds: int = 60
    continue_prompt: str = "Continue"
    autostart: bool = False
    codex_path: str | None = None
    codex_args: list[str] | None = None
    desktop_window_titles: list[str] | None = None
    poll_seconds: int = 30
    desktop_targets: list[dict] | None = None
    recipient_keys: list[str] | None = None
    show_technical_columns: bool = False
    table_layout: dict | None = None
    ui_layout: dict | None = None
    color_theme: str = "auto"
    prompt_limit: int | None = None
    goal_limit: int | None = None
    provider: str = "codex"
    claude_path: str | None = None
    claude_args: list[str] | None = None
    muse_path: str | None = None
    muse_args: list[str] | None = None
    opencode_path: str | None = None
    opencode_args: list[str] | None = None
    chat_provider_filter: str = "all"

    @classmethod
    def load(cls) -> AppConfig:
        path = config_path()
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        prompt = str(data.get("continue_prompt", "Continue"))
        if prompt == LEGACY_CONTINUE_PROMPT:
            prompt = "Continue"
        return cls(
            mode=data.get("mode", "cli"),
            goal_mode=bool(data.get("goal_mode", True)),
            grace_seconds=int(data.get("grace_seconds", 60)),
            continue_prompt=prompt,
            autostart=bool(data.get("autostart", False)),
            codex_path=data.get("codex_path"),
            codex_args=data.get("codex_args"),
            desktop_window_titles=data.get("desktop_window_titles"),
            poll_seconds=int(data.get("poll_seconds", 30)),
            desktop_targets=data.get("desktop_targets"),
            recipient_keys=data.get("recipient_keys") if isinstance(data.get("recipient_keys"), list) else None,
            show_technical_columns=bool(data.get("show_technical_columns", False)),
            table_layout=data.get("table_layout") if isinstance(data.get("table_layout"), dict) else None,
            ui_layout=data.get("ui_layout") if isinstance(data.get("ui_layout"), dict) else None,
            color_theme=data.get("color_theme") if data.get("color_theme") in ("dark", "light", "auto") else "auto",
            prompt_limit=data.get("prompt_limit"),
            goal_limit=data.get("goal_limit"),
            provider=data.get("provider") if data.get("provider") in PROVIDERS else "codex",
            claude_path=data.get("claude_path"),
            claude_args=data.get("claude_args"),
            muse_path=data.get("muse_path"),
            muse_args=data.get("muse_args"),
            opencode_path=data.get("opencode_path"),
            opencode_args=data.get("opencode_args"),
            chat_provider_filter=data.get("chat_provider_filter") if data.get("chat_provider_filter") in ("all", *PROVIDERS) else "all",
        )

    def save(self) -> None:
        path = config_path()
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix="config-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(asdict(self), stream, ensure_ascii=False, indent=2)
            os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def window_titles(self) -> tuple[str, ...]:
        if self.desktop_window_titles:
            return tuple(self.desktop_window_titles)
        return DEFAULT_WINDOW_TITLES

    def all_targets(self):
        from .targets import Target
        from .delivery_policy import clear_consumed_custom_prompt
        result = []
        for value in self.desktop_targets or []:
            target = clear_consumed_custom_prompt(Target.from_dict(value))
            prompt, goal = target.signal_actions(self.goal_mode)
            result.append(replace(target, send_prompt=prompt, send_goal=goal))
        return result

    def targets(self, provider=None):
        return [t for t in self.all_targets() if (provider is None or t.provider == provider) and any(t.signal_actions())]

    def recipients(self):
        """Saved panel membership, independent of the enabled delivery actions.

        Older settings contain disabled preferences for removed recipients, so
        only enabled targets are migrated into the panel on the first save.
        """
        if self.recipient_keys is None:
            return self.targets()
        keys = set(self.recipient_keys)
        return [t for t in self.all_targets() if t.key in keys or any(t.signal_actions())]
