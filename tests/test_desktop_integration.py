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
    assert not result.warnings and len(result.files) == 4 and len(result.launchers) == 2
    for launcher in result.launchers:
        entries = dict(line.split("=",1) for line in launcher.read_text().splitlines() if "=" in line)
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
    assert len(result.launchers) == 2 and not result.files
    assert len(result.warnings) == 4 and all("metadata unavailable" in text for text in result.warnings)


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
