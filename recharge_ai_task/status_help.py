"""Readable, keyboard-accessible continuation rules with theme-aware badges."""
from html import escape
from gi.repository import Gdk, GLib, Gtk
from .status_display import GOAL_STATES, TASK_STATES, continuation_allowed, status_rows, status_colors


def badge_colors(widget):
    colors = status_colors(widget)
    return colors["success"], colors["error"]


def status_markup(value, *, goal=False, widget=None):
    colors = badge_colors(widget) if widget is not None else ("#137333","#b3261e")
    kind = "Goal" if goal else "Task"
    detail = (GOAL_STATES if goal else TASK_STATES).get(value,(None,"Unrecognized status: allowed by default."))[1]
    lines = [f"<b>{kind} statuses · {escape(value)}</b>",escape(detail)]
    for label,manual in (("Automatic Goal",False),("Send now Goal",True)):
        allowed = continuation_allowed(value,goal=goal,manual=manual)
        text = "✓ Continue" if allowed else "✕ Skip / unavailable"
        lines.append(f'{label}: <span foreground="{colors[0 if allowed else 1]}">{text}</span>')
    lines.append("Message-only delivery does not use these status gates. Open ⓘ for the full list.")
    return "\n".join(lines)


class StatusInfoButton(Gtk.Button):
    def __init__(self, *, goal=False):
        super().__init__()
        self.goal = goal
        self.set_relief(Gtk.ReliefStyle.NONE)
        icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic",Gtk.IconSize.MENU)
        icon.set_pixel_size(14)
        self.set_image(icon)
        self.set_always_show_image(True)
        kind = "Goal" if goal else "Task"
        self.get_accessible().set_name(kind + " continuation rules")
        self.set_tooltip_text(f"Hover for {kind.lower()} status rules; open details (Enter / Space)")
        self.connect("clicked",lambda *_: self.open())
        self.popover = None
        self.keyboard_open = False
        self.pinned = False
        self.hide_timer = None
        self.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.connect("enter-notify-event",self._hover)
        self.connect("leave-notify-event",self._leave)
        self.connect("destroy",self._cancel_hide)
        self.badges = []
        self.expanders = []
        self.connect("style-updated",self._recolor)

    def open(self, *, keyboard=True):
        if self.popover is None:
            self._build()
        self._cancel_hide()
        if not self.popover.get_visible():
            self.pinned = False
        table = self.get_ancestor(Gtk.TreeView)
        if table is not None:
            self.popover.set_relative_to(table)
            x, y = self.translate_coordinates(table, 0, 0)
            rectangle = Gdk.Rectangle()
            rectangle.x = min(max(0, x), max(0, table.get_allocated_width() - self.get_allocated_width()))
            rectangle.y = max(0, y)
            rectangle.width = self.get_allocated_width()
            rectangle.height = self.get_allocated_height()
            self.popover.set_pointing_to(rectangle)
        if self.popover.get_visible() and self.keyboard_open != keyboard:
            self.popover.hide()
        self.keyboard_open = keyboard
        self.popover.set_modal(keyboard)
        self._recolor()
        self.popover.show_all()
        self.popover.popup()
        if keyboard:
            self.close_button.grab_focus()

    def bind_column(self,column):
        # TreeView's header button receives pointer events over its child
        # widgets. Handle the info region there, before a press can sort.
        header=column.get_button()
        header.add_events(Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        header.connect("motion-notify-event",self._header_motion)
        header.connect("enter-notify-event",self._header_motion)
        header.connect("leave-notify-event",self._leave)
        header.connect("button-press-event",self._header_press)

    @staticmethod
    def _widget_contains(widget, x, y):
        if widget is None or not widget.get_visible():
            return False
        root = widget.get_toplevel()
        if root.get_window() is None:
            return False
        position = widget.translate_coordinates(root, 0, 0)
        if position is None:
            return False
        _, origin_x, origin_y = root.get_window().get_origin()
        origin_x += position[0]
        origin_y += position[1]
        return (origin_x <= x < origin_x + widget.get_allocated_width() and
                origin_y <= y < origin_y + widget.get_allocated_height())

    def _contains(self, event):
        return self._widget_contains(self, event.x_root, event.y_root)

    def _pointer_inside(self):
        pointer = self.get_display().get_default_seat().get_pointer()
        if pointer is None:
            return False
        _, x, y = pointer.get_position()
        return self._widget_contains(self, x, y) or self._widget_contains(self.popover, x, y)

    def _header_motion(self,_widget,event):
        if self._contains(event):
            self._hover()
        else:
            self._leave()
        return False

    def _header_press(self,_widget,event):
        if self._contains(event):
            self.open(keyboard=False)
            self._pin()
            return True
        return False

    def _hover(self,*_):
        self._cancel_hide()
        if self.popover is None or not self.popover.get_visible():
            self.open(keyboard=False)
        return False

    def _cancel_hide(self,*_):
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer=None

    def _pin(self, *_):
        if self.popover is not None and self.popover.get_visible():
            self.pinned = True
            self._cancel_hide()

    def _close(self, *_):
        self._cancel_hide()
        self.pinned = False
        self.keyboard_open = False
        if self.popover is not None:
            self.popover.popdown()

    def _leave(self, _widget=None, event=None):
        # Crossing into a child expander or label is still inside this popover.
        if event is not None and event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._cancel_hide()
        if not self.keyboard_open and not self.pinned:
            def hide():
                self.hide_timer = None
                if not self.keyboard_open and not self.pinned and not self._pointer_inside():
                    self._close()
                return False
            self.hide_timer = GLib.timeout_add(700, hide)
        return False

    def _recolor(self,*_):
        colors = badge_colors(self)
        for label,allowed in self.badges:
            text = "✓ Continue" if allowed else "✕ Skip"
            label.set_markup(f'<span foreground="{colors[0 if allowed else 1]}">{text}</span>')
    def _build(self):
        self.popover = Gtk.Popover.new(self)
        self.popover.set_position(Gtk.PositionType.BOTTOM)
        self.popover.set_constrain_to(Gtk.PopoverConstraint.WINDOW)
        self.popover.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
        self.popover.connect("enter-notify-event",lambda *_: self._cancel_hide())
        self.popover.connect("leave-notify-event",self._leave)
        self.connect("destroy",lambda *_: self.popover.destroy())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,margin=12)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b>" + ("Goal" if self.goal else "Task") + " statuses · continuation rules</b>")
        box.pack_start(title,False,False,0)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC)
        scroll.connect("scroll-event", lambda *_: self._pin() or False)
        scroll.set_propagate_natural_height(True)
        scroll.set_min_content_height(160)
        scroll.set_max_content_height(380)
        grid = Gtk.Grid(column_spacing=12,row_spacing=10)
        for column,text in enumerate(("Status","Automatic Goal","Send now Goal")):
            label=Gtk.Label(xalign=0)
            label.set_markup("<b>"+text+"</b>")
            grid.attach(label,column,0,1,1)
        for index,(value,automatic,manual,detail) in enumerate(status_rows(goal=self.goal),1):
            expander=Gtk.Expander(label="<b>"+escape(value)+"</b>")
            expander.set_use_markup(True)
            expander.connect("notify::expanded", self._pin)
            expander.set_tooltip_text("Expand this status explanation (Space / Enter)")
            explanation=Gtk.Label(label=detail,xalign=0)
            explanation.set_line_wrap(True)
            explanation.set_max_width_chars(38)
            expander.add(explanation)
            self.expanders.append(expander)
            grid.attach(expander,0,index,1,1)
            for column,allowed in ((1,automatic),(2,manual)):
                badge=Gtk.Label(xalign=0,valign=Gtk.Align.START)
                grid.attach(badge,column,index,1,1)
                self.badges.append((badge,allowed))
        scroll.add(grid)
        box.pack_start(scroll,True,True,0)
        note=Gtk.Label(label="Green ✓ allows the Goal action; red ✕ excludes it.\nNew nonempty statuses are allowed by default.\nMessage-only ignores these status gates. Quota, limits and identity checks still apply.",xalign=0)
        note.set_line_wrap(True)
        note.set_max_width_chars(66)
        box.pack_start(note,False,False,0)
        self.close_button=Gtk.Button(label="Close")
        self.close_button.set_tooltip_text("Close status rules (Enter or Escape)")
        self.close_button.get_style_context().add_class("suggested-action")
        self.close_button.connect("clicked", self._close)
        box.pack_end(self.close_button,False,False,0)
        self.popover.add(box)
        self.rules_scroll=scroll
        self.popover.connect("key-press-event",self._scroll_keys)

    def _scroll_keys(self,_widget,event):
        if event.keyval == Gdk.KEY_Escape:
            self._close()
            return True
        adjustment=self.rules_scroll.get_vadjustment()
        steps={Gdk.KEY_Up:-40,Gdk.KEY_Down:40,
               Gdk.KEY_Page_Up:-adjustment.get_page_increment(),Gdk.KEY_Page_Down:adjustment.get_page_increment()}
        if event.keyval not in steps:
            return False
        adjustment.set_value(max(adjustment.get_lower(),min(adjustment.get_upper()-adjustment.get_page_size(),
                                                           adjustment.get_value()+steps[event.keyval])))
        return True
