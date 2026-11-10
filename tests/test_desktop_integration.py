"""Linux launchers must survive frozen extraction and quote real file paths."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from recharge_ai_task import desktop_integration as integration, gui


@pytest.fixture
def release(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    folder = tmp_path / 'release with space $ ` % " \\ marks'
    folder.mkdir()
    for name in integration._NAMES:
        (folder / name).write_text("#!/bin/sh\nexit 0\n")
        (folder / name).chmod(0o755)
    aliases = home / ".local/bin"
    aliases.mkdir(parents=True)
    for name in integration._NAMES:
        (aliases / name).symlink_to(folder / name)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("XDG_DATA_HOME", str(home / "application data"))
    monkeypatch.setattr(integration.sys, "frozen", True, raising=False)
    monkeypatch.setattr(integration, "SYSTEM_EXECUTABLE", tmp_path / "not-installed")
    monkeypatch.setattr(integration, "SYSTEM_LAUNCHER", tmp_path / "not-installed.desktop")
    monkeypatch.setattr(integration.sys, "executable", str(folder / "recharge-ai-task"))
    original = integration.shutil.which
    monkeypatch.setattr(integration.shutil, "which", lambda name: str(aliases/name) if name in integration._NAMES else original(name))
    return folder, home


def test_both_executables_and_symlinks_get_persistent_icons_and_menu_entries(release, monkeypatch):
    calls = []
    original = integration.shutil.which
    monkeypatch.setattr(integration.shutil, "which", lambda name: "/fixture/gio" if name == "gio" else None if name == "update-desktop-database" else original(name))
    monkeypatch.setattr(integration.subprocess, "run", lambda argv, **kwargs: calls.append(argv) or SimpleNamespace(returncode=0, stderr=""))
    result = integration.install_desktop()
    folder, home = release
    assert not result.warnings and len(result.files) == 2 and len(result.launchers) == 1
    for launcher in result.launchers:
        entries = dict(line.split("=",1) for line in launcher.read_text().split("\n[", 1)[0].splitlines() if "=" in line)
        assert entries["GenericName"] == "AI task continuation"
        assert "OpenCode" in entries["Comment"]
        assert {"Codex", "Claude", "Muse", "OpenCode", "quota"} <= set(entries["Keywords"].split(";"))
        assert entries["Actions"] == "Website;"
        assert "Exec=xdg-open https://github.com/mikkovedru/recharge-ai-task" in launcher.read_text()
        icon = Path(entries["Icon"])
        assert icon.is_file() and icon.read_bytes() == integration.asset_path("icon-256.png").read_bytes()
        assert "Terminal=" + str(launcher.stem.endswith("-cli")).lower() in launcher.read_text()
        assert entries["Exec"].startswith('"') and "%%" in entries["Exec"]
    assert {Path(call[4]) for call in calls} == set(result.files)
    assert all(call[-2] == "metadata::custom-icon" and call[-1] == icon.as_uri() for call in calls)
    # Reinstallation is stable; it does not duplicate or replace the commands.
    assert integration.install_desktop().launchers == result.launchers


def test_metadata_failure_does_not_prevent_usable_launchers(release, monkeypatch):
    original = integration.shutil.which
    monkeypatch.setattr(integration.shutil, "which", lambda name: "/fixture/gio" if name == "gio" else None if name == "update-desktop-database" else original(name))
    monkeypatch.setattr(integration.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stderr="metadata unavailable"))
    result = integration.install_desktop()
    assert len(result.launchers) == 1 and not result.files
    assert len(result.warnings) == 2 and all("metadata unavailable" in text for text in result.warnings)


def test_isolated_profiles_never_install_into_the_real_desktop(release, monkeypatch):
    monkeypatch.setattr(integration, "install_desktop", lambda: pytest.fail("Installed real desktop integration from an isolated profile"))
    integration.install_on_launch()


def test_install_option_exits_without_starting_gui_or_tray(monkeypatch):
    monkeypatch.setattr(integration, "install_main", lambda: 7)
    monkeypatch.setitem(sys.modules, "recharge_ai_task.tray", None)
    assert gui.main(["--install-desktop"]) == 7


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GIO desktop launcher implementation")
def test_native_launcher_roundtrips_shell_characters_without_a_shell(release, monkeypatch, tmp_path):
    from gi.repository import Gio
    import time
    folder, home = release
    output = tmp_path / "started.json"
    command = folder / "recharge-ai-task"
    command.write_text("#!/usr/bin/python3\nimport json,sys\nfrom pathlib import Path\nPath(" + repr(str(output)) + ").write_text(json.dumps(sys.argv))\n")
    # Avoid metadata writes in this quoting-only check.
    original = integration.shutil.which
    monkeypatch.setattr(integration.shutil, "which", lambda name: None if name in {"gio", "update-desktop-database"} else original(name))
    result = integration.install_desktop()
    desktop = next(p for p in result.launchers if p.stem == "recharge-ai-task")
    subprocess.run(["desktop-file-validate", str(desktop)], check=True, capture_output=True)
    app = Gio.DesktopAppInfo.new_from_filename(str(desktop))
    assert app is not None and app.launch([], None)
    until = time.monotonic() + 3
    while not output.exists() and time.monotonic() < until:
        time.sleep(.01)
    assert json.loads(output.read_text()) == [str(command)]


@pytest.mark.parametrize("marked", [False, True])
@pytest.mark.parametrize("portable", [False, True])
def test_installed_build_removes_generated_shadow_and_keeps_package_owned_launcher(tmp_path, monkeypatch, marked, portable):
    root = tmp_path / "system"
    executable = root / "usr/bin/recharge-ai-task"
    executable.parent.mkdir(parents=True)
    executable.touch()
    launcher = root / "usr/share/applications/recharge-ai-task.desktop"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("[Desktop Entry]\nName=Recharge AI-task\n")
    data = tmp_path / "user-data"
    shadow = data / "applications/recharge-ai-task.desktop"
    shadow.parent.mkdir(parents=True)
    old_executable = tmp_path / "old portable/recharge-ai-task" if portable else executable
    shadow.write_text("\n".join([
        "[Desktop Entry]", "Type=Application", "Version=1.0", "Name=Recharge AI-task",
        "Comment=Continue Codex tasks after quota recovery", "Exec=" + integration._exec_value([str(old_executable)]),
        "Icon=" + integration._value(data / "recharge-ai-task/icon.png"), "Terminal=false", "Categories=Utility;",
        "StartupNotify=false", "StartupWMClass=recharge-ai-task-tray",
        *( ["X-Recharge-AI-Task-Managed=true"] if marked else []), ""]))
    monkeypatch.setattr(integration, "SYSTEM_EXECUTABLE", executable)
    monkeypatch.setattr(integration, "SYSTEM_LAUNCHER", launcher)
    monkeypatch.setattr(integration.sys, "frozen", True, raising=False)
    monkeypatch.setattr(integration.sys, "executable", str(executable))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setattr(integration, "_commands", lambda: pytest.fail("Created portable integration for an installed package"))
    result = integration.install_desktop()
    assert result.launchers == [launcher] and not result.warnings
    assert not shadow.exists()
    assert launcher.read_text() == "[Desktop Entry]\nName=Recharge AI-task\n"
    assert integration.install_desktop().launchers == [launcher]


def test_installed_build_preserves_customized_user_launcher(tmp_path, monkeypatch):
    binary = tmp_path / "recharge-ai-task"
    binary.touch()
    system = tmp_path / "system.desktop"
    system.touch()
    data = tmp_path / "user-data"
    shadow = data / "applications/recharge-ai-task.desktop"
    shadow.parent.mkdir(parents=True)
    original = "[Desktop Entry]\nName=My Recharge\nExec=/my/custom/path\n"
    shadow.write_text(original)
    monkeypatch.setattr(integration, "SYSTEM_EXECUTABLE", binary)
    monkeypatch.setattr(integration, "SYSTEM_LAUNCHER", system)
    monkeypatch.setattr(integration.sys, "frozen", True, raising=False)
    monkeypatch.setattr(integration.sys, "executable", str(binary))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    result = integration.install_desktop()
    assert shadow.read_text() == original and len(result.warnings) == 1


@pytest.mark.parametrize("customized", [False, True])
def test_installed_build_only_retires_exact_current_portable_launcher(release, monkeypatch, customized):
    monkeypatch.setattr(integration.shutil, "which", lambda _: None)
    result = integration.install_desktop()
    shadow = result.launchers[0]
    original = shadow.read_text()
    if customized:
        original = original.replace("Name=Project on GitHub", "Name=My website")
        shadow.write_text(original)
    system = shadow.parent.parent / "system.desktop"
    system.touch()
    monkeypatch.setattr(integration, "SYSTEM_LAUNCHER", system)
    monkeypatch.setattr(integration, "SYSTEM_EXECUTABLE", Path(integration.sys.executable))
    installed = integration.install_desktop()
    assert installed.launchers == [system]
    assert shadow.exists() == customized
    if customized:
        assert shadow.read_text() == original and installed.warnings
    else:
        assert not installed.warnings


@pytest.mark.parametrize("kind", ["generated", "custom", "symlink"])
def test_package_configuration_migrates_before_any_app_launch(tmp_path, kind):
    """Execute the shipped postinst with account switching isolated to a fixture."""
    home = tmp_path / "home with spaces"
    data = home / ".local/share"
    shadow = data / "applications/recharge-ai-task.desktop"
    shadow.parent.mkdir(parents=True)
    original = integration.desktop_entry(integration._exec_value(["/old/portable/recharge-ai-task"]),
                                         integration._value(data / "recharge-ai-task/icon.png"))
    if kind == "custom":
        original = original.replace("Name=Project on GitHub", "Name=My repository")
    if kind == "symlink":
        target = tmp_path / "custom.desktop"
        target.write_text(original)
        shadow.symlink_to(target)
    else:
        shadow.write_text(original)
    system = tmp_path / "system.desktop"
    system.write_text("[Desktop Entry]\nName=Package-owned entry\n")
    binary = tmp_path / "installed-binary"
    binary.touch()
    helpers = tmp_path / "helpers"
    helpers.mkdir()
    accounts = (f"root:x:0:0::{home}:/bin/sh\n"
                f"fixture:x:1000:1000::{home}:/bin/sh\n"
                f"nobody:x:65534:65534::{home}:/bin/sh\n"
                f"invalid:x:not-a-uid:1000::{home}:/bin/sh\n")
    (helpers / "getent").write_text(f"#!{sys.executable}\nprint({accounts!r}, end='')\n")
    calls = tmp_path / "runuser.json"
    (helpers / "runuser").write_text(f'''#!{sys.executable}
import json,os,sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parents[1])!r})
from recharge_ai_task import desktop_integration as integration
assert sys.argv[1:] == ['-u','fixture','--','env','-u','XDG_DATA_HOME',{'HOME=' + str(home)!r},'/usr/bin/recharge-ai-task','--install-desktop']
Path({str(calls)!r}).write_text(json.dumps(sys.argv[1:]))
os.environ['HOME']={str(home)!r}
os.environ.pop('XDG_DATA_HOME',None)
sys.frozen=True
integration.SYSTEM_LAUNCHER=Path({str(system)!r})
integration.SYSTEM_EXECUTABLE=Path({str(binary)!r})
sys.exit(integration.install_main())
''')
    for helper in helpers.iterdir():
        helper.chmod(0o755)
    postinst = Path(__file__).resolve().parents[1] / "packaging/linux/postinst"
    env = dict(os.environ, PATH=str(helpers) + os.pathsep + os.environ["PATH"], XDG_DATA_HOME="/wrong/installer/profile")
    # Other maintainer-script phases must not touch user launchers.
    subprocess.run(["sh", str(postinst), "abort-upgrade"], env=env, check=True)
    assert not calls.exists() and shadow.exists()
    for _ in range(2):  # Reconfiguration is safe and repeatable.
        subprocess.run(["sh", str(postinst), "configure"], env=env, check=True, capture_output=True)
    assert calls.exists()
    assert shadow.exists() == (kind != "generated")
    if kind != "generated":
        assert shadow.read_text() == original
    assert system.read_text() == "[Desktop Entry]\nName=Package-owned entry\n"
