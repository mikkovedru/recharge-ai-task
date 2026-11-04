"""Opaque XEmbed tray surface for legacy Cinnamon status applets."""
import logging
import time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_foreign("cairo")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
from PIL import Image
from Xlib import display, protocol, error
from pystray._util.gtk import GtkIcon, mainloop


class CinnamonGtkIcon(GtkIcon):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._rendered_size = None
        self._size_timer = None
        self._xdisplay = display.Display()
        self._plug = None
        self._owner = None
        self._last_dock = 0
        self._closing = False
        self._refresh_error = None
        self._create_plug()

    def _create_plug(self):
        self._plug = Gtk.Plug.new(0)
        # A panel/socket disappearing emits delete-event. Its default handler
        # destroys the plug even though our process and controller stay alive.
        self._plug.connect("delete-event", self._unplugged)
        self._plug.connect("destroy", self._plug_destroyed)
        self._plug.set_title("recharge-ai-task-tray")
        self._area = Gtk.DrawingArea()
        self._area.set_size_request(16, 16)
        self._area.set_hexpand(True)
        self._area.set_vexpand(True)
        self._area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._area.connect("draw", self._draw_icon)
        self._area.connect("button-press-event", self._button_press)
        self._plug.add(self._area)
        self._plug.realize()
        self._plug.set_tooltip_text(self.title)
        self._owner = None
        self._last_dock = 0
        self._rendered_size = None

    def _unplugged(self, *_):
        self._owner = None
        self._last_dock = 0
        return True  # Keep the native plug available for the replacement panel.

    def _plug_destroyed(self, *_):
        self._plug = None
        self._owner = None
        self._rendered_size = None

    def _allocated_size(self):
        if self._plug is None or self._plug.get_window() is None:
            return 16
        # XEmbed hosts allocate physical pixels. GDK geometry uses logical
        # coordinates, which can be smaller and can lag an external resize.
        geometry = self._xdisplay.create_resource_object("window", self._plug.get_id()).get_geometry()
        return max(1, min(geometry.width, geometry.height))

    def _draw_icon(self, _area, cr):
        if _area is not self._area:
            return True
        try:
            size = self._allocated_size()
        except (error.XError, OSError, RuntimeError):
            return True  # A later refresh redraws after the host/window settles.
        image = self.icon.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
        pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(GLib.Bytes.new(image.tobytes()), GdkPixbuf.Colorspace.RGB, True, 8, size, size, size * 4)
        # GTK's draw context already scales logical coordinates to device pixels.
        # Paint a physical-resolution pixbuf exactly once into the host's square.
        scale = self._area.get_scale_factor()
        cr.save()
        cr.scale(1 / scale, 1 / scale)
        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
        cr.paint()
        cr.restore()
        self._rendered_size = size
        return True

    def _button_press(self, _area, event):
        if event.button == 1 and event.type == Gdk.EventType.DOUBLE_BUTTON_PRESS:
            self()
            return True
        if event.button == 3 and self._menu_handle is not None:
            self._menu_handle.popup_at_pointer(event)
            return True
        return False

    def _dock(self):
        selection = self._xdisplay.intern_atom(f"_NET_SYSTEM_TRAY_S{self._xdisplay.get_default_screen()}")
        owner = self._xdisplay.get_selection_owner(selection)
        if not getattr(owner, "id", 0):
            self._owner = None
            return
        now = time.monotonic()
        if owner.id != self._owner or (not self._plug.get_embedded() and now - self._last_dock >= 2):
            request = protocol.event.ClientMessage(window=owner, client_type=self._xdisplay.intern_atom("_NET_SYSTEM_TRAY_OPCODE"), data=(32, [0, 0, self._plug.get_id(), 0, 0]))
            owner.send_event(request)
            self._xdisplay.flush()
            self._owner = owner.id
            self._last_dock = now

    def _refresh(self):
        try:
            result = self._refresh_once()
            self._refresh_error = None
            return result
        except (error.XError, OSError, RuntimeError, GLib.Error) as exc:
            # A manager can die between lookup, geometry and docking requests.
            # GLib removes a timeout whose callback raises; keep this one alive.
            message = str(exc)
            if self._refresh_error != message:
                logging.getLogger("recharge-ai-task.tray").warning("Tray refresh will retry: %s", message)
                self._refresh_error = message
            self._owner = None
            return True

    def _refresh_once(self):
        if self._closing:
            return False
        if self._plug is None:
            self._create_plug()
            if self.visible:
                self._plug.show_all()
        self._dock()
        size = self._allocated_size()
        if size != self._rendered_size:
            self._area.queue_draw()
        return True

    def _stop_refresh(self):
        if self._size_timer is not None:
            if GLib.MainContext.default().find_source_by_id(self._size_timer) is not None:
                GLib.source_remove(self._size_timer)
            self._size_timer = None

    @mainloop
    def ensure_visible(self):
        """Repair only the tray surface/timer; retain the app and its services."""
        if self._closing:
            return
        self._stop_refresh()
        if self._plug is not None:
            self._plug.destroy()
        self._create_plug()
        self.visible = True
        self._plug.show_all()
        self._refresh()
        self._size_timer = GLib.timeout_add(500, self._refresh)

    @mainloop
    def _show(self):
        if self._plug is None:
            self._create_plug()
        self._plug.show_all()
        self._dock()
        self._area.queue_draw()

    @mainloop
    def _hide(self):
        if self._plug is not None:
            self._plug.hide()

    @mainloop
    def _update_icon(self):
        self._remove_fs_icon()
        self._update_fs_icon()
        self._area.queue_draw()

    @mainloop
    def _update_title(self):
        if self._plug is not None:
            self._plug.set_tooltip_text(self.title)

    @mainloop
    def _update_menu(self):
        self._menu_handle = self._create_menu(self.menu)

    def _initialize(self):
        super()._initialize()
        self._size_timer = GLib.timeout_add(500, self._refresh)
        logging.getLogger("recharge-ai-task.tray").info("Using direct XEmbed drawing for Cinnamon's legacy tray")

    def _finalize(self):
        self._closing = True
        self._stop_refresh()
        if self._plug is not None:
            self._plug.destroy()
        self._xdisplay.close()
        super()._finalize()
