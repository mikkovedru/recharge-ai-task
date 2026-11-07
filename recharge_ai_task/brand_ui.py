"""Version information and repository actions on the dashboard logo."""
from gi.repository import Gdk, GLib, Gtk
from . import __version__
from .branding import REPOSITORY_URL


class ProjectLogo(Gtk.Button):
    def __init__(self, image):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.set_tooltip_text(f"Recharge AI-task {__version__}\nOpen GitHub (Enter / Space). Right-click or press Shift+F10 to copy the repository link.")
        self.add(image)
        self.image = image
        self.connect("button-press-event", self._press)
        self.connect("clicked",self._open)
        self.connect("popup-menu",self._popup)
        self.menu = Gtk.Menu()
        item = Gtk.MenuItem(label=f"Copy GitHub repository link ({REPOSITORY_URL})")
        item.connect("activate", self.copy_link)
        self.menu.append(item)
        self.menu.show_all()
        self.connect("destroy", lambda *_: self.menu.destroy())

    def match_width(self, reference, artwork):
        """Keep the artwork as wide as a neighboring control, including HiDPI."""
        self.set_halign(Gtk.Align.FILL)
        self.image.set_halign(Gtk.Align.FILL)
        self.width_css = Gtk.CssProvider()
        self.width_css.load_from_data(b"button.project-logo { padding: 0; border-width: 0; min-width: 0; min-height: 0; }")
        self.get_style_context().add_class("project-logo")
        self.get_style_context().add_provider(self.width_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.scaled_size = None
        self.width_update = None
        self.width_closed = False
        def update():
            self.width_update = None
            if self.width_closed:
                return False
            width = reference.get_allocated_width() if reference.get_realized() else reference.get_preferred_width()[1]
            scale = self.get_scale_factor()
            if width <= 1 or self.scaled_size == (width, scale):
                return False
            height = max(1, round(width * artwork.get_height() / artwork.get_width()))
            from gi.repository import GdkPixbuf
            pixels = artwork.scale_simple(width * scale, height * scale, GdkPixbuf.InterpType.HYPER)
            self.image.set_from_surface(Gdk.cairo_surface_create_from_pixbuf(pixels, scale, self.get_window()))
            self.scaled_size = (width, scale)
            return False
        def resize(*_):
            # Changing image requests during allocation can leave its old height.
            if not self.width_closed and self.width_update is None:
                self.width_update = GLib.idle_add(update)
        def closed(*_):
            self.width_closed = True
            if self.width_update is not None:
                GLib.source_remove(self.width_update)
                self.width_update = None
        reference.connect("size-allocate", resize)
        self.connect("notify::scale-factor", resize)
        self.connect("destroy", closed)
        if not reference.get_realized():
            update()  # Establish the correct height before the first window allocation.

    def copy_link(self, *_):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(REPOSITORY_URL, -1)

    def _open(self,*_):
        Gtk.show_uri_on_window(self.get_toplevel(),REPOSITORY_URL,Gdk.CURRENT_TIME)

    def _popup(self,*_):
        self.menu.popup_at_widget(self,Gdk.Gravity.SOUTH_WEST,Gdk.Gravity.NORTH_WEST,None)
        return True

    def _press(self, _widget, event):
        if event.button == 3:
            self.menu.popup_at_pointer(event)
            return True
        return False
