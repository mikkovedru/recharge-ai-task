"""Editable target plans, effective messages and continuation allowances."""
from dataclasses import replace
from uuid import uuid4
from gi.repository import GLib, Gtk, Pango

from .provider_ui import ProviderButtons, PROVIDER_NAMES
from .wrapping_button import WrappingButton
from .transfer_arrow import TransferButton
from .config import AppConfig
from .resizable_editor import ResizableEditor
from .delivery_policy import Usage, UsageLedger, effective_limit, effective_message
from .recipient_readiness import recipient_readiness
from .recipient_readiness import target_health
from .status_display import status_colors
from .status_display import draw_target_border


class ActionFlowBoxChild(Gtk.FlowBoxChild):
    """Request height for the width GTK actually assigns to the action."""
    def do_get_preferred_height_for_width(self, width):
        button = self.get_child()
        allocated = button.get_allocated_width()
        return button.get_preferred_height_for_width(allocated if allocated > 1 else width)

    def do_get_preferred_height(self):
        return self.do_get_preferred_height_for_width(self.get_allocated_width())


class LimitControl(Gtk.Box):
    def __init__(self, changed, *, inherit=False, off=False):
        super().__init__(spacing=4)
        self.updating = False
        if off:
            self.get_style_context().add_class("action-limit")
        self.inherit = inherit
        self.number = Gtk.SpinButton.new_with_range(0, 1000000, 1)
        self.number.set_value(1)
        self.number.set_tooltip_text("Maximum actions since the last count reset; 0 disables the action (Up / Down)")
        self.number.set_width_chars(4)
        self.unlimited = Gtk.ToggleButton(label="∞")
        self.limited = Gtk.ToggleButton(label="1")
        self.unlimited.get_accessible().set_name("Unlimited")
        self._size_infinity(self.unlimited)
        self.unlimited.set_tooltip_text("Use an unlimited allowance for this target (Enter / Space)")
        self.limited.set_tooltip_text("Use a fixed allowance; click to edit its number (Enter / Space)")
        self.last_value = None
        self.modes = {}
        if off:
            self.off = Gtk.ToggleButton(label="Off")
            self.off.get_style_context().add_class("action-off")
            self.off.set_tooltip_text("Do not send this action to this target (Enter / Space)")
            self.modes["off"] = self.off
        if inherit:
            self.default = Gtk.ToggleButton(label="Global default")
            self.default.set_tooltip_text("Inherit the global limit, including future changes (Enter / Space)")
            self.modes["default"] = self.default
        self.modes.update(unlimited=self.unlimited, limited=self.limited)
        linked = Gtk.Box()
        linked.get_style_context().add_class("linked")
        for kind, button in self.modes.items():
            linked.pack_start(button, False, False, 0)
            button.connect("clicked", lambda _button, key=kind: self._mode(key, changed))
        self.pack_start(linked, False, False, 0)
        self.number_popover = Gtk.Popover.new(self.limited)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=8)
        content.pack_start(Gtk.Label(label="Maximum actions per target:"), False, False, 0)
        content.pack_start(self.number, False, False, 0)
        self.number_popover.add(content)
        self.number.connect("value-changed", lambda *_: self._changed(changed))
        self.set_value(None)

    def _mode(self, kind, changed):
        if self.updating:
            return
        if self.enabled():
            self.last_value = self.value()
        self._select(kind)
        if kind != "off":
            self.last_value = self.value()
        changed()
        if kind == "limited":
            self.number_popover.show_all()
            self.number_popover.popup()
            self.number.grab_focus()

    def _select(self, kind):
        self.updating = True
        try:
            for key, button in self.modes.items():
                button.set_active(key == kind)
        finally:
            self.updating = False

    def _changed(self, changed):
        self.limited.set_label(str(self.number.get_value_as_int()))
        if not self.updating:
            changed()

    def enabled(self):
        return not hasattr(self, "off") or not self.off.get_active()

    @staticmethod
    def _size_infinity(button):
        text = GLib.markup_escape_text(button.get_label())
        button.get_child().set_markup(text.replace("∞", "<span size='x-large'>∞</span>"))

    def inherited_value(self, value):
        if self.inherit:
            self.default.set_label("Global default (" + ("∞" if value is None or value == -1 else str(value)) + ")")
            self._size_infinity(self.default)

    def value(self):
        if not self.enabled():
            return self.last_value
        if self.limited.get_active():
            return self.number.get_value_as_int()
        return -1 if self.inherit and self.unlimited.get_active() else None

    def set_value(self, value, *, enabled=True):
        self.updating = True
        try:
            self.last_value = value
            kind = "default" if value is None and self.inherit else "unlimited" if value is None or value == -1 else "limited"
            if kind == "limited":
                self.number.set_value(value)
            self.limited.set_label(str(self.number.get_value_as_int()))
            for key, button in self.modes.items():
                button.set_active(key == (kind if enabled else "off"))
        finally:
            self.updating = False


def wrapped(text=""):
    label = Gtk.Label(label=text, xalign=0)
    label.set_line_wrap(True)
    label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_max_width_chars(48)
    label.set_selectable(False)
    return label


class RecipientPanel(Gtk.Box):
    def __init__(self, picker):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.picker = picker
        self.updating = False
        self.rows = {}
        self.selected_keys = set()
        self.selected_key = None
        self.selection_initialized = False
        self.ledger_error = ""
        self.ledger = None
        self.last_usage = {}
        self.status_css = Gtk.CssProvider()
        self.status_palette = None
        self.get_style_context().add_provider_for_screen(self.get_screen(), self.status_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION+1)
        self.connect("style-updated", self._recolor_status)
        self.connect("destroy", lambda *_: Gtk.StyleContext.remove_provider_for_screen(self.get_screen(), self.status_css))
        self._recolor_status()
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .target-passive { background-color: mix(@theme_base_color, @theme_bg_color, .55); }
            .target-passive .target-title, .target-passive .target-preview {
                color: mix(@theme_text_color, @theme_base_color, .20); opacity: 1; }
            .target-actions-off .target-title { font-style: normal; }
            .target-passive-badge { background-color: alpha(@theme_fg_color, .12);
                color: @theme_text_color; border: 0;
                border-radius: 3px; padding: 0 4px; font-size: .85em; }
            .target-row { border-left: 4px solid transparent; }
            .target-row:selected { background-color: @theme_selected_bg_color;
                color: @theme_selected_fg_color; }
            .target-row:selected label, .target-row:selected .target-title {
                color: @theme_selected_fg_color; opacity: 1; }
            .target-row:selected .target-passive-badge {
                color: @theme_selected_fg_color; background-color: alpha(@theme_selected_fg_color, .18); }
            .target-row button { padding: 3px; }
            flowbox.target-heading > flowboxchild { padding: 0; }
            button.target-info { background-image: none; background-color: @theme_base_color;
                border: 1px solid alpha(@theme_text_color, .5); border-radius: 4px; }
            button.target-info, button.target-info image { color: @theme_text_color; }
            button.target-info:hover { background-color: mix(@theme_base_color, @theme_selected_bg_color, .18); }
            button.target-info:focus { box-shadow: inset 0 0 0 2px @theme_selected_bg_color; }
        """)
        self.get_style_context().add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.heading_row = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE,
            column_spacing=8, row_spacing=4, min_children_per_line=1, max_children_per_line=2)
        self.heading_row.get_style_context().add_class("target-heading")
        self.heading = Gtk.Label(xalign=0)
        self.heading.set_markup("<b>Targets &amp; actions</b>")
        self.heading.set_tooltip_text("Targets & actions")
        self.provider_filter = ProviderButtons(compact=True, purpose="Filter this target list only; hidden actions remain enabled")
        self.provider_filter.connect("changed", self._filter_changed)
        # Treat the complete tab group as one item: it moves below the heading
        # only when both items' natural widths cannot fit together.
        for widget in (self.heading, self.provider_filter):
            self.heading_row.add(widget)
            widget.get_parent().set_can_focus(False)

        self.pack_start(self.heading_row, False, False, 0)
        self.default_prompt = LimitControl(self._defaults_changed)
        self.default_goal = LimitControl(self._defaults_changed)
        self.default_controls = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.default_controls.attach(Gtk.Label(label="Global limits per target:", xalign=0), 0, 0, 2, 1)
        for row, (caption, control) in enumerate((("Reactivate goals", self.default_goal), ("Send messages", self.default_prompt)), 1):
            self.default_controls.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            self.default_controls.attach(control, 1, row, 1, 1)
        self.reset_all = WrappingButton(label="Reset counts for all")
        self.reset_all.set_tooltip_text("Reset message and Goal allowances for every target (Enter / Space)")
        self.reset_all.connect("clicked", self._reset_all)
        self.default_controls.set_tooltip_text("Manual and automatic sends share each target's allowance. Counts survive restarts. Zero stops an action; use the reset buttons to renew allowances.")
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.MULTIPLE)
        self.list.set_filter_func(lambda row: self.provider_filter.get_active_id() in ("all", row.provider_id))
        self.list.set_activate_on_single_click(False)
        self.list.connect("selected-rows-changed", self._row_selected)
        self.list.connect("row-activated", self._row_activated)
        self.list.set_tooltip_text("Choose a target to edit it. Ctrl+click toggles selection; Shift+click selects a range. Double-click or Enter removes a target and turns both actions off (Up / Down)")
        self.list_scroller = Gtk.ScrolledWindow()
        self.list_scroller.set_shadow_type(Gtk.ShadowType.IN)
        self.list_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_scroller.set_size_request(250, 60)
        self.list_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.empty_label = Gtk.Label(label="No targets for this provider", margin=12, wrap=True)
        self.empty_label.set_no_show_all(True)
        self.list_container.pack_start(self.list, True, True, 0)
        self.list_container.pack_start(self.empty_label, False, False, 0)
        self.list_scroller.add(self.list_container)
        self.editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        actions = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, column_spacing=8, row_spacing=4)
        self.actions = actions
        actions.set_max_children_per_line(3)
        actions.set_min_children_per_line(1)
        actions.set_homogeneous(False)
        self.reset = WrappingButton(label="Reset current target's counts")
        self.reset.set_tooltip_text("Reset both used allowances for this target. This never sends anything.")
        self.reset.connect("clicked", self._reset)
        self._action_height_update = 0
        self.transfer = TransferButton()
        self.transfer.set_sensitive(False)
        self.transfer.connect("clicked", picker.transfer_recipient)
        send_group = Gtk.Box(spacing=6)
        send_group.pack_start(self.transfer, False, False, 0)
        send_group.pack_start(picker.send_button, True, True, 0)
        self.action_buttons = (picker.send_button, self.reset_all, self.reset)
        for button in self.action_buttons:
            button.compact_natural_width = True
            button.set_valign(Gtk.Align.CENTER)
            if button is not picker.send_button:
                self._wrap_reset_label(button)
            child = ActionFlowBoxChild()
            child.add(send_group if button is picker.send_button else button)
            actions.add(child)
            button.connect("size-allocate", self._queue_action_heights)
        self.editor.pack_start(actions, False, False, 0)
        overrides = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.prompt_limit = LimitControl(self._editor_changed, inherit=True, off=True)
        self.goal_limit = LimitControl(self._editor_changed, inherit=True, off=True)
        for row, (caption, control) in enumerate((("Reactivate goals", self.goal_limit), ("Send messages", self.prompt_limit))):
            overrides.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            overrides.attach(control, 1, row, 1, 1)
        self.editor.pack_start(overrides, False, False, 0)
        self.custom = Gtk.CheckButton(label="Use a custom message for this target")
        self.custom.set_tooltip_text("Override the default message for only this target; edits save automatically (Space)")
        self.custom.connect("toggled", self._custom_toggled)
        self.custom_row = Gtk.Box(spacing=6)
        self.custom_row.pack_start(self.custom, False, False, 0)
        self.save_status = Gtk.Image()
        self.save_status.set_can_focus(True)
        self.save_status_group = Gtk.Box(spacing=0)
        self.save_status_open = Gtk.Label(label="(")
        self.save_status_close = Gtk.Label(label=")")
        for widget in (self.save_status_open, self.save_status, self.save_status_close):
            self.save_status_group.pack_start(widget, False, False, 0)
        self.custom_row.pack_start(self.save_status_group, False, False, 0)
        self.editor.pack_start(self.custom_row, False, False, 0)
        self.once = Gtk.CheckButton(label="Send only once")
        self.once.set_tooltip_text("Use this custom message for one accepted send, then return to the default. Unconfirmed sends are not repeated (Space)")
        self.once.connect("toggled", self._once_changed)
        self.custom_row.pack_start(self.once, False, False, 0)
        self.message = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        preview_css = Gtk.CssProvider()
        preview_css.load_from_data(b"textview.inherited-message, textview.inherited-message text { background-color: @theme_bg_color; color: @theme_fg_color; }")
        self.message.get_style_context().add_provider(preview_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.message.set_left_margin(4)
        self.message.set_right_margin(4)
        self.message_buffer = self.message.get_buffer()
        self.message_buffer.connect("changed", self._message_changed)
        self.message_scroller = Gtk.ScrolledWindow()
        self.message_scroller.set_shadow_type(Gtk.ShadowType.IN)
        self.message_scroller.set_size_request(120, 48)
        self.message_scroller.add(self.message)
        self.message_resize = picker.window_layout.region("custom_message", ResizableEditor(self.message_scroller, height=100))
        self.editor.pack_start(self.message_resize, False, False, 0)
        self.editor_scroller = Gtk.ScrolledWindow()
        self.editor_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.editor_scroller.set_size_request(250, 120)
        self.editor_scroller.set_propagate_natural_height(True)
        self.editor_frame=Gtk.Frame()
        self.editor_frame.get_accessible().set_name("Selected target overrides")
        self.editor.set_border_width(6)
        self.editor_frame.add(self.editor)
        self.editor_scroller.add(self.editor_frame)
        self.split = picker.window_layout.pane("recipient_list_editor", self.list_scroller, self.editor_scroller, position="fit-second", resize_second=False)
        self.pack_start(self.split, True, True, 0)

    def _recolor_status(self, *_):
        colors = status_colors(self)
        found, selected = self.get_style_context().lookup_color("theme_selected_bg_color")
        palette = (*colors.values(), selected.to_string() if found else "")
        if palette == self.status_palette:
            return
        self.status_palette = palette
        text = "#142018" if colors["success"] != "#137333" else "#ffffff"
        def linear(value):
            return value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4
        luminance = sum(weight*linear(value) for weight,value in zip((.2126,.7152,.0722),(selected.red,selected.green,selected.blue))) if found else 0
        selected_text = "#000000" if luminance > .179 else "#ffffff"
        self.status_css.load_from_data(f"""
            .target-row:selected label, .target-row:selected .target-title {{ color: {selected_text}; }}
            .target-save-success {{ color: {colors['success']}; }}
            .target-save-warning {{ color: {colors['warning']}; }}
            .target-save-error {{ color: {colors['error']}; }}
            .action-limit button:checked {{ background-image: none; background-color: {colors['success']};
                color: {text}; border-color: {colors['success']}; }}
            .action-limit button.action-off:checked {{ background-color: {colors['error']}; border-color: {colors['error']}; }}
            .action-limit button:checked:hover {{ background-color: shade({colors['success']}, .88); }}
            .action-limit button.action-off:checked:hover {{ background-color: shade({colors['error']}, .88); }}
        """.encode())

    def _usage(self):
        try:
            if self.ledger is None:
                self.ledger = UsageLedger()
            usage = self.ledger.snapshot()
            self.last_usage = usage
            self.ledger_error = ""
            return usage
        except Exception as exc:
            error = f"Cannot read delivery allowances: {exc}"
            if error != self.ledger_error:
                self.picker._message(error, "error")
            self.ledger_error = error
            return {}

    def render(self):
        config = AppConfig.load()
        self.view_config = config
        usage = self._usage()
        self.updating = True
        try:
            self.default_prompt.set_value(config.prompt_limit)
            self.default_goal.set_value(config.goal_limit)
            selected = self.picker.selected
            for key in list(self.rows):
                if key not in selected:
                    self.list.remove(self.rows.pop(key))
            for key, target in selected.items():
                row = self.rows.get(key)
                if row is None:
                    row = Gtk.ListBoxRow()
                    row.key = key
                    row.provider_id = target.provider
                    row.expanded = False
                    row.preview_pending = False
                    row.custom_message = ""
                    row.get_style_context().add_class("target-row")
                    row.connect_after("draw", self._draw_health_border)
                    body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, margin=8)
                    header = Gtk.Box(spacing=6)
                    row.title, row.plan, row.allowance, row.preview = [wrapped() for _ in range(4)]
                    row.allowance.set_line_wrap(False)
                    row.allowance.set_ellipsize(Pango.EllipsizeMode.END)
                    row.title.set_line_wrap(False)
                    row.title.set_ellipsize(Pango.EllipsizeMode.END)
                    row.provider = Gtk.Label(label=PROVIDER_NAMES[target.provider], valign=Gtk.Align.START)
                    row.provider.set_tooltip_text("Provider: " + PROVIDER_NAMES[target.provider])
                    row.title.set_hexpand(True)
                    header.pack_start(row.title, True, True, 0)
                    row.passive_badge = Gtk.Label(label="\u23f8 Passive", valign=Gtk.Align.START)
                    row.passive_badge.get_style_context().add_class("target-passive-badge")
                    row.passive_badge.set_tooltip_text("Goal and Message are off. This chat stays in Targets & actions; nothing will be sent.")
                    row.passive_badge.set_no_show_all(True)
                    header.pack_start(row.passive_badge, False, False, 0)
                    header.pack_start(row.provider, False, False, 0)
                    row.allowance_box = Gtk.Box(spacing=6)
                    row.allowance.set_hexpand(True)
                    row.allowance_box.pack_start(row.allowance, True, True, 0)
                    row.preview_toggle = Gtk.Button(valign=Gtk.Align.START)
                    row.preview_toggle.set_relief(Gtk.ReliefStyle.NONE)
                    row.preview_toggle.get_style_context().add_class("target-info")
                    row.preview_toggle.set_image(Gtk.Image.new_from_icon_name("pan-down-symbolic", Gtk.IconSize.MENU))
                    row.preview_toggle.set_no_show_all(True)
                    row.preview_toggle.connect("clicked", self._toggle_preview, row)
                    row.allowance_box.pack_end(row.preview_toggle, False, False, 0)
                    row.allowance_box.connect("size-allocate", self._queue_preview, row)
                    row.preview.set_selectable(True)
                    row.preview.set_max_width_chars(-1)
                    row.preview.set_width_chars(1)
                    row.preview.set_no_show_all(True)
                    for label, name in ((row.title, "title"), (row.preview, "preview")):
                        label.get_style_context().add_class("target-" + name)
                    row.indicator = Gtk.Button(relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.START)
                    row.indicator.get_style_context().add_class("target-info")
                    row.indicator.set_image(Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.BUTTON))
                    row.details = Gtk.Popover.new(row.indicator)
                    row.explanation = wrapped()
                    row.explanation.set_margin_start(10)
                    row.explanation.set_margin_end(10)
                    row.explanation.set_margin_top(10)
                    row.explanation.set_margin_bottom(10)
                    row.details.add(row.explanation)
                    row.indicator.connect("clicked", lambda _button, current=row: self._show_details(current))
                    row.remove = Gtk.Button.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.BUTTON)
                    row.remove.get_style_context().add_class("target-info")
                    row.remove.get_accessible().set_name("Remove target")
                    row.remove.set_tooltip_text("Remove this target from Targets & actions and turn off both Goal and Message. Custom text and limits are retained. You can also double-click the row (Enter / Space)")
                    row.remove.connect("clicked", lambda _button, key=key: self.picker.remove_recipient(key))
                    icons = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.START)
                    icons.pack_start(row.indicator, False, False, 0)
                    icons.pack_start(row.remove, False, False, 0)
                    content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
                    outer = Gtk.Box(spacing=6)
                    outer.pack_start(content, True, True, 0)
                    outer.pack_start(icons, False, False, 0)
                    for widget in (header, row.plan, row.allowance_box, row.preview):
                        content.pack_start(widget, False, False, 0)
                    body.pack_start(outer, False, False, 0)
                    row.add(body)
                    self.list.add(row)
                    self.rows[key] = row
                    row.show_all()
                caption = " · ".join(part for part in (target.project_name, target.title) if part)
                row.title.set_markup("<b>" + GLib.markup_escape_text(caption) + "</b>")
                row.title.set_tooltip_text(caption)
                row.set_tooltip_text("\n".join(part for part in (caption, target.cwd, target.instance) if part))
                prompt, goal = target.signal_actions()
                row.passive_badge.set_visible(not (prompt or goal))
                context = row.get_style_context()
                if prompt or goal:
                    context.remove_class("target-actions-off")
                else:
                    context.add_class("target-actions-off")
                pl, gl = effective_limit(target, "prompt", config), effective_limit(target, "goal", config)
                pu, gu = usage.get((key, "prompt"), Usage()), usage.get((key, "goal"), Usage())
                message = effective_message(target, self.picker._prompt_text())
                row.automatic = recipient_readiness(target, config, usage, message, ledger_error=self.ledger_error)
                row.manual = recipient_readiness(target, config, usage, message, manual=True, ledger_error=self.ledger_error)
                row.health_ok = target_health(target, row.automatic)
                self._readiness(row)
                colors = status_colors(self)
                allowances, expanded_allowances, details = [], [], []
                for action, enabled, used, limit, override in (("Goal", goal, gu, gl, target.goal_limit),
                                                              ("Message", prompt, pu, pl, target.prompt_limit)):
                    if enabled:
                        caption = f"{action}: used {used.used} / " + ("∞" if limit is None else str(limit))
                        caption += " (override)" if override is not None else " (default)"
                        if used.uncertain:
                            caption += f" · {used.uncertain} unconfirmed"
                        text = GLib.markup_escape_text(caption).replace(action + ":", "<b>" + action + "</b>:", 1).replace("∞", "<span size='x-large'>∞</span>")
                        if limit is not None and used.used >= limit:
                            text = f"<span foreground='{colors['error']}' weight='bold'>⚠ {text}</span>"
                        elif used.uncertain:
                            text = f"<span foreground='{colors['warning']}'>⚠ {text}</span>"
                        expanded_text = text
                        if action == "Message" and target.custom_prompt is not None:
                            preview = " ".join(message.splitlines()) or "(empty)"
                            once = " (<b>once</b>)" if target.custom_prompt_once else ""
                            expanded_text += "    |    <b>Custom</b> message" + once + ":"
                            text = expanded_text + " " + GLib.markup_escape_text(preview)
                            caption += "    |    Custom message" + (" (once)" if once else "") + ": " + message
                        allowances.append(text)
                        expanded_allowances.append(expanded_text)
                        details.append(caption)
                row.allowance_collapsed = "\n".join(allowances)
                row.allowance_expanded = "\n".join(expanded_allowances)
                row.allowance.set_markup(row.allowance_expanded if row.expanded else row.allowance_collapsed)
                row.allowance_box.set_no_show_all(True)
                row.allowance_box.set_visible(bool(allowances))
                row.allowance.set_tooltip_text("\n".join(details))
                row.custom_message = message if prompt and target.custom_prompt is not None else ""
                if not row.custom_message:
                    row.expanded = False
                row.preview.set_text(row.custom_message)
                self._queue_preview(row.allowance_box, None, row)
            if self.selected_key not in selected:
                self.selected_key = None if self.selection_initialized else next(iter(selected), None)
            self.list.invalidate_filter()
            self.provider_filter.set_counts(target.provider for target in selected.values())
            self.selected_keys.intersection_update(selected)
            if self.selected_key is not None and not self.selected_keys:
                self.selected_keys.add(self.selected_key)
            self.list.unselect_all()
            for key in self.selected_keys:
                self.list.select_row(self.rows[key])
            self.empty_label.set_visible(not self._visible_rows())
            self._load_editor(config)
            self._update_reset_help()
        finally:
            self.updating = False

    def _visible_rows(self):
        provider = self.provider_filter.get_active_id()
        return [row for row in self.rows.values() if provider in ("all", row.provider_id)]

    def _filter_changed(self, *_):
        if not hasattr(self, "list"):
            return
        self.updating = True
        try:
            self.list.invalidate_filter()
            rows = self._visible_rows()
            current = self.rows.get(self.selected_key)
            current = current if current in rows else next(iter(rows), None)
            self.selected_key = current.key if current else None
            self.list.unselect_all()
            self.selected_keys = {current.key} if current else set()
            self.list.select_row(current)
            self.empty_label.set_visible(not rows)
            self._load_editor(AppConfig.load())
            self._update_reset_help()
        finally:
            self.updating = False

    def _queue_preview(self, _widget, _allocation, row):
        if row.preview_pending:
            return
        row.preview_pending = True
        def update():
            row.preview_pending = False
            if row.get_parent() is None:
                return False
            row.allowance.set_markup(row.allowance_expanded if row.expanded else row.allowance_collapsed)
            layout = row.allowance.get_layout().copy()
            # Measure the collapsed caption even while its message is expanded.
            layout.set_markup(row.allowance_collapsed, -1)
            layout.set_width(-1)
            layout.set_ellipsize(Pango.EllipsizeMode.NONE)
            overflow = layout.get_pixel_size()[0] > row.allowance_box.get_allocated_width()
            row.preview.set_visible(bool(row.custom_message and row.expanded))
            row.preview_toggle.set_visible(bool(row.custom_message and (row.expanded or overflow)))
            caption = "Shorten custom message" if row.expanded else "Expand custom message"
            icon = "pan-up-symbolic" if row.expanded else "pan-down-symbolic"
            if row.preview_toggle.get_image().get_icon_name()[0] != icon:
                row.preview_toggle.get_image().set_from_icon_name(icon, Gtk.IconSize.MENU)
            row.preview_toggle.get_accessible().set_name(caption)
            row.preview_toggle.set_tooltip_text(("Hide the full custom message" if row.expanded else "Show the full custom message") + " (Enter / Space)")
            return False
        GLib.idle_add(update)

    def _toggle_preview(self, _button, row):
        row.expanded = not row.expanded
        self._queue_preview(row.allowance_box, None, row)

    @staticmethod
    def _show_details(row):
        row.details.show_all()
        row.details.popup()

    def _readiness(self, row):
        colors = status_colors(self)
        def caption(action):
            name = "Message" if action.action == "prompt" else "Goal"
            reason = action.reason
            if action.ready:
                return name + " ready"
            return reason if reason.startswith(name) else name + ": " + reason
        def summary(readiness):
            if not readiness.actions:
                return ""
            parts = []
            for action in readiness.actions:
                if action.ready and not action.warning:
                    continue
                text = GLib.markup_escape_text(action.warning or caption(action))
                if action.state in {"blocked", "uncertain", "passive"}:
                    color = colors["error" if action.state == "blocked" else "warning"]
                    text = f"<span foreground='{color}'>⚠ {text}</span>"
                parts.append(text)
            return " · ".join(parts)
        automatic, manual = summary(row.automatic), summary(row.manual)
        lines = (["Automatic / Send now: " + automatic] if automatic and automatic == manual else
                 (["Automatic: " + automatic] if automatic else []) + (["Send now: " + manual] if manual else []))
        if not row.automatic.actions:
            lines = ["Goal and Message are off"]
        row.plan.set_markup("\n".join(lines))
        row.plan.set_no_show_all(True)
        row.plan.set_visible(bool(lines))
        context = row.get_style_context()
        if row.automatic.ready:
            context.remove_class("target-passive")
        else:
            context.add_class("target-passive")
        actions = (*row.automatic.actions, *row.manual.actions)
        warning = any(action.state in {"blocked", "uncertain"} or action.warning or
                      action.state == "passive" and not action.reason.startswith("Already active") for action in actions)
        passive = any(not action.ready for action in actions) or not actions
        icon = "dialog-warning-symbolic" if warning else "dialog-information-symbolic" if passive else "dialog-information-symbolic"
        row.indicator.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        row.indicator.set_no_show_all(True)
        row.indicator.set_visible(True)
        row.indicator.get_accessible().set_name("Target readiness: " +
            ("needs attention" if warning else "some actions passive" if passive else "ready"))
        detail = []
        for name, readiness in (("Automatic recovery", row.automatic), ("Send now", row.manual)):
            detail.append(name + ":")
            detail.extend("• " + caption(action) for action in readiness.actions)
            if not readiness.actions:
                detail.append("• No actions selected")
        notes = list(dict.fromkeys(action.warning for action in actions if action.warning))
        detail.extend(notes)
        detail.append("Preview uses the latest refresh and describes eligibility when quota is usable. Goal state, routing and allowances are verified at delivery.")
        explanation = "\n".join(detail)
        row.explanation.set_text(explanation)
        row.plan.set_tooltip_text(explanation)
        row.indicator.set_tooltip_text(explanation + "\nShow details (Enter / Space)")

    def refresh_health(self):
        runtime = self.picker.runtime or {}
        watch_on = bool(runtime.get("desktop_watch"))
        for key, row in self.rows.items():
            target = self.picker.selected.get(key)
            provider_error = self.picker.quota_errors.get(target.provider, "") if target else ""
            healthy = row.health_ok and not provider_error and not runtime.get("watch_error")
            row.health_level = ("success" if watch_on else "warning") if healthy else "error"
            context = row.get_style_context()
            for level in ("success", "warning", "error"):
                context.remove_class("health-" + level)
            context.add_class("health-" + row.health_level)

    def _draw_health_border(self, row, cr):
        draw_target_border(cr, self, 0, row.get_allocated_height(), getattr(row, "health_level", "error"), inset=3)
        return False

    def _row_selected(self, _list):
        if self.updating:
            return
        keys = {row.key for row in self.list.get_selected_rows()}
        added = keys - self.selected_keys
        self.selected_keys = keys
        if added:
            self.selected_key = next(row.key for row in self.list.get_selected_rows() if row.key in added)
        elif self.selected_key not in keys:
            self.selected_key = next((row.key for row in self.list.get_selected_rows()), None)
        self.selection_initialized = True
        self.updating = True
        try:
            if self.selected_key is not None:
                self.picker.highlight_recipient(self.selected_key)
            self._load_editor(AppConfig.load())
            self._update_reset_help()
        finally:
            self.updating = False

    def _row_activated(self, _list, row):
        if not self.updating:
            self.picker.remove_recipient(row.key)

    def select_recipient(self, key, *, preserve_selection=False):
        if self.updating:
            return
        self.updating = True
        self.selection_initialized = True
        try:
            self.selected_key = key if key in self.rows else None
            row = self.rows.get(self.selected_key)
            if not preserve_selection or self.selected_key not in self.selected_keys:
                self.list.unselect_all()
                self.selected_keys = {self.selected_key} if row else set()
                self.list.select_row(row)
            if row is not None:
                if not preserve_selection:
                    self.picker.highlight_recipient(row.key)
                y = row.translate_coordinates(self.list, 0, 0)[1]
                self.list_scroller.get_vadjustment().clamp_page(y, y + row.get_allocated_height())
            self._load_editor(AppConfig.load())
            self._update_reset_help()
        finally:
            self.updating = False

    def _load_editor(self, config):
        target = self.picker.selected.get(self.selected_key)
        for child in self.editor.get_children():
            if child is not self.actions:
                child.set_sensitive(target is not None)
        self.reset.set_sensitive(bool(self.selected_keys))
        state, detail = self.picker.custom_message_status(target)
        icon = {"saved": "emblem-ok-symbolic", "pending": "emblem-synchronizing-symbolic",
                "error": "dialog-error-symbolic", "unknown": "dialog-warning-symbolic", "default": "dialog-information-symbolic", "paused": "media-playback-pause-symbolic"}[state]
        level = "success" if state == "saved" else "error" if state in {"error", "paused"} else "warning"
        context = self.save_status.get_style_context()
        for old_level in ("success", "warning", "error"):
            context.remove_class("target-save-" + old_level)
        context.add_class("target-save-" + level)
        self.save_status.set_from_icon_name(icon, Gtk.IconSize.BUTTON)
        self.save_status.set_tooltip_text(detail)
        self.save_status_group.set_tooltip_text(detail)
        self.save_status.get_accessible().set_name("Custom message status: " + detail)
        self.prompt_limit.inherited_value(config.prompt_limit)
        self.goal_limit.inherited_value(config.goal_limit)
        if target is None:
            self.custom.set_active(False)
            self.once.set_active(False)
            self.prompt_limit.set_value(None, enabled=False)
            self.goal_limit.set_value(None, enabled=False)
            self.message_buffer.set_text("")
            self._set_custom_appearance(False)
            return
        self.prompt_limit.set_value(target.prompt_limit, enabled=target.send_prompt)
        self.goal_limit.set_value(target.goal_limit, enabled=target.send_goal)
        for kind, button in self.goal_limit.modes.items():
            button.set_sensitive(target.kind == "thread" or kind == "off")
        self.custom.set_active(target.custom_prompt is not None)
        self.once.set_active(bool(target.custom_prompt_once))
        self.once.set_sensitive(target.custom_prompt is not None)
        self._set_custom_appearance(target.custom_prompt is not None)
        text = effective_message(target, self.picker._prompt_text())
        current = self.message_buffer.get_text(*self.message_buffer.get_bounds(), True)
        if current != text:
            self.message_buffer.set_text(text)

    def _defaults_changed(self):
        if self.updating:
            return
        try:
            config = AppConfig.load()
            config.prompt_limit = self.default_prompt.value()
            config.goal_limit = self.default_goal.value()
            config.save()
            self.picker.config = config
            self.picker._summary()
            self.picker.poll_runtime()
        except Exception as exc:
            self.default_prompt.set_value(self.picker.config.prompt_limit)
            self.default_goal.set_value(self.picker.config.goal_limit)
            self.picker._message(f"Could not save default limits: {exc}", "error")

    def _editor_changed(self, *_):
        if self.updating:
            return
        target = self.picker.selected.get(self.selected_key)
        if target is None:
            return
        self.picker.update_recipient(replace(target, send_prompt=self.prompt_limit.enabled(), send_goal=self.goal_limit.enabled(),
            prompt_limit=self.prompt_limit.value(), goal_limit=self.goal_limit.value()))

    def _set_custom_appearance(self, enabled):
        self.once.set_sensitive(enabled)
        self.message.set_editable(enabled)
        self.message.set_cursor_visible(enabled)
        context = self.message.get_style_context()
        if enabled:
            context.remove_class("inherited-message")
        else:
            context.add_class("inherited-message")
        self.message.set_tooltip_text("Custom message for this target" if enabled else
            "Default message preview. Enable the custom message checkbox to edit this target's message.")

    def _custom_toggled(self, *_):
        if self.updating:
            return
        target = self.picker.selected.get(self.selected_key)
        if target is not None:
            self._set_custom_appearance(self.custom.get_active())
            self.picker.update_recipient(replace(target, custom_prompt=effective_message(target, self.picker._prompt_text()) if self.custom.get_active() else None,
                custom_prompt_once=str(uuid4()) if self.custom.get_active() and self.once.get_active() else ""))

    def _once_changed(self, *_):
        if self.updating:
            return
        target = self.picker.selected.get(self.selected_key)
        if target is not None and target.custom_prompt is not None:
            runtime = self.picker.runtime or {}
            if self.once.get_active() and (runtime.get("desktop_watch") or runtime.get("watch_requested")) and not runtime.get("one_use_messages"):
                self.updating = True
                self.once.set_active(False)
                self.updating = False
                self.picker._message("Restart the tray before enabling Send only once for an active watch.", "error")
                return
            self.picker.update_recipient(replace(target, custom_prompt_once=str(uuid4()) if self.once.get_active() else ""))

    def _message_changed(self, *_):
        if self.updating or not self.custom.get_active():
            return
        target = self.picker.selected.get(self.selected_key)
        if target is not None:
            self._set_custom_appearance(self.custom.get_active())
            self.picker.update_recipient(replace(target, custom_prompt=self.message_buffer.get_text(*self.message_buffer.get_bounds(), True),
                custom_prompt_once=str(uuid4()) if self.once.get_active() else ""))

    def _queue_action_heights(self, *_):
        if not self._action_height_update:
            self._action_height_update = GLib.idle_add(self._update_action_heights)

    def _update_action_heights(self):
        self._action_height_update = 0
        # FlowBox sizes each row independently. Measure the captions at their
        # allocated widths so buttons on different rows still match.
        height = max(WrappingButton.do_get_preferred_height_for_width(button, max(1, button.get_allocated_width()))[0]
                     for button in self.action_buttons)
        for button in self.action_buttons:
            if button.get_size_request().height != height:
                button.set_size_request(-1, height)
        return GLib.SOURCE_REMOVE

    @staticmethod
    def _wrap_reset_label(button):
        label = WrappingButton._label(button)
        label.set_line_wrap(True)
        label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(16)
        label.set_justify(Gtk.Justification.CENTER)

    def _update_reset_help(self):
        count = len(self.selected_keys)
        self.reset.set_label(f"Reset current targets' ({count}) counts" if count > 1 else "Reset current target's counts")
        self._wrap_reset_label(self.reset)
        for button, all_recipients in ((self.reset, False), (self.reset_all, True)):
            button.set_tooltip_text(self._reset_help(all_recipients))
            if not getattr(button, "reset_help_connected", False):
                button.connect("query-tooltip", self._reset_tooltip, all_recipients)
                button.reset_help_connected = True

    def _reset_tooltip(self, _button, _x, _y, _keyboard, tooltip, all_recipients):
        tooltip.set_text(self._reset_help(all_recipients))
        return True

    def _reset_help(self, all_recipients):
        usage = self._usage()
        if self.ledger_error:
            return self.ledger_error + " Counts cannot be previewed or reset safely until the ledger is readable."
        keys = ({key for key, _action in usage} | set(self.picker.selected)) if all_recipients else set(self.selected_keys)
        scope = "all stored targets (including hidden and removed targets with counts)" if all_recipients else "the selected targets only"
        lines = [f"Reset Goal and Message counts for {len(keys)} target(s): {scope}."]
        config = AppConfig.load()
        for key in sorted(keys):
            target = self.picker.preferences.get(key)
            name = " · ".join(part for part in (target.project_name, target.title, target.instance) if part) if target else key
            lines.append(name + (f" (ID: {target.id})" if target else ""))
            for action, label in (("goal", "Goal"), ("prompt", "Message")):
                old = usage.get((key, action), Usage())
                detail = f"  {label}: used {old.used} → 0; unconfirmed {old.uncertain} → 0."
                if target:
                    limit = effective_limit(target, action, config)
                    detail += " Allowance remains unlimited." if limit is None else f" Remaining {max(0, limit-old.used)} → {limit} of {limit}."
                lines.append(detail)
        lines.append("Limits, action choices and custom messages stay unchanged. Completed one-use messages are not rearmed. Nothing is sent. Live deliveries must finish first. (Enter / Space)")
        return "\n".join(lines)

    def _reset(self, *_):
        if not self.selected_keys:
            return
        try:
            (self.ledger or UsageLedger()).reset(self.selected_keys)
            self.picker._message(f"Counts reset for {len(self.selected_keys)} target(s). No signals sent.")
            self.render()
        except Exception as exc:
            self.picker._message(str(exc), "error")

    def _reset_all(self, *_):
        try:
            ledger = self.ledger or UsageLedger()
            ledger.reset({key for key, _action in ledger.snapshot()})
            self.picker._message("All target counts reset. No signals sent.")
            self.render()
        except Exception as exc:
            self.picker._message(str(exc), "error")
