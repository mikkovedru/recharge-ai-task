"""GTK settings editor; shared configuration is reloaded before saving."""
from __future__ import annotations

import shlex
from gi.repository import Gdk, Gtk

from .autostart import is_autostart_enabled, set_autostart
from .config import AppConfig
from .branding import set_window_icon
from .window_layout import WindowLayout


class SettingsDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Recharge AI-task — Settings", transient_for=parent, modal=True)
        set_window_icon(self)
        self.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save settings", Gtk.ResponseType.OK)
        self.set_default_response(Gtk.ResponseType.OK)
        save_button=self.get_widget_for_response(Gtk.ResponseType.OK)
        save_button.set_can_default(True)
        save_button.grab_default()
        save_button.get_style_context().add_class("suggested-action")
        save_button.set_tooltip_text("Save settings and apply monitoring changes (Enter)")
        cancel_button=self.get_widget_for_response(Gtk.ResponseType.CANCEL)
        cancel_button.set_tooltip_text("Close without saving settings (Escape)")
        self.connect("key-press-event",self._dialog_keys)
        self.set_default_size(540, 390)
        self.window_layout = WindowLayout(self, "settings")
        self.connect("destroy", self.window_layout.close)
        config = AppConfig.load()
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin=18)
        self.get_content_area().add(grid)
        self.mode = Gtk.ComboBoxText()
        for key, label in (("desktop", "Desktop watch"), ("cli", "Codex CLI")):
            self.mode.append(key, label)
        self.mode.set_active_id(config.mode)
        self.path = Gtk.Entry(text=config.codex_path or "", placeholder_text="Auto-detect Codex CLI")
        self.args = Gtk.Entry(text=shlex.join(config.codex_args or []), placeholder_text="Optional CLI arguments")
        self.grace = Gtk.SpinButton.new_with_range(0, 86400, 10)
        self.grace.set_value(config.grace_seconds)
        self.poll = Gtk.SpinButton.new_with_range(1, 3600, 5)
        self.poll.set_value(config.poll_seconds)
        self.autostart = Gtk.CheckButton(label="Run the tray when I log in")
        self.autostart.set_tooltip_text("Start the tray when you log in; applies when settings are saved (Space)")
        try:
            startup = "Enabled" if is_autostart_enabled() else "Disabled"
        except OSError:
            startup = "Unavailable"
        self.autostart.set_active(startup == "Enabled")
        runtime = getattr(parent, "runtime", None)
        launched = "Unknown (tray unavailable)" if runtime is None else "Yes" if runtime.get("launched_at_startup") else "No"
        for index, (name, widget) in enumerate((("Default mode", self.mode),
            ("Codex CLI path", self.path), ("CLI arguments", self.args),
            ("Reset grace (seconds)", self.grace), ("Quota polling (seconds)", self.poll))):
            grid.attach(Gtk.Label(label=name, xalign=0), 0, index, 1, 1)
            widget.set_hexpand(True)
            grid.attach(widget, 1, index, 1, 1)
        startup_row = Gtk.Box(spacing=6)
        startup_row.pack_start(self.autostart, False, False, 0)
        self.startup_info = Gtk.Label(label="(This tray started at login: " + launched + ")", xalign=0)
        self.startup_info.set_line_wrap(True)
        self.startup_info.set_max_width_chars(35)
        startup_row.pack_start(self.startup_info, True, True, 0)
        grid.attach(startup_row, 0, 5, 2, 1)
        self.notes = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for text in (
            "Message text, continuation limits and per-recipient overrides are in the main window.",
            "Those choices save automatically for future quota recovery; Send now acts immediately.",
            "Startup launches the tray; Desktop watch starts when you turn it on.",
            "Changes to an active watch apply automatically."):
            row = Gtk.Box(spacing=6)
            bullet = Gtk.Label(label="•", valign=Gtk.Align.START)
            note = Gtk.Label(label=text, xalign=0, hexpand=True)
            note.set_line_wrap(True)
            note.set_max_width_chars(58)
            row.pack_start(bullet, False, False, 0)
            row.pack_start(note, True, True, 0)
            self.notes.pack_start(row, False, False, 0)
        grid.attach(self.notes, 0, 6, 2, 1)
        self.error = Gtk.Label(xalign=0)
        self.error.set_line_wrap(True)
        grid.attach(self.error, 0, 7, 2, 1)
        self.show_all()

    def _dialog_keys(self,_dialog,event):
        buttons=[self.get_widget_for_response(Gtk.ResponseType.CANCEL),self.get_widget_for_response(Gtk.ResponseType.OK)]
        focus=self.get_focus()
        if event.keyval in (Gdk.KEY_Left,Gdk.KEY_Right) and focus in buttons:
            buttons[1-buttons.index(focus)].grab_focus()
            return True
        return False

    def save_settings(self):
        args = shlex.split(self.args.get_text())
        config = AppConfig.load()
        config.mode = self.mode.get_active_id()
        config.codex_path = self.path.get_text().strip() or None
        config.codex_args = args or None
        config.grace_seconds = self.grace.get_value_as_int()
        config.poll_seconds = self.poll.get_value_as_int()
        config.autostart = self.autostart.get_active()
        # Recreate an enabled entry to update its executable/launch marker.
        previous = is_autostart_enabled()
        set_autostart(config.autostart)
        try:
            config.save()
        except Exception:
            set_autostart(previous)
            self.autostart.set_active(previous)
            raise
        return config

    def edit(self):
        while self.run() == Gtk.ResponseType.OK:
            try:
                result = self.save_settings()
            except Exception as exc:
                self.error.set_text(str(exc))
            else:
                self.destroy()
                return result
        self.destroy()
        return None
