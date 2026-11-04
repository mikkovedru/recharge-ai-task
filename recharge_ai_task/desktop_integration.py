"""Per-user Linux launchers and Nemo/GIO executable icons.

ELF executables do not supply Nemo's file icon. Keep artwork outside the frozen
runtime's temporary directory and assign its URI to each file and command link.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .branding import asset_path

_NAMES = ("recharge-ai-task", "recharge-ai-task-cli")


@dataclass
class InstallResult:
    launchers: list[Path] = field(default_factory=list)
    files: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _commands():
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
        return {name: [str(folder / name)] for name in _NAMES if (folder / name).is_file()}
    result = {}
    for name, module in zip(_NAMES, ("gui", "cli")):
        command = shutil.which(name)
        result[name] = [command] if command else [sys.executable, "-m", f"recharge_ai_task.{module}"]
    return result


def _exec_value(argv):
    # Exec quoting and desktop-entry string escaping are separate layers.
    # Literal percent signs must not become desktop field codes.
    # GIO probes argv[0] before expanding %% and otherwise rejects valid paths
    # containing a percent sign. env execs the command after argument expansion.
    if "%" in argv[0]:
        argv = ["/usr/bin/env", *argv]
    tokens = []
    for arg in argv:
        if any(char in arg for char in "\n\r\0"):
            raise ValueError("Desktop launcher command contains a control character")
        quoted = arg.replace("%", "%%")
        for char in ("\\", '"', "$", "`"):
            quoted = quoted.replace(char, "\\" + char)
        tokens.append('"' + quoted + '"')
    return " ".join(tokens).replace("\\", "\\\\")


def _value(value):
    return str(value).replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")


def _write_if_changed(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content if isinstance(content, bytes) else content.encode("utf-8")
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)


def _file_paths(commands):
    files = set()
    for name, command in commands.items():
        if len(command) != 1:
            continue  # Never apply our artwork to the Python interpreter.
        executable = Path(command[0]).absolute()
        files.update((executable, executable.resolve()))
        for candidate in (shutil.which(name), Path.home() / ".local" / "bin" / name):
            if candidate and Path(candidate).is_file() and Path(candidate).resolve() == executable.resolve():
                files.add(Path(candidate).absolute())
    return sorted(files)


def install_desktop() -> InstallResult:
    if sys.platform != "linux":
        raise RuntimeError("Desktop integration installation requires Linux")
    commands = _commands()
    if not commands:
        raise RuntimeError("No Recharge AI-task executable found beside this installer")
    data_home = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share").expanduser()
    if not data_home.is_absolute():
        data_home = Path.home() / ".local" / "share"
    icon = data_home / "recharge-ai-task" / "icon.png"
    _write_if_changed(icon, asset_path("icon-256.png").read_bytes())
    result = InstallResult()
    for name, argv in commands.items():
        terminal = name.endswith("-cli")
        launcher = data_home / "applications" / (name + ".desktop")
        content = "\n".join((
            "[Desktop Entry]", "Type=Application", "Version=1.0",
            "Name=Recharge AI-task" + (" CLI" if terminal else ""),
            "Comment=Continue Codex tasks after quota recovery",
            "Exec=" + _exec_value(argv), "Icon=" + _value(icon),
            "Terminal=" + str(terminal).lower(), "Categories=Utility;",
            "StartupNotify=false", "StartupWMClass=recharge-ai-task-tray", "",
        ))
        _write_if_changed(launcher, content)
        result.launchers.append(launcher)
    gio = shutil.which("gio")
    files = _file_paths(commands)
    if not gio:
        result.warnings.append("gio is unavailable; launchers have icons, but executable file icons need GIO/GVfs")
    else:
        for executable in files:
            try:
                assigned = subprocess.run([gio, "set", "-t", "string", str(executable),
                    "metadata::custom-icon", icon.as_uri()], capture_output=True, text=True, timeout=5)
                if assigned.returncode:
                    result.warnings.append(f"Could not set file icon for {executable}: {assigned.stderr.strip()}")
                else:
                    result.files.append(executable)
            except (OSError, subprocess.TimeoutExpired) as exc:
                result.warnings.append(f"Could not set file icon for {executable}: {exc}")
    updater = shutil.which("update-desktop-database")
    if updater:
        try:
            subprocess.run([updater, str(data_home / "applications")], capture_output=True, timeout=5, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            result.warnings.append(f"Could not refresh the application menu: {exc}")
    return result


def install_main():
    result = install_desktop()
    for path in result.launchers:
        print(f"Installed launcher: {path}")
    for path in result.files:
        print(f"Assigned file icon: {path}")
    for warning in result.warnings:
        print(warning, file=sys.stderr)
    return 1 if result.warnings else 0


def install_on_launch():
    """Refresh frozen-release integration without affecting isolated test profiles."""
    from ._migration import environment_value
    if not getattr(sys, "frozen", False) or environment_value("CONFIG_DIR") or not Path(sys.executable).is_file():
        return
    import logging
    try:
        result = install_desktop()
        for warning in result.warnings:
            logging.getLogger("recharge-ai-task.desktop").warning(warning)
    except (OSError, RuntimeError, ValueError) as exc:
        logging.getLogger("recharge-ai-task.desktop").warning("Could not install desktop integration: %s", exc)
