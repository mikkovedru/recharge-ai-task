"""Detect the login session without importing a graphical toolkit."""
import os
import sys


def is_wayland():
    if not sys.platform.startswith("linux"):
        return False
    session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    # An explicit X11 login wins over an inherited nested-compositor variable.
    return session == "wayland" or (session != "x11" and bool(os.environ.get("WAYLAND_DISPLAY")))


def uses_x11_gdk():
    """Check the actual GTK connection, which can differ from the login session."""
    import gi
    gi.require_version("Gdk", "3.0")
    from gi.repository import Gdk
    connection = Gdk.Display.get_default()
    return connection is not None and connection.__gtype__.name == "GdkX11Display"
