"""Compact, keyboard-accessible provider buttons shared by dashboard sections."""
from gi.repository import Gdk, GObject, Gtk

PROVIDER_NAMES = {'all': 'All', 'codex': 'Codex', 'claude': 'Claude', 'muse': 'Muse'}


class ProviderButtons(Gtk.Box):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, *, active='all', purpose='Filter visible items; saved recipients and monitoring stay unchanged'):
        super().__init__(spacing=0)
        self.get_style_context().add_class('linked')
        self.buttons = {}
        group = None
        for key, caption in PROVIDER_NAMES.items():
            button = Gtk.RadioButton.new_with_label_from_widget(group, caption)
            group = group or button
            button.set_mode(False)
            button.set_tooltip_text(f'{caption}: {purpose} (Left / Right, Home / End)')
            button.get_accessible().set_name(f'{caption} providers')
            button.connect('toggled', self._changed)
            button.connect('key-press-event', self._keys, key)
            self.pack_start(button, False, False, 0)
            self.buttons[key] = button
        self.set_active_id(active)

    def _changed(self, button):
        if button.get_active():
            self.emit('changed')

    def get_active_id(self):
        return next((key for key, button in self.buttons.items() if button.get_active()), 'all')

    def set_active_id(self, key):
        self.buttons[key if key in self.buttons else 'all'].set_active(True)

    def _keys(self, _button, event, key):
        keys = list(self.buttons)
        if event.keyval in (Gdk.KEY_Home, Gdk.KEY_End):
            index = 0 if event.keyval == Gdk.KEY_Home else len(keys) - 1
        elif event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Right, Gdk.KEY_Down):
            index = (keys.index(key) + (-1 if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up) else 1)) % len(keys)
        else:
            return False
        self.buttons[keys[index]].set_active(True)
        self.buttons[keys[index]].grab_focus()
        return True
