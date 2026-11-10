"""Branded entry to the system package manager; never remove files directly."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .branding import REPOSITORY_URL, asset_path, set_window_icon

PACKAGE = "recharge-ai-task"


def host_environment():
    """Do not load the frozen app's bundled libraries into system tools."""
    env = dict(os.environ)
    if getattr(sys, "frozen", False):
        original = env.get("LD_LIBRARY_PATH_ORIG")
        if original is None:
            env.pop("LD_LIBRARY_PATH", None)
        else:
            env["LD_LIBRARY_PATH"] = original
    return env


def package_installed():
    query = shutil.which("dpkg-query")
    if not query:
        return False
    result = subprocess.run([query, "--show", "--showformat=${db:Status-Abbrev}", PACKAGE],
                            capture_output=True, text=True, timeout=10, env=host_environment())
    return result.returncode == 0 and result.stdout.startswith("ii ")


def removal_command():
    sudo, apt = shutil.which("sudo"), shutil.which("apt")
    if not sudo or not apt:
        raise RuntimeError("Remove the package in Synaptic or run sudo apt remove recharge-ai-task in a terminal.")
    command = [sudo, apt, "remove", PACKAGE]
    for name, flags in (("x-terminal-emulator", ["-e"]), ("gnome-terminal", ["--wait", "--"]),
                        ("konsole", ["-e"]), ("xterm", ["-e"])):
        terminal = shutil.which(name)
        if terminal:
            return [terminal, *flags, *command]
    raise RuntimeError("No terminal emulator found. Remove Recharge AI-task with Synaptic or another package manager.")


def build_dialog(Gtk, *, installed):
    dialog = Gtk.Dialog(title="Uninstall Recharge AI-task", resizable=True)
    dialog.set_default_size(500, -1)
    set_window_icon(dialog)
    content = dialog.get_content_area()
    content.set_spacing(12)
    content.set_border_width(18)
    dialog.logo = Gtk.Image.new_from_file(str(asset_path("icon-64.png")))
    content.pack_start(dialog.logo, False, False, 0)
    heading = Gtk.Label()
    heading.set_markup("<b>Remove Recharge AI-task?</b>" if installed else "<b>No installed package found</b>")
    content.pack_start(heading, False, False, 0)
    text = ("A terminal will open the system package manager, which asks for your password and confirmation before removing the package. Your personal settings and logs will be kept. Turn off Run at startup, then use Exit in the tray to stop running tasks before removal."
            if installed else "This copy is portable or the Debian package is not installed. Portable copies can be deleted from their download folder; no package removal is needed.")
    label = Gtk.Label(label=text, wrap=True, max_width_chars=65, xalign=0)
    content.pack_start(label, True, True, 0)
    dialog.repository = Gtk.LinkButton.new_with_label(REPOSITORY_URL, "Project on GitHub")
    dialog.repository.set_tooltip_text("Open the Recharge AI-task source, documentation and releases on GitHub (Enter)")
    content.pack_start(dialog.repository, False, False, 0)
    dialog.cancel = dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    dialog.cancel.set_tooltip_text("Close without removing anything (Escape)")
    dialog.remove = dialog.add_button("Remove in terminal…", Gtk.ResponseType.ACCEPT)
    dialog.remove.set_tooltip_text("Open apt removal in a terminal; review and confirm there (Enter)")
    dialog.remove.set_sensitive(installed)
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    dialog.cancel.grab_focus()
    def navigate(_widget, event):
        from gi.repository import Gdk
        if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Right) and installed:
            (dialog.cancel if dialog.remove.has_focus() else dialog.remove).grab_focus()
            return True
        return False
    dialog.connect("key-press-event", navigate)
    dialog.show_all()
    return dialog


def main():
    if sys.platform != "linux":
        raise RuntimeError("Package removal requires Linux")
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    dialog = build_dialog(Gtk, installed=package_installed())
    try:
        while dialog.run() == Gtk.ResponseType.ACCEPT:
            try:
                subprocess.Popen(removal_command(), start_new_session=True, env=host_environment())
                return 0
            except (OSError, RuntimeError) as exc:
                error = Gtk.MessageDialog(transient_for=dialog, modal=True, message_type=Gtk.MessageType.ERROR,
                                          buttons=Gtk.ButtonsType.CLOSE, text="Could not open package removal")
                error.format_secondary_text(str(exc))
                error.run()
                error.destroy()
        return 0
    finally:
        dialog.destroy()
