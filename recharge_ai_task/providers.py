"""Automatic local provider detection, independent from the list's display filter."""
from .config import AppConfig, PROVIDERS
from .targets import Inventory, discover_targets, codex_home, discover_windows


def installed_providers(config=None):
    config = config or AppConfig.load()
    from .quota import discover_codex
    from .claude import discover_claude, claude_home
    from .muse import discover_muse
    from .session_catalog import muse_home
    roots = {"codex": codex_home(), "claude": claude_home(), "muse": muse_home()}
    discover = {"codex": discover_codex, "claude": discover_claude, "muse": discover_muse}
    result = {}
    for provider in PROVIDERS:
        try:
            executable = discover[provider](getattr(config, provider + "_path"))
        except Exception:
            executable = None
        present = bool(executable or roots[provider].is_dir())
        if not present and provider != "muse":
            try:
                present = bool(discover_windows(provider))
            except Exception:
                pass  # Headless/Wayland inventory must still find CLI histories.
        if present:
            result[provider] = executable
    return result


def discover_all_targets():
    available = installed_providers()
    result = Inventory(providers=tuple(available))
    for provider in available:
        try:
            inventory = discover_targets(provider)
            result.targets.extend(inventory.targets)
            result.warnings.extend(inventory.warnings)
        except Exception as exc:
            result.warnings.append(f"{provider.title()} discovery unavailable: {exc}")
    # Provider identity is part of each non-Codex key. Never deduplicate by title.
    result.targets = list({target.key: target for target in result.targets}.values())
    return result
