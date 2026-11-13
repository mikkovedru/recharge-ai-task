"""Compact, keyboard-accessible provider buttons shared by dashboard sections."""
from gi.repository import Gdk, GObject, Gtk
from .status_display import status_colors
from .config import PROVIDER_SHORT_NAMES

PROVIDER_NAMES = {'all': 'All', **PROVIDER_SHORT_NAMES}


class ProviderNotice(Gtk.Box):
    """A real themed question/exclamation icon inside neutral round brackets."""
    def __init__(self):
        super().__init__(spacing=0)
        self.icon = Gtk.Image()
        self.icon.set_pixel_size(14)
        for child in (Gtk.Label(label="("), self.icon, Gtk.Label(label=")")):
            self.pack_start(child, False, False, 0)
        self.show_all()
        self.set_no_show_all(True)
        self.hide()

    def update(self, state):
        visible = state in ("warning", "error")
        if visible and getattr(self, 'notice_state', None) != state:
            self.icon.set_from_icon_name("dialog-question-symbolic" if state == "warning" else "dialog-warning-symbolic", Gtk.IconSize.MENU)
            self.icon.get_accessible().set_name("Warning" if state == "warning" else "Error")
        self.notice_state = state
        self.set_visible(visible)


class ProviderButtons(Gtk.FlowBox):
    __gsignals__ = {'changed': (GObject.SignalFlags.RUN_FIRST, None, ())}

    def __init__(self, *, active='all', purpose='Filter visible items; saved recipients and monitoring stay unchanged', include_all=True):
        super().__init__()
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_min_children_per_line(4)
        self.set_max_children_per_line(len(PROVIDER_NAMES))
        self.set_row_spacing(2)
        self.set_column_spacing(2)
        self.get_style_context().add_class('provider-buttons')
        self.names = PROVIDER_NAMES if include_all else PROVIDER_SHORT_NAMES
        self.fallback = next(iter(self.names))
        self.buttons = {}
        self.purpose = purpose
        self.palette = None
        self.css = Gtk.CssProvider()
        self.get_style_context().add_provider_for_screen(self.get_screen(), self.css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.connect('style-updated', self._colors)
        self.connect('destroy', lambda *_: Gtk.StyleContext.remove_provider_for_screen(self.get_screen(), self.css))
        group = None
        for key, caption in self.names.items():
            button = Gtk.RadioButton.new_with_label_from_widget(group, caption)
            group = group or button
            button.set_mode(False)
            label = button.get_child()
            button.caption = label
            button.remove(label)
            content = Gtk.Box(spacing=3)
            button.status_image = Gtk.Image()
            button.status_image.set_no_show_all(True)
            button.status_image.set_pixel_size(14)
            button.notice = ProviderNotice()
            content.pack_start(button.status_image, False, False, 0)
            content.pack_start(label, False, False, 0)
            content.pack_start(button.notice, False, False, 0)
            button.add(content)
            button.set_tooltip_text(f'{caption}: {purpose} (Left / Right, Home / End)' if purpose else caption)
            button.get_accessible().set_name(f'{caption} providers')
            button.connect('toggled', self._changed)
            button.connect('key-press-event', self._keys, key)
            self.add(button)
            button.get_parent().set_can_focus(False)
            self.buttons[key] = button
        self.set_active_id(active)

    def _colors(self, *_):
        colors = status_colors(self)
        palette = tuple(colors.values())
        if palette == self.palette:
            return
        self.palette = palette
        self.css.load_from_data((
            ".provider-buttons flowboxchild { padding: 0; }"
            ".provider-buttons button { padding: 2px 5px; min-width: 0; min-height: 16px; }"
            f".provider-enabled image {{ color: {colors['success']}; }}"
            f".provider-error image {{ color: {colors['error']}; }}"
            f".provider-warning image {{ color: {colors['warning']}; }}"
            ".provider-off image { opacity: .6; }").encode())

    def set_status(self, provider, state, detail, *, installed=True):
        button = self.buttons[provider]
        if getattr(button, 'provider_state', None) != state:
            context = button.get_style_context()
            for value in ('enabled', 'off', 'warning', 'error'):
                context.remove_class('provider-' + value)
            context.add_class('provider-' + state)
            button.status_image.set_from_icon_name('media-playback-start-symbolic' if state=='enabled' else 'media-playback-stop-symbolic', Gtk.IconSize.MENU)
            button.status_image.hide()
            button.notice.update(state)
            button.provider_state = state
        button.set_sensitive(installed)
        if not installed and button.get_active():
            self.set_active_id(self.fallback)
        button.get_accessible().set_name(PROVIDER_NAMES[provider] + ": " + (state if installed else 'not installed'))
        tooltip = PROVIDER_NAMES[provider] + ': ' + detail
        if self.purpose:
            tooltip += '\n' + self.purpose + ' (Left / Right, Home / End)'
        if not installed:
            tooltip += '\nNo installed executable or supported running app detected. Saved history may still be visible under All.'
        if button.get_tooltip_text() != tooltip:
            button.set_tooltip_text(tooltip)

    def set_counts(self, providers):
        """Count recipients independently of the currently visible category."""
        providers = list(providers)
        for key, button in self.buttons.items():
            count = len(providers) if key == 'all' else providers.count(key)
            button.caption.set_text(f'{PROVIDER_NAMES[key]} ({count})')
            button.get_accessible().set_name(f'{PROVIDER_NAMES[key]}: {count} recipients')
        self.set_visible_providers(providers)

    def set_visible_providers(self, providers):
        """Keep All available and hide the complete FlowBox slot for empty categories."""
        visible = {'all', *providers}
        for key, button in self.buttons.items():
            slot = button.get_parent()
            slot.set_no_show_all(key not in visible)
            slot.set_visible(key in visible)
        if self.get_active_id() not in visible:
            self.set_active_id(self.fallback)

    def _changed(self, button):
        if button.get_active():
            self.emit('changed')

    def get_active_id(self):
        return next((key for key, button in self.buttons.items() if button.get_active()), self.fallback)

    def set_active_id(self, key):
        selected = key if key in self.buttons else self.fallback
        if not self.buttons[selected].get_sensitive() or self.buttons[selected].get_parent().get_no_show_all():
            selected = self.fallback
        self.buttons[selected].set_active(True)

    def _keys(self, _button, event, key):
        keys = [key for key, button in self.buttons.items()
                if button.get_sensitive() and not button.get_parent().get_no_show_all()]
        if not keys:
            return False
        if event.keyval in (Gdk.KEY_Home, Gdk.KEY_End):
            index = 0 if event.keyval == Gdk.KEY_Home else len(keys) - 1
        elif event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_Right, Gdk.KEY_Down):
            index = (keys.index(key) + (-1 if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up) else 1)) % len(keys)
        else:
            return False
        direction = -1 if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Up, Gdk.KEY_End) else 1
        for _ in keys:
            if self.buttons[keys[index]].get_sensitive():
                break
            index = (index + direction) % len(keys)
        self.buttons[keys[index]].set_active(True)
        self.buttons[keys[index]].grab_focus()
        return True
