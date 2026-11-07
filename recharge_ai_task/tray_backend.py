"""Select the native Cinnamon backend, retaining pystray elsewhere."""
import os
import sys
from .display_session import is_wayland, uses_x11_gdk


def is_cinnamon() -> bool:
    return sys.platform == "linux" and "cinnamon" in os.environ.get("XDG_CURRENT_DESKTOP", "").lower()


def prepare_backend() -> None:
    if is_wayland():
        # Gtk.StatusIcon/Gtk.Plug and pystray's xorg fallback use XEmbed.
        # AppIndicator publishes a StatusNotifierItem over D-Bus instead.
        os.environ.setdefault("PYSTRAY_BACKEND", "appindicator")
    if is_cinnamon():
        os.environ.setdefault("PYSTRAY_BACKEND", "gtk")
        try:
            from gi.repository import GLib
            GLib.set_prgname("recharge-ai-task-tray")
            if GLib.get_application_name() != "Recharge AI-task":
                GLib.set_application_name("Recharge AI-task")
        except ImportError:
            pass


def icon_class(default):
    if is_cinnamon() and os.environ.get("PYSTRAY_BACKEND") == "gtk":
        try:
            import gi
            gi.require_version("XApp", "1.0")
            from gi.repository import XApp
            if XApp.StatusIcon.any_monitors():
                from .tray_xapp import XAppIcon
                return XAppIcon
            if uses_x11_gdk():
                from .tray_gtk import CinnamonGtkIcon
                return CinnamonGtkIcon
            from pystray._appindicator import Icon
            return Icon
        except (ImportError, ValueError):
            import logging
            logging.getLogger("recharge-ai-task.tray").warning("XApp is unavailable; using the GTK tray backend")
    return default
