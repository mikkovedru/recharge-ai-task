"""Uninstall is a deliberate handoff to apt, never a direct deletion."""
from types import SimpleNamespace

import pytest
from recharge_ai_task import uninstall


def test_package_detection_requires_installed_status(monkeypatch):
    monkeypatch.setattr(uninstall.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    calls = []
    def query(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout="ii ")
    monkeypatch.setattr(uninstall.subprocess, "run", query)
    assert uninstall.package_installed()
    assert calls == [["/usr/bin/dpkg-query", "--show", "--showformat=${db:Status-Abbrev}", "recharge-ai-task"]]
    monkeypatch.setattr(uninstall.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="rc "))
    assert not uninstall.package_installed()


def test_removal_uses_terminal_and_apt_confirmation_without_shell_or_auto_yes(monkeypatch):
    monkeypatch.setattr(uninstall.shutil, "which", lambda name: "/usr/bin/" + name)
    assert uninstall.removal_command() == ["/usr/bin/x-terminal-emulator", "-e", "/usr/bin/sudo", "/usr/bin/apt", "remove", "recharge-ai-task"]
    monkeypatch.setattr(uninstall.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="Synaptic"):
        uninstall.removal_command()


def test_uninstall_dispatch_does_not_start_tray(monkeypatch):
    from recharge_ai_task import gui
    monkeypatch.setattr(gui.sys, "platform", "linux")
    monkeypatch.setattr(uninstall, "main", lambda: 7)
    assert gui.main(["--uninstall"]) == 7
    with pytest.raises(SystemExit):
        gui.main(["--uninstall", "--autostart"])


def test_removal_dialog_logo_link_cancel_default_and_disabled_portable_action():
    import os
    if os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1":
        pytest.skip("Requires GTK")
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk
    for installed in (False, True):
        dialog = uninstall.build_dialog(Gtk, installed=installed)
        try:
            assert dialog.repository.get_uri() == uninstall.REPOSITORY_URL
            assert dialog.logo.get_pixbuf() is not None
            assert dialog.get_default_widget() == dialog.cancel
            assert dialog.remove.get_sensitive() == installed
            dialog.resize(420, 300)
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            # Cancel remains the default even when the destructive action exists.
            assert dialog.get_default_widget() == dialog.cancel
            if installed:
                dialog.cancel.grab_focus()
                event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
                event.keyval = Gdk.KEY_Right
                dialog.emit("key-press-event", event)
                assert dialog.get_focus() == dialog.remove
        finally:
            dialog.destroy()


@pytest.mark.parametrize("original", [None, "/original/system/libs"])
def test_frozen_removal_restores_host_library_environment(monkeypatch, original):
    monkeypatch.setattr(uninstall.sys, "frozen", True, raising=False)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/frozen/runtime")
    if original is None:
        monkeypatch.delenv("LD_LIBRARY_PATH_ORIG", raising=False)
    else:
        monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", original)
    env = uninstall.host_environment()
    assert env.get("LD_LIBRARY_PATH") == original
    import os
    assert os.environ["LD_LIBRARY_PATH"] == "/frozen/runtime"
