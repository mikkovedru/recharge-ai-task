"""A scrolling editor with an explicit mouse/keyboard corner resize handle."""
from gi.repository import Gdk, GObject, Gtk


class ResizableEditor(Gtk.Overlay):
    __gsignals__ = {"resized": (GObject.SignalFlags.RUN_LAST, None, ())}

    def __init__(self, content, *, height=90):
        super().__init__()
        self.content = content
        self.set_valign(Gtk.Align.START)
        self.set_hexpand(True)
        self.desired_size = [-1, height]
        self.add(content)
        self.drag = None
        self.handle = Gtk.DrawingArea()
        self.handle.set_size_request(18,18)
        self.handle.set_halign(Gtk.Align.END)
        self.handle.set_valign(Gtk.Align.END)
        self.handle.set_can_focus(True)
        self.handle.set_tooltip_text("Resize this message editor by dragging the corner (Arrow keys when focused)")
        self.handle.get_accessible().set_name("Resize message editor")
        self.handle.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                               Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK)
        self.handle.connect("draw",self._draw)
        self.handle.connect("enter-notify-event",self._cursor)
        self.handle.connect("button-press-event",self._press)
        self.handle.connect("motion-notify-event",self._motion)
        self.handle.connect("button-release-event",self._release)
        self.handle.connect("key-press-event",self._key)
        self.add_overlay(self.handle)

    @staticmethod
    def _draw(widget,cr):
        color=widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        cr.set_source_rgba(color.red,color.green,color.blue,color.alpha)
        cr.set_line_width(1.5)
        for offset in (4,8,12):
            cr.move_to(17-offset,17)
            cr.line_to(17,17-offset)
        cr.stroke()
        if widget.has_focus():
            Gtk.render_focus(widget.get_style_context(),cr,0,0,18,18)
        return False

    @staticmethod
    def _cursor(widget,*_):
        if widget.get_window():
            widget.get_window().set_cursor(Gdk.Cursor.new_for_display(widget.get_display(),Gdk.CursorType.BOTTOM_RIGHT_CORNER))
        return False

    def editor_size(self):
        return list(self.desired_size)

    def restore_size(self,width,height):
        self.set_halign(Gtk.Align.FILL if width == -1 else Gtk.Align.START)
        self.desired_size = [width, max(48, height)]
        self.queue_resize()

    def do_get_preferred_width(self):
        minimum, natural = Gtk.Overlay.do_get_preferred_width(self)
        return minimum, max(minimum, self.desired_size[0] if self.desired_size[0] != -1 else natural)

    def do_get_preferred_height(self):
        minimum, _natural = Gtk.Overlay.do_get_preferred_height(self)
        return minimum, max(minimum, self.desired_size[1])

    def do_get_preferred_height_for_width(self, width):
        return self.do_get_preferred_height()

    def _bounds(self):
        parent=self.get_parent()
        width=parent.get_allocated_width() if parent else self.get_allocated_width()
        height=max(80,self.get_toplevel().get_allocated_height()//2)
        branch=self
        overhead=0
        while parent is not None:
            if isinstance(parent,Gtk.Box):
                others=[w for w in parent.get_children() if w is not branch and w.get_visible()]
                if parent.get_orientation()==Gtk.Orientation.VERTICAL:
                    overhead+=sum(w.get_preferred_height()[0] for w in others)+parent.get_spacing()*len(others)
                elif branch is self:
                    width-=sum(w.get_preferred_width()[0] for w in others)+parent.get_spacing()*len(others)
            if isinstance(parent,Gtk.Paned) and parent.get_orientation()==Gtk.Orientation.VERTICAL:
                other=parent.get_child2() if parent.get_child1() is branch else parent.get_child1()
                height=max(48,parent.get_allocated_height()-overhead-other.get_preferred_height()[0]-8)
                break
            branch,parent=parent,parent.get_parent()
        return max(100,width),max(48,height)

    def resize_to(self,width,height):
        max_width,max_height=self._bounds()
        self.restore_size(min(max_width,max(100,int(width))),min(max_height,max(48,int(height))))
        self.emit("resized")

    def _press(self,_widget,event):
        if event.button != 1:
            return False
        self.handle.grab_focus()
        self.drag=(event.x_root,event.y_root,self.get_allocated_width(),self.get_allocated_height())
        self.handle.grab_add()
        return True

    def _motion(self,_widget,event):
        if self.drag is None:
            return False
        x,y,width,height=self.drag
        self.resize_to(width+event.x_root-x,height+event.y_root-y)
        return True

    def _release(self,_widget,event):
        if event.button==1 and self.drag is not None:
            self.drag=None
            self.handle.grab_remove()
            return True
        return False

    def _key(self,_widget,event):
        steps={Gdk.KEY_Left:(-12,0),Gdk.KEY_Right:(12,0),Gdk.KEY_Up:(0,-12),Gdk.KEY_Down:(0,12)}
        if event.keyval not in steps:
            return False
        dx,dy=steps[event.keyval]
        self.resize_to(self.get_allocated_width()+dx,self.get_allocated_height()+dy)
        return True
