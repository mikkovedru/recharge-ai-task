"""A bounded, selectable, scrollable GTK message log with per-message colors."""
from datetime import datetime
from pathlib import Path

from gi.repository import GLib, Gtk
from .status_display import COLORS, status_colors


class StatusLog(Gtk.ScrolledWindow):
    def __init__(self):
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.set_shadow_type(Gtk.ShadowType.IN)
        self.set_size_request(-1, 96)
        self.view = Gtk.TextView(editable=False, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.view.set_left_margin(8)
        self.view.set_right_margin(8)
        self.view.set_top_margin(6)
        self.view.set_bottom_margin(6)
        self.buffer = self.view.get_buffer()
        for level, color in COLORS.items():
            self.buffer.create_tag(level, foreground=color)
        self.buffer.create_tag("normal")  # Inherit the normal theme text color.
        self.add(self.view)
        self.view.connect("style-updated",self._colors)
        self._colors()
        self.latest_text = ""
        self.latest_level = "normal"
        self._scroll_pending = False
        self._closed = False
        self.connect("destroy", self._destroy)

    def _colors(self,*_):
        for level,color in status_colors(self.view).items():
            self.buffer.get_tag_table().lookup(level).set_property("foreground",color)

    def write(self, message, level="normal", *, timestamp=None, provider=None, attributed=False):
        if not message:
            return
        adjustment = self.get_vadjustment()
        follow = adjustment.get_value() + adjustment.get_page_size() >= adjustment.get_upper() - 2
        self.latest_text, self.latest_level = message, level
        if self.buffer.get_char_count():
            self.buffer.insert(self.buffer.get_end_iter(), "\n")
        moment = datetime.now().astimezone() if timestamp is None else datetime.fromtimestamp(timestamp).astimezone()
        scope = {"codex": "Codex", "claude": "Claude", "muse": "Muse"}.get(provider, "Program")
        content = message if attributed else f"[{scope}] {message}"
        entry = f"[{moment:%Y-%m-%d %H:%M:%S}] {content}"
        self.buffer.insert_with_tags_by_name(self.buffer.get_end_iter(), entry, level)
        # Bound memory while preserving recent text and its tags.
        if self.buffer.get_line_count() > 1000:
            end = self.buffer.get_iter_at_line(self.buffer.get_line_count() - 1000)
            self.buffer.delete(self.buffer.get_start_iter(), end)
        if follow and not self._scroll_pending:
            self._scroll_pending = True
            GLib.idle_add(self._scroll_to_end)

    def text(self):
        return self.buffer.get_text(*self.buffer.get_bounds(), True)

    @staticmethod
    def default_filename():
        return datetime.now().astimezone().strftime("%Y-%m-%d_log_Recharge-AI-task.txt")

    def save_to(self, path):
        text = self.text()
        Path(path).write_text(text + ("\n" if text else ""), encoding="utf-8")

    def clear(self):
        self.buffer.set_text("")
        self.latest_text, self.latest_level = "", "normal"

    def _scroll_to_end(self):
        self._scroll_pending = False
        if not self._closed:
            self.view.scroll_to_iter(self.buffer.get_end_iter(), 0, False, 0, 0)
        return False

    def _destroy(self, *_):
        self._closed = True
