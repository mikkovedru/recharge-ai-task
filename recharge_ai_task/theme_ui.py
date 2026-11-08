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


def install_readability(window):
    """Keep app text legible even when GTK marks the window as a backdrop.

    Use theme colors and a priority below semantic status styles so status,
    selection and checked-action colors retain their meaning in either theme.
    """
    window.get_style_context().add_class("recharge-ui")
    css = Gtk.CssProvider()
    css.load_from_data(b"""
        .recharge-ui label { color: @theme_fg_color; opacity: 1; }
        .recharge-ui button, .recharge-ui checkbutton, .recharge-ui spinbutton {
            color: @theme_fg_color; }
        .recharge-ui button { border-color: alpha(@theme_fg_color, .60); }
        .recharge-ui button label, .recharge-ui button image { color: inherit; }
        .recharge-ui button:disabled, .recharge-ui label:disabled {
            color: mix(@theme_fg_color, @theme_bg_color, .30); }
        .recharge-ui entry, .recharge-ui textview text, .recharge-ui treeview.view {
            color: @theme_text_color; background-color: @theme_base_color; }
        .recharge-ui treeview.view:selected {
            color: @theme_text_color;
            background-color: mix(@theme_base_color, @theme_selected_bg_color, .16); }
        .recharge-ui checkbutton check:not(:checked), .recharge-ui treeview.view check:not(:checked) {
            border-color: alpha(@theme_fg_color, .65); background-color: @theme_base_color; }
        .recharge-ui frame > border { border-color: alpha(@theme_fg_color, .35); }
        .recharge-ui entry selection, .recharge-ui textview text selection {
            color: @theme_selected_fg_color; background-color: @theme_selected_bg_color; }
    """)
    screen = window.get_screen()
    Gtk.StyleContext.add_provider_for_screen(screen, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION - 1)
    window.connect("destroy", lambda *_: Gtk.StyleContext.remove_provider_for_screen(screen, css))
