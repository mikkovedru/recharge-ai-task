"""Editable recipient plans, effective messages and continuation allowances."""
from dataclasses import replace
from gi.repository import GLib, Gtk, Pango

from .config import AppConfig
from .resizable_editor import ResizableEditor
from .delivery_policy import Usage, UsageLedger, effective_limit, effective_message
from .recipient_readiness import recipient_readiness
from .status_display import status_colors


class LimitControl(Gtk.Box):
    def __init__(self, changed, *, inherit=False, off=False):
        super().__init__(spacing=4)
        self.updating = False
        self.inherit = inherit
        self.number = Gtk.SpinButton.new_with_range(0, 1000000, 1)
        self.number.set_value(1)
        self.number.set_tooltip_text("Maximum actions since the last count reset; 0 disables the action (Up / Down)")
        self.number.set_width_chars(4)
        self.unlimited = Gtk.ToggleButton(label="Unlimited")
        self.limited = Gtk.ToggleButton(label="1")
        self.unlimited.set_tooltip_text("Use an unlimited allowance for this recipient (Enter / Space)")
        self.limited.set_tooltip_text("Use a fixed allowance; click to edit its number (Enter / Space)")
        self.last_value = None
        self.modes = {}
        if off:
            self.off = Gtk.ToggleButton(label="Off")
            self.off.set_tooltip_text("Do not send this action to this recipient (Enter / Space)")
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
        content.pack_start(Gtk.Label(label="Maximum actions per recipient:"), False, False, 0)
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

    def inherited_value(self, value):
        if self.inherit:
            self.default.set_label("Global default (" + ("Unlimited" if value is None or value == -1 else str(value)) + ")")

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
        self.selected_key = None
        self.selection_initialized = False
        self.ledger_error = ""
        self.ledger = None
        css = Gtk.CssProvider()
        css.load_from_data(b"""
            .recipient-passive .recipient-title, .recipient-passive .recipient-identity,
            .recipient-passive .recipient-preview { opacity: .62; }
            .recipient-row:selected { background-color: mix(@theme_base_color, @theme_selected_bg_color, .24);
                color: @theme_text_color; box-shadow: inset 0 0 0 2px @theme_selected_bg_color; }
            .recipient-row:selected .recipient-title { opacity: 1; }
            .recipient-row button { padding: 3px; }
        """)
        self.get_style_context().add_provider_for_screen(self.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        heading = wrapped()
        heading.set_markup("<b>Recipients &amp; actions</b>")
        self.pack_start(heading, False, False, 0)
        self.default_prompt = LimitControl(self._defaults_changed)
        self.default_goal = LimitControl(self._defaults_changed)
        self.default_controls = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.default_controls.attach(Gtk.Label(label="Global limits per recipient:", xalign=0), 0, 0, 2, 1)
        for row, (caption, control) in enumerate((("Send messages", self.default_prompt), ("Reactivate goals", self.default_goal)), 1):
            self.default_controls.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            self.default_controls.attach(control, 1, row, 1, 1)
        self.reset_all = Gtk.Button(label="Reset all counts")
        self.reset_all.set_tooltip_text("Reset message and Goal allowances for every recipient (Enter / Space)")
        self.reset_all.set_valign(Gtk.Align.CENTER)
        self.reset_all.set_halign(Gtk.Align.END)
        self.reset_all.set_hexpand(False)
        self.reset_all.connect("clicked", self._reset_all)
        self.default_controls.set_tooltip_text("Manual and automatic sends share each recipient's allowance. Counts survive restarts. Zero stops an action; use Reset counts to renew allowances.")
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect("row-selected", self._row_selected)
        self.list.connect("row-activated", self._row_activated)
        self.list.set_tooltip_text("Choose a recipient to edit it and reveal the matching chat in the main list (Up / Down)")
        self.list_scroller = Gtk.ScrolledWindow()
        self.list_scroller.set_shadow_type(Gtk.ShadowType.IN)
        self.list_scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_scroller.set_size_request(250, 60)
        self.list_scroller.add(self.list)
        self.editor = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        actions = Gtk.Box(spacing=8)
        self.reset = Gtk.Button(label="Reset counts")
        self.reset.set_tooltip_text("Reset both used allowances for this recipient. This never sends anything.")
        self.reset.connect("clicked", self._reset)
        actions.pack_end(self.reset, False, False, 0)
        actions.pack_end(self.reset_all, False, False, 0)
        self.editor.pack_start(actions, False, False, 0)
        overrides = Gtk.Grid(column_spacing=6, row_spacing=4)
        self.prompt_limit = LimitControl(self._editor_changed, inherit=True, off=True)
        self.goal_limit = LimitControl(self._editor_changed, inherit=True, off=True)
        for row, (caption, control) in enumerate((("Send messages", self.prompt_limit), ("Reactivate goals", self.goal_limit))):
            overrides.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            overrides.attach(control, 1, row, 1, 1)
        self.editor.pack_start(overrides, False, False, 0)
        self.custom = Gtk.CheckButton(label="Use a custom message for this recipient")
        self.custom.set_tooltip_text("Override the default message for only this recipient; edits save automatically (Space)")
        self.custom.connect("toggled", self._custom_toggled)
        self.editor.pack_start(self.custom, False, False, 0)
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
        self.editor_frame.get_accessible().set_name("Selected recipient overrides")
        self.editor.set_border_width(6)
        self.editor_frame.add(self.editor)
        self.editor_scroller.add(self.editor_frame)
        self.split = picker.window_layout.pane("recipient_list_editor", self.list_scroller, self.editor_scroller, position="fit-second", resize_second=False)
        self.pack_start(self.split, True, True, 0)

    def _usage(self):
        try:
            if self.ledger is None:
                self.ledger = UsageLedger()
            usage = self.ledger.snapshot()
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
                    row.get_style_context().add_class("recipient-row")
                    body = Gtk.Box(spacing=6, margin=8)
                    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3, hexpand=True)
                    row.title, row.plan, row.allowance, row.preview = [wrapped() for _ in range(4)]
                    row.title.set_line_wrap(False)
                    row.title.set_ellipsize(Pango.EllipsizeMode.END)
                    for label in (row.title, row.plan, row.allowance, row.preview):
                        text.pack_start(label, False, False, 0)
                    for label, name in ((row.title, "title"), (row.preview, "preview")):
                        label.get_style_context().add_class("recipient-" + name)
                    row.indicator = Gtk.Button(relief=Gtk.ReliefStyle.NONE, valign=Gtk.Align.START)
                    row.indicator.set_image(Gtk.Image.new_from_icon_name("dialog-information-symbolic", Gtk.IconSize.BUTTON))
                    row.details = Gtk.Popover.new(row.indicator)
                    row.explanation = wrapped()
                    row.explanation.set_margin_start(10)
                    row.explanation.set_margin_end(10)
                    row.explanation.set_margin_top(10)
                    row.explanation.set_margin_bottom(10)
                    row.details.add(row.explanation)
                    row.indicator.connect("clicked", lambda _button, current=row: self._show_details(current))
                    body.pack_start(text, True, True, 0)
                    body.pack_start(row.indicator, False, False, 0)
                    row.add(body)
                    self.list.add(row)
                    self.rows[key] = row
                    row.show_all()
                caption = " · ".join(part for part in (target.project_name, target.title) if part)
                row.title.set_markup("<b>" + GLib.markup_escape_text(caption) + "</b>")
                row.title.set_tooltip_text(caption)
                row.set_tooltip_text("\n".join(part for part in (caption, target.cwd, target.instance) if part))
                prompt, goal = target.signal_actions()
                pl, gl = effective_limit(target, "prompt", config), effective_limit(target, "goal", config)
                pu, gu = usage.get((key, "prompt"), Usage()), usage.get((key, "goal"), Usage())
                message = effective_message(target, self.picker._prompt_text())
                row.automatic = recipient_readiness(target, config, usage, message, ledger_error=self.ledger_error)
                row.manual = recipient_readiness(target, config, usage, message, manual=True, ledger_error=self.ledger_error)
                self._readiness(row)
                colors = status_colors(self)
                allowances = []
                for action, enabled, used, limit, override in (("Goal", goal, gu, gl, target.goal_limit),
                                                              ("Message", prompt, pu, pl, target.prompt_limit)):
                    if enabled:
                        text = GLib.markup_escape_text(action + ": " + used.describe(limit) + (" (override)" if override is not None else " (default)"))
                        if limit is not None and used.used >= limit:
                            text = f"<span foreground='{colors['error']}' weight='bold'>⚠ {text}</span>"
                        elif used.uncertain:
                            text = f"<span foreground='{colors['warning']}'>⚠ {text}</span>"
                        allowances.append(text)
                row.allowance.set_markup("\n".join(allowances))
                preview = " ".join(message.splitlines())
                row.preview.set_text(("Custom: " if target.custom_prompt is not None else "Default: ") + (preview[:100] + "…" if len(preview) > 100 else preview) if prompt else "")
                row.preview.set_no_show_all(True)
                row.preview.set_visible(prompt)
                row.preview.set_tooltip_text(message if prompt else "")
            if self.selected_key not in selected:
                self.selected_key = None if self.selection_initialized else next(iter(selected), None)
            self.list.select_row(self.rows.get(self.selected_key))
            self._load_editor(config)
        finally:
            self.updating = False

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
                return "No actions selected"
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
        row.plan.set_markup("\n".join(lines))
        row.plan.set_no_show_all(True)
        row.plan.set_visible(bool(lines))
        context = row.get_style_context()
        if row.automatic.ready:
            context.remove_class("recipient-passive")
        else:
            context.add_class("recipient-passive")
        actions = (*row.automatic.actions, *row.manual.actions)
        warning = any(action.state in {"blocked", "uncertain"} or action.warning or
                      action.state == "passive" and not action.reason.startswith("Already active") for action in actions)
        passive = any(not action.ready for action in actions) or not actions
        icon = "dialog-warning-symbolic" if warning else "dialog-information-symbolic" if passive else "emblem-ok-symbolic"
        row.indicator.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
        row.indicator.set_no_show_all(True)
        row.indicator.set_visible(warning or passive)
        row.indicator.get_accessible().set_name("Recipient readiness: " +
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

    def _row_selected(self, _list, row):
        if self.updating:
            return
        self.selected_key = row.key if row is not None else None
        self.selection_initialized = True
        self.updating = True
        try:
            if row is not None:
                self.picker.highlight_recipient(row.key)
            self._load_editor(AppConfig.load())
        finally:
            self.updating = False

    def _row_activated(self, _list, row):
        if not self.updating:
            self.picker.highlight_recipient(row.key)

    def select_recipient(self, key):
        if self.updating:
            return
        self.updating = True
        self.selection_initialized = True
        try:
            self.selected_key = key if key in self.rows else None
            row = self.rows.get(self.selected_key)
            self.list.select_row(row)
            if row is not None:
                y = row.translate_coordinates(self.list, 0, 0)[1]
                self.list_scroller.get_vadjustment().clamp_page(y, y + row.get_allocated_height())
            self._load_editor(AppConfig.load())
        finally:
            self.updating = False

    def _load_editor(self, config):
        target = self.picker.selected.get(self.selected_key)
        for child in self.editor.get_children():
            if child is not self.reset.get_parent():
                child.set_sensitive(target is not None)
        self.reset.set_sensitive(target is not None)
        self.prompt_limit.inherited_value(config.prompt_limit)
        self.goal_limit.inherited_value(config.goal_limit)
        if target is None:
            self.custom.set_active(False)
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
        self.message.set_editable(enabled)
        self.message.set_cursor_visible(enabled)
        context = self.message.get_style_context()
        if enabled:
            context.remove_class("inherited-message")
        else:
            context.add_class("inherited-message")
        self.message.set_tooltip_text("Custom message for this recipient" if enabled else
            "Default message preview. Enable the custom message checkbox to edit this recipient's message.")

    def _custom_toggled(self, *_):
        if self.updating:
            return
        target = self.picker.selected.get(self.selected_key)
        if target is not None:
            self._set_custom_appearance(self.custom.get_active())
            self.picker.update_recipient(replace(target, custom_prompt=effective_message(target, self.picker._prompt_text()) if self.custom.get_active() else None))

    def _message_changed(self, *_):
        if self.updating or not self.custom.get_active():
            return
        target = self.picker.selected.get(self.selected_key)
        if target is not None:
            self._set_custom_appearance(self.custom.get_active())
            self.picker.update_recipient(replace(target, custom_prompt=self.message_buffer.get_text(*self.message_buffer.get_bounds(), True)))

    def _reset(self, *_):
        if self.selected_key is None:
            return
        try:
            (self.ledger or UsageLedger()).reset([self.selected_key])
            self.picker._message("Recipient counts reset. No signals sent.")
            self.render()
        except Exception as exc:
            self.picker._message(str(exc), "error")

    def _reset_all(self, *_):
        try:
            ledger = self.ledger or UsageLedger()
            ledger.reset({key for key, _action in ledger.snapshot()})
            self.picker._message("All recipient counts reset. No signals sent.")
            self.render()
        except Exception as exc:
            self.picker._message(str(exc), "error")
