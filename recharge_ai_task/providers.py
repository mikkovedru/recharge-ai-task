"""Automatic local provider detection, independent from the list's display filter."""
import os
import subprocess
from pathlib import Path

from .config import AppConfig, PROVIDERS, TERMINAL_PROVIDERS
from .targets import Inventory, discover_targets, codex_home, discover_windows


def installed_providers(config=None):
    config = config or AppConfig.load()
    from .quota import discover_codex
    from .claude import discover_claude, claude_home
    from .muse import discover_muse
    from .session_catalog import muse_home
    from .opencode import discover_opencode
    from .google_ai import discover_google_cli
    roots = {"codex": codex_home(), "claude": claude_home(), "muse": muse_home(), "opencode": Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "opencode"}
    discover = {"codex": discover_codex, "claude": discover_claude, "muse": discover_muse, "opencode": discover_opencode}
    roots.update(gemini=Path.home()/".gemini", antigravity=Path.home()/".gemini/antigravity-cli")
    discover.update(gemini=lambda path: discover_google_cli("gemini", path),
                    antigravity=lambda path: discover_google_cli("antigravity", path))
    result = {}
    for provider in PROVIDERS:
        try:
            executable = discover[provider](getattr(config, provider + "_path"))
        except Exception:
            executable = None
        present = bool(executable or roots[provider].is_dir())
        if not present and provider not in ("muse", *TERMINAL_PROVIDERS):
            try:
                present = bool(discover_windows(provider))
            except Exception:
                pass  # Headless/Wayland inventory must still find CLI histories.
        if present:
            result[provider] = executable
    return result


def discover_all_targets(*, check_versions=False):
    available = installed_providers()
    installed = []
    for provider, executable in available.items():
        if executable:
            installed.append(provider)
        elif provider not in ("muse", *TERMINAL_PROVIDERS):
            try:
                if discover_windows(provider):
                    installed.append(provider)
            except Exception:
                pass
    result = Inventory(providers=tuple(available), installed_providers=tuple(installed))
    if check_versions:
        for provider in PROVIDERS:
            executable = available.get(provider)
            if executable:
                try:
                    probe = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=8, check=True)
                    version = (probe.stdout or probe.stderr).strip().splitlines()
                    detail = version[0][:240] if version else "Version unavailable: command returned no version"
                except Exception as exc:
                    detail = f"Version unavailable: {exc}"
                result.provider_details[provider] = f"Executable: {executable}\n{detail}"
            else:
                result.provider_details[provider] = ("Supported desktop app detected; CLI version unavailable" if provider in installed else
                    "No installed executable or supported running app detected" +
                    ("; saved local history is available" if provider in available else ""))
    for provider in available:
        try:
            inventory = discover_targets(provider)
            result.targets.extend(inventory.targets)
            result.warnings.extend(inventory.warnings)
            result.provider_warnings[provider] = list(inventory.warnings)
        except Exception as exc:
            problem = f"{provider.title()} discovery unavailable: {exc}"
            result.warnings.append(problem)
            result.provider_warnings[provider] = [problem]
    # Provider identity is part of each non-Codex key. Never deduplicate by title.
    result.targets = list({target.key: target for target in result.targets}.values())
    return result


def check_providers():
    """Explicit read-only installation/version and chat inventory refresh."""
    return discover_all_targets(check_versions=True)
