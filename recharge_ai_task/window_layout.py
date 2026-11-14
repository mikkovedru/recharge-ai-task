"""Remember window geometry and user-adjustable split pane positions."""
from gi.repository import GLib, Gtk
from .config import AppConfig


class WindowLayout:
    def __init__(self, window, namespace="dashboard", *, version=1, reset_size_on_version_change=False):
        self.window, self.namespace = window, namespace
        self.version = version
        self.regions = {}
        saved = AppConfig.load().ui_layout or {}
        self.saved = saved.get(namespace, {}) if isinstance(saved, dict) else {}
        if not isinstance(self.saved, dict):
            self.saved = {}
        if self.saved.get("layout_version") != version:
            self.saved = dict(self.saved, panes={})
            if reset_size_on_version_change:
                self.saved.pop("size", None)
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

    def pane(self, key, first, second, *, horizontal=False, position=200, resize_second=True):
        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL if horizontal else Gtk.Orientation.VERTICAL)
        # All user-resizable dividers share the native theme and handle size.
        pane.get_style_context().add_class("workspace-divider")
        pane.set_wide_handle(True)
        pane.pack1(first, resize=True, shrink=not horizontal)
        pane.pack2(second, resize=resize_second, shrink=not horizontal)
        self.panes[key] = pane, position
        pane.connect("notify::position", self._changed)
        return pane

    def region(self,key,widget):
        self.regions[key]=widget
        regions=self.saved.get("regions",{})
        size=regions.get(key) if isinstance(regions,dict) else None
        if isinstance(size,list) and len(size)==2 and type(size[0]) is int and type(size[1]) is int and -1<=size[0]<=4000 and 48<=size[1]<=4000:
            widget.restore_size(*size)
        widget.connect("resized",self._changed)
        return widget

    def _mapped(self, *_):
        if self.ready:
            return
        previous_geometry = None
        stable_passes = 0
        def restore(step=0):
            nonlocal previous_geometry, stable_passes
            if self.closed:
                return False
            geometry = tuple((key, pane.get_position(), pane.get_allocated_width(), pane.get_allocated_height(),
                              pane.get_child1().get_allocated_height(), pane.get_child2().get_allocated_height())
                             for key, (pane, _default) in self.panes.items())
            stable_passes = stable_passes + 1 if geometry == previous_geometry else 0
            previous_geometry = geometry
            positions = self.saved.get("panes", {})
            for key, (pane, default) in reversed(list(self.panes.items())):
                value = positions.get(key, default) if isinstance(positions, dict) else default
                extent=pane.get_allocated_width() if pane.get_orientation()==Gtk.Orientation.HORIZONTAL else pane.get_allocated_height()
                if value == "fit-second" and pane.get_orientation() == Gtk.Orientation.VERTICAL:
                    first, second = pane.get_child1(), pane.get_child2()
                    handle = max(0, extent - first.get_allocated_height() - second.get_allocated_height())
                    natural = second.get_preferred_height_for_width(max(1, pane.get_allocated_width()))[1]
                    value = max(first.get_preferred_height()[0], extent - natural - handle)
                if type(value) is float and 0<value<1:
                    value=int(extent*value)
                pane.set_position(value if type(value) is int and 0 <= value <= 10000 else 200)
            minimum_passes = 6 if positions else 2
            if (step >= minimum_passes and stable_passes >= 2) or step >= 8:
                self.ready = True
                self.initial = self.snapshot()
            else:
                # GTK may adjust a non-resizing child after the first restore
                # passes. Finish only after geometry settles, with a bounded
                # startup window so later user drags remain authoritative.
                # Saved positions need the later style/layout passes as well.
                GLib.timeout_add(30, lambda: restore(step + 1))
            return False
        GLib.idle_add(restore)

    def snapshot(self):
        return {"layout_version": self.version, "size": list(self.window.get_size()),
                "regions": {key: widget.editor_size() for key,widget in self.regions.items()},
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
