"""Saved GTK table widths, column order, wrapping and header sorting."""
from gi.repository import GLib, Gtk, Pango

from .config import AppConfig


class TableLayout:
    def __init__(self, table, store, saved, message, *, default_sort=None):
        self.table, self.store = table, store
        self.table.set_halign(Gtk.Align.START)
        self.saved = saved if isinstance(saved, dict) else {}
        self.message = message
        self.default_sort = default_sort
        self.columns = {}
        self.sort_column = None
        self.descending = False
        self.restoring = True
        self.timer = None
        self.dirty = False
        self.table.connect("columns-changed", self._changed)

    def register(self, key, column, index, width, renderer=None):
        self.columns[key] = (column, index)
        header = column.get_widget()
        if header is None:
            header = Gtk.Label(label=column.get_title())
            column.set_widget(header)
            header.show()
        column.set_resizable(True)
        column.set_reorderable(True)
        column.set_clickable(True)
        column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
        column.set_min_width(36)
        for cell in column.get_cells():
            cell.set_padding(2, 1)
        column.set_expand(False)
        widths = self.saved.get("widths")
        value = widths.get(key) if isinstance(widths, dict) else None
        old_defaults = {"send_prompt": 125, "send_goal": 125, "title": 270,
                        "task_status": 170, "goal_status": 140, "project_name": 180,
                        "last_active_at": 180}
        if self.saved.get("density") != 2 and value == old_defaults.get(key):
            value = width
        column.set_fixed_width(value if type(value) is int and 36 <= value <= 10000 else width)
        column.connect("clicked", self._clicked, key)
        column.connect("notify::fixed-width", self._changed)
        self._header_width(column)
        column.connect("notify::width", self._header_width)
        column.connect("notify::fixed-width", self._header_width)
        if renderer is not None:
            renderer.set_property("ellipsize", Pango.EllipsizeMode.NONE)
            renderer.set_property("wrap-mode", Pango.WrapMode.WORD_CHAR)
            renderer.set_property("yalign", 0)
            self._wrap(column, None, renderer)
            column.connect("notify::width", self._wrap, renderer)
            column.connect("notify::fixed-width", self._wrap, renderer)
        self.store.set_sort_func(index, self._compare, index)

    @staticmethod
    def _header_width(column, _spec=None):
        # GtkTreeView measures a wrapping GtkLabel at its minimum width, which
        # can make headers hundreds of pixels tall. Explicit line breaks keep
        # header height tied to the column width instead.
        width = max(12, (column.get_width() or column.get_fixed_width()) - 24)
        def wrap(widget, available):
            if isinstance(widget, Gtk.Label):
                caption = getattr(widget, "_table_caption", widget.get_text())
                widget._table_caption = caption
                layout = widget.create_pango_layout(caption)
                layout.set_width(available * Pango.SCALE)
                layout.set_wrap(Pango.WrapMode.WORD_CHAR)
                encoded = caption.encode("utf-8")
                lines = [encoded[line.start_index:line.start_index + line.length].decode("utf-8").strip()
                         for line in layout.get_lines_readonly()]
                text = "\n".join(lines)
                if widget.get_text() != text:
                    widget.set_text(text)
            elif isinstance(widget, Gtk.Container):
                children = widget.get_children()
                space = 20 if any(isinstance(child, Gtk.Image) for child in children) else 0
                for child in children:
                    wrap(child, max(12, available - space))
        wrap(column.get_widget(), width)

    @staticmethod
    def _wrap(column, _spec, renderer):
        width = max(1, (column.get_width() or column.get_fixed_width()) - 6)
        if renderer.get_property("wrap-width") != width:
            renderer.set_property("wrap-width", width)
            column.queue_resize()

    @staticmethod
    def _compare(model, first, second, index):
        a, b = model[first][index], model[second][index]
        if index == 5:  # PID is displayed as text but sorts as a number.
            a, b = int(a or 0), int(b or 0)
        elif isinstance(a, str):
            a, b = a.casefold(), b.casefold()
        result = (a > b) - (a < b)
        if not result:
            # Keep equal values stable across discovery and status refreshes.
            a = (model[first][6], model[first][4])
            b = (model[second][6], model[second][4])
            result = (a > b) - (a < b)
        return result

    def restore(self):
        order = self.saved.get("order")
        previous = None
        seen = set()
        for key in order if isinstance(order, list) else []:
            if isinstance(key, str) and key in self.columns and key not in seen:
                column = self.columns[key][0]
                self.table.move_column_after(column, previous)
                previous = column
                seen.add(key)
        key = self.saved.get("sort_column")
        if not isinstance(key, str) or key not in self.columns:
            key = self.default_sort
            descending = True
        else:
            descending = self.saved.get("descending") is True
        if key in self.columns:
            self.sort(key, descending)
        self.restoring = False

    def _clicked(self, _column, key):
        self.sort(key, not self.descending if self.sort_column == key else False)

    def sort(self, key, descending=False):
        self.sort_column, self.descending = key, descending
        order = Gtk.SortType.DESCENDING if descending else Gtk.SortType.ASCENDING
        for name, (column, _index) in self.columns.items():
            column.set_sort_indicator(name == key)
            column.set_sort_order(order)
        self.store.set_sort_column_id(self.columns[key][1], order)
        self._changed()

    def snapshot(self):
        keys = {column: key for key, (column, _index) in self.columns.items()}
        return {"density": 2, "order": [keys[column] for column in self.table.get_columns()],
                "widths": {key: column.get_fixed_width() for key, (column, _index) in self.columns.items()},
                "sort_column": self.sort_column, "descending": self.descending}

    def _changed(self, *_):
        if self.restoring:
            return
        self.dirty = True
        if self.timer is not None:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(250, self._save)

    def _save(self):
        self.timer = None
        if self.dirty:
            try:
                config = AppConfig.load()
                config.table_layout = self.snapshot()
                config.save()
                self.dirty = False
            except Exception as exc:
                self.message(f"Could not save table layout: {exc}", "error")
        return False

    def close(self):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        self._save()
