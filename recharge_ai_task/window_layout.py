"""Remember window geometry and user-adjustable split pane positions."""
from gi.repository import GLib, Gtk
from .config import AppConfig


class WindowLayout:
    def __init__(self, window, namespace="dashboard"):
        self.window, self.namespace = window, namespace
        saved = AppConfig.load().ui_layout or {}
        self.saved = saved.get(namespace, {}) if isinstance(saved, dict) else {}
        if not isinstance(self.saved, dict):
            self.saved = {}
        size = self.saved.get("size")
        if not (isinstance(size, list) and len(size) == 2 and all(type(v) is int and 200 <= v <= 10000 for v in size)):
            size = list(window.get_default_size())
        screen = window.get_screen()
        area = screen.get_monitor_workarea(screen.get_primary_monitor())
        # Leave room for window-manager borders and the title bar on laptops.
        window.set_default_size(min(max(200, size[0]), max(200, area.width - 16)),
                                min(max(200, size[1]), max(200, area.height - 48)))
        self.panes = {}
        self.ready = False
        self.timer = None
        self.pending = False
        self.initial = None
        self.closed = False
        window.connect("map", self._mapped)
        window.connect("configure-event", self._changed)

    def pane(self, key, first, second, *, horizontal=False, position=200):
        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL)
        pane.set_wide_handle(True)
        pane.pack1(first, resize=True, shrink=False)
        pane.pack2(second, resize=True, shrink=False)
        self.panes[key] = pane, position
        pane.connect("notify::position", self._changed)
        return pane

    def _mapped(self, *_):
        if self.ready:
            return
        def restore(step=0):
            if self.closed:
                return False
            positions = self.saved.get("panes", {})
            for key, (pane, default) in reversed(list(self.panes.items())):
                value = positions.get(key, default) if isinstance(positions, dict) else default
                pane.set_position(value if type(value) is int and 0 <= value <= 10000 else default)
            if step == 2:
                self.ready = True
                self.initial = self.snapshot()
            else:
                # Outer panes allocate their children on the next GTK layout
                # pass. Reapply inner positions afterwards to avoid drift.
                GLib.timeout_add(30, lambda: restore(step + 1))
            return False
        GLib.idle_add(restore)

    def snapshot(self):
        return {"size": list(self.window.get_size()),
                "panes": {key: pane.get_position() for key, (pane, _) in self.panes.items()}}

    def _changed(self, *_):
        if not self.ready or self.closed:
            return False
        self.pending = True
        if self.timer is not None:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(250, self._save)
        return False

    def _save(self):
        self.timer = None
        if self.pending and self.snapshot() != self.initial:
            try:
                config = AppConfig.load()
                layouts = dict(config.ui_layout or {})
                layouts[self.namespace] = self.snapshot()
                config.ui_layout = layouts
                config.save()
                self.initial = layouts[self.namespace]
            except Exception as exc:
                if hasattr(self.window, "_message"):
                    self.window._message(f"Could not save panel sizes: {exc}", "error")
                else:
                    import logging
                    logging.getLogger(__name__).warning("Could not save panel sizes: %s", exc)
                return False
        self.pending = False
        return False

    def close(self, *_):
        if self.timer is not None:
            GLib.source_remove(self.timer)
            self.timer = None
        self._save()
        self.closed = True
