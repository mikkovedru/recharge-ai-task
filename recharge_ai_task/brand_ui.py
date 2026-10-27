"""Version information and repository actions on the dashboard logo."""
from gi.repository import Gdk, Gtk
from . import __version__
from .branding import REPOSITORY_URL


class ProjectLogo(Gtk.Button):
    def __init__(self, image):
        super().__init__()
        self.set_relief(Gtk.ReliefStyle.NONE)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.set_tooltip_text(f"Recharge AI-task {__version__}\nOpen GitHub (Enter / Space). Right-click or press Shift+F10 to copy the repository link.")
        self.add(image)
        self.connect("button-press-event", self._press)
        self.connect("clicked",self._open)
        self.connect("popup-menu",self._popup)
        self.menu = Gtk.Menu()
        item = Gtk.MenuItem(label="Copy GitHub repository link")
        item.connect("activate", self.copy_link)
        self.menu.append(item)
        self.menu.show_all()
        self.connect("destroy", lambda *_: self.menu.destroy())

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
