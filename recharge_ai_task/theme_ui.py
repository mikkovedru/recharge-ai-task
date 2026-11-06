"""Apply a GTK color preference without changing the desktop's settings."""
from gi.repository import Gtk


def apply_color_theme(mode):
    settings = Gtk.Settings.get_default()
    if settings is None:
        return
    if mode not in {"light", "dark"}:
        # Release our overrides so GTK follows current XSettings/settings.ini,
        # including system theme changes made while the app is running.
        settings.reset_property("gtk-theme-name")
        settings.reset_property("gtk-application-prefer-dark-theme")
        return
    # A dark-only system theme cannot become light just by clearing prefer-dark.
    # GTK's bundled Adwaita variants provide both forced modes consistently.
    settings.set_property("gtk-theme-name", "Adwaita")
    settings.set_property("gtk-application-prefer-dark-theme", mode == "dark")
