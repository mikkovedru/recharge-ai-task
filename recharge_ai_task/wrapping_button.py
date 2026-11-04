"""GTK buttons measured at their available caption width, rather than its minimum."""
from gi.repository import Gtk


class WrappingButton(Gtk.Button):
    @staticmethod
    def _label(widget):
        if isinstance(widget, Gtk.Label):
            return widget
        if isinstance(widget, Gtk.Container):
            for child in widget.get_children():
                result = WrappingButton._label(child)
                if result is not None:
                    return result
        return None

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_get_preferred_height_for_width(self, width):
        label = self._label(self.get_child())
        if label is None:
            return Gtk.Button.do_get_preferred_height_for_width(self, width)
        # Retain the theme's icon, border and padding measurements. GtkButton's
        # default calculation asks its alignment child for the label's minimum
        # width, making a one-line caption reserve several lines of height.
        base_width = Gtk.Button.do_get_preferred_width(self)[0]
        horizontal_inset = max(0, base_width - label.get_preferred_width()[0])
        icon = self.get_image()
        icon_height = icon.get_preferred_height()[0] if icon is not None and self.get_always_show_image() else 0
        base_height = Gtk.Button.do_get_preferred_height(self)[0]
        vertical_inset = max(0, base_height - max(label.get_preferred_height()[0], icon_height))
        text_height = label.get_preferred_height_for_width(max(1, width - horizontal_inset))[0]
        height = max(icon_height, text_height) + vertical_inset
        return height, height

    def do_get_preferred_height(self):
        width = self.get_allocated_width()
        if width <= 1:
            width = Gtk.Button.do_get_preferred_width(self)[1]
        return self.do_get_preferred_height_for_width(width)
