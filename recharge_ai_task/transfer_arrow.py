"""A taller transfer chevron within the existing native icon/button request."""
from gi.repository import Gtk


class TransferArrow(Gtk.Image):
    def __init__(self, icon_name="go-next-symbolic"):
        super().__init__(icon_name=icon_name, icon_size=Gtk.IconSize.BUTTON)

    def do_draw(self, cr):
        # Reserve the unchanged native icon request; the button paints the
        # glyph across its available height instead of enlarging that request.
        return True


class TransferButton(Gtk.Button):
    def __init__(self):
        super().__init__()
        self.set_image(TransferArrow())

    def draw_glyph(self, cr):
        image = self.get_image()
        if not isinstance(image, TransferArrow):
            return
        width, height = self.get_allocated_width(), self.get_allocated_height()
        color = self.get_style_context().get_color(self.get_state_flags())
        cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
        cr.set_line_width(2)
        cr.set_line_cap(1)
        cr.set_line_join(1)
        half_width = min(6, (width-10)/2)
        half_height = min(11, (height-8)/2)
        left, right = width/2-half_width, width/2+half_width
        start, tip = (right, left) if image.get_icon_name()[0] == "go-previous-symbolic" else (left, right)
        cr.move_to(start, height/2-half_height)
        cr.line_to(tip, height/2)
        cr.line_to(start, height/2+half_height)
        cr.stroke()

    def do_draw(self, cr):
        Gtk.Button.do_draw(self, cr)
        self.draw_glyph(cr)
        return False
