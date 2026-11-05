"""GTK target picker; discovery and delivery run outside the UI thread."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

import threading
import subprocess
import sys
import time
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk, Pango

from .brand_ui import ProjectLogo
from .table_layout import TableLayout
from .wrapping_button import WrappingButton
from .window_layout import WindowLayout
from .resizable_editor import ResizableEditor
from .recipient_ui import RecipientPanel
from .delivery_policy import invalid_messages
from .config import AppConfig, config_path
from .autostart import is_autostart_enabled, set_autostart
from .quota import discover_codex, fetch_quota
from . import tray_control
from .target_delivery import open_target, send_signals
from .targets import Target, discover_targets
from .status_display import COLORS, status_colors, status_level, status_tooltip, watch_check_summary, send_schedule_summary
from .status_log import StatusLog
from .status_help import StatusInfoButton, status_markup
from .activity import target_label
from .branding import asset_path, set_window_icon


class TargetPicker(Gtk.Window):
    def __init__(self, *, quit_on_close=True):
        self.quit_on_close = quit_on_close
        super().__init__(title="Recharge AI-task")
        set_window_icon(self)
        self.set_default_size(1440, 980)
        self.config = AppConfig.load()
        self.window_layout = WindowLayout(self, version=2)
        self.preferences = {t.key: t for t in self.config.all_targets()}
        self.selected = {t.key: t for t in self.config.targets()}
        self.targets = dict(self.selected)
        self.busy = False
        self.closed = False
        self._updating_startup = False
        self.runtime = None
        self.runtime_busy = False
        self.activity_busy = False
        self.activity_cursor = 0
        self.activity_error = ""
        self.quota_busy = False
        self.discovery_busy = False
        self.quota = None
        self.quota_error = ""
        self.quota_updated = None
        self.autosave_error = ""
        self._save_notice = ""
        self._runtime_notice = None
        self._inventory_notice = ""
        self._quota_notice = ""
        self.saved_signature = self._signature(self.config.targets(), self.config.continue_prompt) if config_path().exists() else None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(14)
        self.add(box)
        dashboard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.watch_label = Gtk.Label(label="Desktop watch: checking…", xalign=0)
        self.watch_label.set_line_wrap(True)
        self.watch_label.set_max_width_chars(25)
        watch_css = Gtk.CssProvider()
        watch_css.load_from_data(b"""
            .watch-status { border-width: 2px; border-style: solid; border-radius: 4px; padding: 6px 8px; }
            .watch-on { border-color: #198038; }
            .watch-off { border-color: #c62828; }
            .watch-stopping { border-color: #e0b400; }
        """)
        context = self.watch_label.get_style_context()
        context.add_provider(watch_css, Gtk.STYLE_PROVIDER_PRIORITY_USER)
        context.add_class("watch-status")
        context.add_class("watch-off")
        self.startup_label = Gtk.Label(label="Startup: checking…", xalign=0)
        self.quota_label = Gtk.Label(label="Quota: loading…", xalign=0, selectable=True)
        self.quota_label.set_line_wrap(True)
        controls = Gtk.Box(spacing=8)
        self.watch_button = Gtk.Button(label="Start Desktop watch")
        self.watch_button.connect("clicked", self.toggle_watch)
        self.watch_button.set_sensitive(False)
        watch_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        watch_row.set_valign(Gtk.Align.START)
        self.watch_label.set_halign(Gtk.Align.START)
        watch_row.pack_start(self.watch_button, False, False, 0)
        watch_row.pack_start(self.watch_label, False, False, 0)
        overview = Gtk.Box(spacing=10)

        def card(title, content, *, expand=True):
            frame = Gtk.Frame()
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
            body.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
            body.pack_start(content, True, True, 0)
            frame.add(body)
            overview.pack_start(frame, expand, expand, 0)
            return frame

        self.monitoring_card = card("Monitoring", watch_row, expand=False)
        self.monitoring_card.set_size_request(260, -1)
        self.recipient_label = Gtk.Label(xalign=0)
        self.recipient_label.set_line_wrap(True)
        self.recipient_label.set_max_width_chars(30)
        check = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.next_check_label = Gtk.Label(label="Checking…", xalign=0)
        self.next_check_detail = Gtk.Label(xalign=0)
        self.next_check_detail.set_line_wrap(True)
        self.next_check_detail.set_max_width_chars(32)
        check.pack_start(self.next_check_label, False, False, 0)
        check.pack_start(self.next_check_detail, False, False, 0)
        self.send_time_label = Gtk.Label(xalign=0)
        self.send_countdown_label = Gtk.Label(xalign=0)
        self.send_actions_label = Gtk.Label(xalign=0)
        sending = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for label in (self.send_time_label, self.send_countdown_label, self.send_actions_label):
            label.set_line_wrap(True)
            label.set_max_width_chars(30)
            sending.pack_start(label, False, False, 0)
        checks = Gtk.Box(spacing=12)
        checks.pack_start(check, True, True, 0)
        checks.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        checks.pack_start(sending, True, True, 0)
        self.quota_card = card("Quota checks & recovery", checks)
        dashboard.pack_start(overview, False, False, 0)
        startup_row = Gtk.Box(spacing=8)
        self.startup_toggle = Gtk.CheckButton()
        self.startup_toggle.set_tooltip_text("Run Recharge AI-task in the tray when you log in")
        self.startup_toggle.connect("toggled", self.toggle_startup)
        startup_row.pack_start(self.startup_toggle, False, False, 0)
        startup_row.pack_start(self.startup_label, True, True, 0)
        self.startup_label.set_line_wrap(True)
        self.startup_label.set_max_width_chars(26)
        self.startup_toggle.set_valign(Gtk.Align.START)
        dashboard.pack_start(self.quota_label, False, False, 0)
        self.quota_button = Gtk.Button(label="Check quota now")
        self.quota_button.connect("clicked", self.refresh_quota)
        self.settings_button = Gtk.Button(label="Settings…")
        self.settings_button.connect("clicked", self.settings)
        for widget in (self.quota_button, self.settings_button):
            controls.pack_start(widget, False, False, 0)
        dashboard.pack_start(controls, False, False, 0)
        dashboard_row = Gtk.Box(spacing=12)
        dashboard_row.pack_start(dashboard, True, True, 0)
        self.logo = Gtk.Image.new_from_file(str(asset_path("logo-lockup.png")))
        self.logo.get_accessible().set_name("Recharge AI-task logo")
        self.logo_link = ProjectLogo(self.logo)
        self.logo_link.set_halign(Gtk.Align.END)
        self.logo_link.set_valign(Gtk.Align.START)
        self.brand_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.brand_area.set_valign(Gtk.Align.START)
        self.brand_area.pack_start(self.logo_link, False, False, 0)
        self.brand_area.pack_start(startup_row, False, False, 0)
        dashboard_row.pack_end(self.brand_area, False, False, 0)
        box.pack_start(dashboard_row, False, False, 0)
        self.selection_help = Gtk.Label(xalign=0)
        self.selection_help.set_markup("<b>Automatic quota recovery</b> · Choose Send message, Resume goal, or both for each recipient.\n"
            "Choices and message text save automatically for future quota recovery. Editing them sends nothing now.")
        self.selection_help.set_line_wrap(True)
        box.pack_start(self.selection_help, False, False, 0)
        self.search = Gtk.SearchEntry(placeholder_text="Search title, status, ID, project, process, or link…")
        self.search.connect("search-changed", lambda _: self.filtered.refilter())
        search_row = Gtk.Box(spacing=10)
        search_row.pack_start(self.search, True, True, 0)
        self.technical_toggle = Gtk.CheckButton(label="Show technical columns")
        self.technical_toggle.set_tooltip_text("Show paths, recipient kind, availability, IDs, process and routing details. Search includes these fields in either view.")
        self.technical_toggle.set_active(self.config.show_technical_columns)
        self.technical_toggle.connect("toggled", self.toggle_technical_columns)
        search_row.pack_start(self.technical_toggle, False, False, 0)
        box.pack_start(search_row, False, False, 0)
        self.store = Gtk.ListStore(bool, str, str, str, str, str, str, str, str, str, str, str, bool, str, str, float)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self._visible)
        self.table = Gtk.TreeView(model=self.filtered)
        density_css = Gtk.CssProvider()
        density_css.load_from_data(b"""
            .recipient-table { -GtkTreeView-horizontal-separator: 2; -GtkTreeView-vertical-separator: 2; }
            .recipient-table header button { padding: 3px 4px; min-width: 0; }
        """)
        self.table.get_style_context().add_class("recipient-table")
        self.table.get_style_context().add_provider(density_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.table.connect_after("draw", self._draw_recipient_divider)
        self.table.set_has_tooltip(True)
        self.table.connect("query-tooltip", self._tooltip)
        self.table_layout = TableLayout(self.table, self.store, self.config.table_layout, self._message, default_sort="last_active_at", leading_column="project_name", selected_columns=(0, 12))
        for label, index, action in (("Send message", 0, "send_prompt"), ("Resume goal", 12, "send_goal")):
            checkbox = Gtk.CellRendererToggle()
            checkbox.connect("toggled", self._toggle, action)
            column = Gtk.TreeViewColumn(label, checkbox, active=index)
            header = Gtk.Label(label=label)
            header.set_tooltip_text("Send the message below. When both actions are selected, native Goal activation is verified first."
                if action == "send_prompt" else
                "Resume the native goal without a message. Automatic recovery respects intentional pauses; Send now may resume a paused goal. Window recipients cannot identify a fixed goal.")
            header.show()
            column.set_widget(header)
            if action == "send_goal":
                column.set_cell_data_func(checkbox, self._goal_cell)
            self.table.append_column(column)
            self.table_layout.register(action, column, index, 95)
        columns = [("Title", 1, 230), ("Last active", 14, 155), ("Task status", 10, 125), ("Goal status", 11, 105),
                   ("Project", 13, 130), ("Project path", 8, 300), ("Kind", 2, 80), ("Availability", 3, 160), ("ID", 4, 295),
                   ("PID", 5, 95), ("Instance", 6, 260), ("Deep link", 7, 400),
                   ("Desktop client", 9, 300)]
        self.technical_columns = []
        self.status_info = {}
        column_keys = {1: "title", 2: "kind", 3: "availability", 4: "id", 5: "pid",
                       6: "instance", 7: "deeplink", 8: "cwd", 9: "owner_id",
                       10: "task_status", 11: "goal_status", 13: "project_name", 14: "last_active_at"}
        for name, index, width in columns:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(name, renderer, text=index)
            if index in (10, 11):
                column.set_cell_data_func(renderer, self._status_cell, index)
                header = Gtk.Box(spacing=5)
                header.pack_start(Gtk.Label(label=name), False, False, 0)
                info = StatusInfoButton(goal=index == 11)
                self.status_info[index] = info
                header.pack_start(info,False,False,0)
                header.set_tooltip_text("Hover over ⓘ for status recovery rules; keyboard help (F1).")
                header.show_all()
                column.set_widget(header)
            column.set_resizable(True)
            column.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            column.set_fixed_width(width)
            if index == 1:
                self.title_column = column
            if index not in (1, 10, 11, 13, 14):
                self.technical_columns.append(column)
                column.set_visible(self.config.show_technical_columns)
            self.table.append_column(column)
            self.table_layout.register(column_keys[index], column, index, width, renderer,
                                       sort_index=15 if index == 14 else None)
            if index == 14:
                column.get_widget().set_tooltip_text("Last chat update recorded by Codex, shown in local time. Refreshes every 15 seconds. Unknown means Codex did not provide a timestamp.")
        for index,info in self.status_info.items():
            info.bind_column(self.table_layout.columns["goal_status" if index==11 else "task_status"][0])
        self.table_layout.restore()
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.table)
        box.pack_start(scroller, True, True, 0)
        self.inventory_status = Gtk.Label(label="Discovering targets…", xalign=0)
        self.inventory_status.set_line_wrap(True)
        self.inventory_status.set_tooltip_text("Chat statuses refresh every 15 seconds. Send message sends only the message; Resume goal resumes without a prompt. Resume goal is available for chat IDs. Task state comes from Codex's live desktop owner when available; goal state also uses the saved goal database. Windows do not identify a fixed chat. Unavailable means the state could not be read.")
        self.buttons = []
        self.list_toolbar = Gtk.Box(spacing=8)
        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.connect("clicked", self.refresh)
        self.copy_button = WrappingButton(label="Copy link / ID")
        self.copy_button.connect("clicked", self.copy_row)
        self.list_toolbar.pack_start(self.refresh_button, False, False, 0)
        self.toolbar_spacer = Gtk.Box()
        self.list_toolbar.pack_start(self.toolbar_spacer, True, True, 0)
        self.list_toolbar.pack_start(self.copy_button, False, False, 0)
        self.open_button = WrappingButton(label="Open selected row")
        self.open_button.connect("clicked", self.open_row)
        self.list_toolbar.pack_start(self.open_button, False, False, 0)
        for button in (self.refresh_button, self.copy_button, self.open_button):
            button.set_valign(Gtk.Align.CENTER)
        self.buttons.extend((self.refresh_button, self.copy_button, self.open_button))
        box.pack_start(self.list_toolbar, False, False, 0)
        prompt = Gtk.Box(spacing=8)
        prompt_label = Gtk.Label(label="Default message:", valign=Gtk.Align.START)
        prompt_label.set_margin_top(6)
        self.prompt_actions = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.prompt_actions.set_size_request(118, -1)
        self.prompt_actions.pack_start(prompt_label, False, False, 0)
        prompt.pack_start(self.prompt_actions, False, False, 0)
        self.signal = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.signal.set_tooltip_text("Used for Send message recipients. Resume goal alone does not send this message.")
        self.signal.set_left_margin(8)
        self.signal.set_right_margin(8)
        self.signal.set_top_margin(6)
        self.signal.set_bottom_margin(6)
        self.signal_buffer = self.signal.get_buffer()
        self.signal_buffer.set_text(self.config.continue_prompt)
        self.prompt_scroller = Gtk.ScrolledWindow()
        self.prompt_scroller.set_shadow_type(Gtk.ShadowType.IN)
        self.prompt_scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.prompt_scroller.set_size_request(100, 36)
        self.prompt_scroller.add(self.signal)
        self.default_editor = self.window_layout.region("default_message", ResizableEditor(self.prompt_scroller))
        prompt.pack_start(self.default_editor, True, True, 0)
        box.pack_start(prompt, False, False, 0)
        self.signal_buffer.connect("changed", self._preferences_changed)
        self.summary = Gtk.Label(xalign=0)
        self.summary.set_line_wrap(True)
        self.summary.set_max_width_chars(80)
        self.send_row = Gtk.Box(spacing=8)
        self.send_row.pack_start(self.summary, True, True, 0)
        self.send_button = WrappingButton(label="Send now", valign=Gtk.Align.END)
        self.send_button.set_tooltip_text("Apply the selected actions immediately, even when Desktop watch is off. If both are selected, Goal activation is verified before sending the message. Paused goals may resume.")
        self.send_button.connect("clicked", self.send)
        self.prompt_actions.pack_end(self.send_button, False, False, 0)
        self.buttons.append(self.send_button)
        box.pack_start(self.send_row, False, False, 0)
        self.status = StatusLog()
        box.pack_start(self.status, False, False, 0)
        # Each scrolling list and multiline editor gets a draggable boundary.
        self.list_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for widget, expand in ((search_row, False), (scroller, True), (self.inventory_status, False), (self.list_toolbar, False)):
            if widget.get_parent() is box:
                box.remove(widget)
            self.list_area.pack_start(widget, expand, expand, 0)
        self.message_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for widget, expand in ((prompt, False), (self.send_row, False)):
            box.remove(widget)
            self.message_area.pack_start(widget, expand, expand, 0)
        box.remove(self.status)
        self.status.set_size_request(100, 36)
        self.message_area.pack_start(self.status, True, True, 0)
        self.recipient_panel = RecipientPanel(self)
        prompt.pack_start(self.recipient_panel.default_controls, False, False, 0)
        self.recipient_panel.default_controls.set_valign(Gtk.Align.START)
        self.recipient_panel.set_border_width(8)
        self.recipient_frame = Gtk.Frame()
        self.recipient_frame.get_accessible().set_name("Recipient actions and overrides")
        self.recipient_frame.add(self.recipient_panel)
        self.main_split = self.window_layout.pane("targets", self.list_area, self.message_area, position=.50)
        self.workspace_split = self.window_layout.pane("chat_recipients", self.main_split, self.recipient_frame, horizontal=True, position=.50)
        box.pack_start(self.workspace_split, True, True, 0)
        self.default_editor.connect("resized", self._resize_default_message)
        self._install_shortcuts()
        WrappingButton._label(self.send_button).set_max_width_chars(12)
        self.default_editor.set_valign(Gtk.Align.FILL)
        self.connect("delete-event", lambda *_: self.busy)
        self.connect("destroy", self._destroy)
        self._timers = [GLib.timeout_add_seconds(2, self.poll_runtime),
                        GLib.timeout_add_seconds(60, self.refresh_quota),
                        GLib.timeout_add_seconds(1, self.render_quota),
                        GLib.timeout_add_seconds(15, self.refresh_statuses)]
        self.refresh()
        self.poll_runtime()
        self.refresh_quota()

    def _install_shortcuts(self):
        group=Gtk.AccelGroup()
        self.add_accel_group(group)
        self.accelerators=group
        for button,key,modifiers,tip in (
            (self.refresh_button,Gdk.KEY_r,Gdk.ModifierType.CONTROL_MASK,"Refresh chats and their statuses (Ctrl+R)"),
            (self.quota_button,Gdk.KEY_r,Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK,"Check quota now and wake the active monitor; the grace period still applies (Ctrl+Shift+R)"),
            (self.send_button,Gdk.KEY_Return,Gdk.ModifierType.CONTROL_MASK,"Apply the selected actions now, respecting each recipient's limits (Ctrl+Enter)"),
            (self.settings_button,Gdk.KEY_comma,Gdk.ModifierType.CONTROL_MASK,"Open program settings (Ctrl+,)")):
            button.add_accelerator("clicked",group,key,modifiers,Gtk.AccelFlags.VISIBLE)
            button.set_tooltip_text(tip)
        for button,icon in ((self.refresh_button,"view-refresh-symbolic"),(self.quota_button,"view-refresh-symbolic"),
                            (self.settings_button,"emblem-system-symbolic"),(self.send_button,"mail-send-symbolic"),
                            (self.copy_button,"edit-copy-symbolic"),(self.open_button,"go-jump-symbolic")):
            button.set_image(Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.BUTTON))
            button.set_always_show_image(True)
        for button in (self.copy_button, self.open_button, self.send_button):
            self._wrap_button_label(button)
        self.watch_button.set_tooltip_text("Start or stop automatic quota recovery for selected recipients (Space / Enter)")
        self.search.set_tooltip_text("Search chats by title, status, project or ID (Ctrl+F)")
        self.connect("key-press-event",self._keyboard)

    @staticmethod
    def _wrap_button_label(button):
        def labels(widget):
            if isinstance(widget, Gtk.Label):
                widget.set_line_wrap(True)
                widget.set_line_wrap_mode(Pango.WrapMode.WORD)
                widget.set_max_width_chars(24)
                widget.set_justify(Gtk.Justification.CENTER)
            elif isinstance(widget, Gtk.Container):
                for child in widget.get_children():
                    labels(child)
        labels(button)

    def _resize_default_message(self, editor):
        # Consume spare log space first; enlarge the lower panel when necessary.
        width = max(100, self.message_area.get_allocated_width())
        summary_height = self.send_row.get_preferred_height_for_width(width)[0]
        required = editor.editor_size()[1] + summary_height + self.status.get_preferred_height()[0] + 12
        if self.message_area.get_allocated_height() < required:
            extent = self.main_split.get_allocated_height()
            minimum_list = self.list_area.get_preferred_height()[0]
            self.main_split.set_position(max(minimum_list, extent - required - 5))

    def _keyboard(self,_window,event):
        if event.keyval == Gdk.KEY_f and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
            return True
        if event.keyval == Gdk.KEY_F1:
            column=self.table.get_cursor()[1]
            index=11 if column is not None and column.get_title()=="Goal status" else 10
            self.status_info[index].open()
            return True
        return False

    def _tooltip(self, table, x, y, keyboard, tooltip):
        context = table.get_tooltip_context(x, y, keyboard)
        if not context or not context[0]:
            return False
        _valid, _x, _y, model, path, iterator = context
        row = model[iterator]
        if keyboard:
            column = table.get_cursor()[1]
        else:
            bx, by = table.convert_widget_to_bin_window_coords(x, y)
            hit = table.get_path_at_pos(bx, by)
            column = hit[1] if hit else None
        name = column.get_title() if column else ""
        if name == "Last active":
            tooltip.set_text(f"Last active: {row[14]}\nLast chat update recorded by Codex, shown in local time.")
            table.set_tooltip_cell(tooltip, path, column, None)
            return True
        if name in ("Task status", "Goal status"):
            index = 11 if name == "Goal status" else 10
            if hasattr(tooltip,"set_markup"):
                tooltip.set_markup(status_markup(row[index],goal=index == 11,widget=self.table))
            else:
                tooltip.set_text(status_tooltip(row[index],goal=index == 11))
            table.set_tooltip_cell(tooltip, path, column, None)
            return True
        tooltip.set_text(f"{row[1]}\nTask: {row[10]}\nGoal: {row[11]}\nLast active: {row[14]}\nID: {row[4]}\nPID: {row[5] or '—'}\nInstance: {row[6]}\n{row[7]}\nProject: {row[13] or '—'}\nProject path: {row[8]}\nDesktop client: {row[9]}")
        table.set_tooltip_row(tooltip, path)
        return True

    @staticmethod
    def _status_cell(_column, renderer, model, iterator, index):
        colors = status_colors(_column.get_tree_view())
        text = model[iterator][index]
        level = status_level(text, goal=index == 11)
        # Reset all reusable renderer state, including after a colored row.
        renderer.set_property("foreground-set", False)
        markup = GLib.markup_escape_text(text)
        if index == 11 and text == "Complete":
            markup = f"<span foreground='{colors['success']}'>✓</span> " + markup
        elif level != "normal":
            renderer.set_property("foreground", colors[level])
        renderer.set_property("markup", markup)

    def _message(self, text, level="normal"):
        self.status.write(text, level)

    def toggle_technical_columns(self, *_):
        visible = self.technical_toggle.get_active()
        path, cursor_column = self.table.get_cursor()
        if not visible and path is not None and cursor_column in self.technical_columns:
            self.table.set_cursor(path, self.title_column)
        for column in self.technical_columns:
            column.set_visible(visible)
        if not visible:
            self.table.get_hadjustment().set_value(0)
        try:
            config = AppConfig.load()
            config.show_technical_columns = visible
            config.save()
            self.config = config
        except Exception as exc:
            self._message(f"Could not save table view: {exc}", "error")

    def _draw_recipient_divider(self, table, cr):
        selected_seen = False
        for row in self.filtered:
            if row[0] or row[12]:
                selected_seen = True
            elif selected_seen:
                bounds = table.get_background_area(row.path, self.title_column)
                _x, y = table.convert_bin_window_to_widget_coords(0, bounds.y)
                header_height = table.convert_bin_window_to_widget_coords(0, 0)[1]
                if y > header_height:
                    color = table.get_style_context().get_color(Gtk.StateFlags.NORMAL)
                    cr.set_source_rgba(color.red, color.green, color.blue, .8)
                    cr.set_line_width(3)
                    cr.move_to(0, y)
                    cr.line_to(table.get_allocated_width(), y)
                    cr.stroke()
                break
        return False

    def _visible(self, model, iterator, _data):
        query = self.search.get_text().casefold()
        return not query or query in " ".join(str(model[iterator][i]) for i in (*range(1, 12), 13, 14)).casefold()

    @staticmethod
    def _goal_cell(_column, renderer, model, iterator, _data):
        available = model[iterator][2] == "thread"
        renderer.set_property("activatable", available)
        renderer.set_property("sensitive", available)

    def _toggle(self, _renderer, path, action="send_prompt"):
        if self.busy:
            return
        row = self.filtered[path]
        target = self.targets[row[6] + "\0" + row[4]]
        if action == "send_goal" and target.kind != "thread":
            self._message("Resume goal needs a chat ID. Window recipients support Send message only.", "warning")
            return
        prompt, goal = row[0], row[12]
        self.update_recipient(replace(target,
            send_prompt=not prompt if action == "send_prompt" else prompt,
            send_goal=not goal if action == "send_goal" else goal))

    def update_recipient(self, target):
        self.preferences[target.key] = target
        self.targets[target.instance + "\0" + target.id] = target
        if any(target.signal_actions()):
            self.selected[target.key] = target
        else:
            self.selected.pop(target.key, None)
        # Locate by identity. A checkbox change can reorder the source model.
        for row in self.store:
            if row[4] == target.id and row[6] == target.instance:
                self.store.set(row.iter, [0, 12], [target.send_prompt, target.send_goal])
                break
        self._preferences_changed()

    def _preferences_changed(self, *_):
        self.save()

    def _prompt_text(self):
        return self.signal_buffer.get_text(*self.signal_buffer.get_bounds(), True)

    @staticmethod
    def _signature(targets, text):
        return (frozenset((t.key, *t.signal_actions(), t.custom_prompt, t.prompt_limit, t.goal_limit) for t in targets), text)

    def dirty(self):
        return self._signature(self.selected.values(), self._prompt_text()) != self.saved_signature

    def _summary(self):
        prompts = sum(t.signal_actions()[0] for t in self.selected.values())
        goals = sum(t.signal_actions()[1] for t in self.selected.values())
        count = len(self.selected)
        recipients = f"{count} " + ("recipient" if count == 1 else "recipients")
        self.summary.set_text(f"{recipients} · Send message: {prompts} · Resume goal: {goals}.\n"
            "Send now acts immediately, even with monitoring off, and may resume paused goals.")
        self.send_button.set_label(f"Send now to {recipients}" if count else "Send now")
        self._wrap_button_label(self.send_button)
        WrappingButton._label(self.send_button).set_max_width_chars(12)
        self.summary.set_line_wrap(True)
        message = ("Could not save automatically — retrying: " + self.autosave_error if self.autosave_error else
                   "Changes differ from saved settings. Edits save automatically." if self.dirty() else "")
        if message and message != self._save_notice:
            self._message(message, "error" if self.autosave_error else "warning")
        self._save_notice = message
        if hasattr(self, "recipient_panel"):
            self.recipient_panel.render()
        self._render_runtime()

    def _destroy(self, *_):
        self.window_layout.close()
        self.table_layout.close()
        self.closed = True
        for timer in self._timers:
            GLib.source_remove(timer)
        if self.quit_on_close:
            Gtk.main_quit()

    def _background(self, job, done):
        def worker():
            try:
                value, error = job(), None
            except Exception as exc:
                value, error = None, str(exc)
            def finish():
                if not self.closed:
                    done(value, error)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker, daemon=True).start()

    def poll_runtime(self):
        if self.closed:
            return False
        self.poll_activity()
        if self.runtime_busy:
            return True
        if self.autosave_error and not self.busy:
            self.save()
        self.runtime_busy = True
        def show(value, error):
            self.runtime_busy = False
            self.runtime = value
            try:
                saved = AppConfig.load()
                self.saved_signature = self._signature(saved.targets(), saved.continue_prompt) if config_path().exists() else None
                self._summary()
            except Exception as exc:
                self._message(f"Could not read settings: {exc}", "error")
            self._render_runtime()
        self._background(lambda: tray_control.request(timeout=1), show)
        return True

    def poll_activity(self):
        if self.closed or self.activity_busy:
            return
        from .activity import ActivityLog, display_event
        self.activity_busy = True
        def show(events, error):
            self.activity_busy = False
            if error:
                if error != self.activity_error:
                    self._message("Cannot read delivery history: " + error, "warning")
                self.activity_error = error
                return
            self.activity_error = ""
            for event in events:
                text, level = display_event(event)
                self.status.write(text, level, timestamp=event["created"])
                self.activity_cursor = event["id"]
        self._background(lambda: ActivityLog().read(self.activity_cursor), show)

    def _render_runtime(self):
        if not hasattr(self, "watch_button"):
            return
        runtime = self.runtime or {}
        alive = runtime.get("desktop_watch", False)
        stopping = runtime.get("stopping", False)
        restarting = runtime.get("restarting", False)
        requested = runtime.get("watch_requested", alive)
        state = "Stopping…" if stopping else "Restarting…" if restarting else "On" if alive else "Off"
        if self.runtime is None:
            state += " — tray is not running or is unavailable"
        elif runtime.get("watch_error"):
            state += " — watch error (details below)"
        elif runtime.get("watch_pause_reason"):
            state += " — waiting for valid saved settings"
        elif runtime.get("cli_running"):
            state += " — CLI service is running"
        elif alive:
            try:
                if runtime.get("watch_settings") != tray_control.watch_settings(AppConfig.load()):
                    state += " — applying saved changes automatically"
            except Exception:
                state += " — saved settings could not be read"
        self.watch_label.set_text("Desktop watch: " + state)
        self._render_overview()
        context = self.watch_label.get_style_context()
        for name in ("watch-off", "watch-on", "watch-stopping"):
            context.remove_class(name)
        context.add_class("watch-stopping" if stopping or restarting else "watch-on" if alive else "watch-off")
        self.watch_button.set_label("Stop Desktop watch" if alive or requested else "Start Desktop watch")
        self.watch_button.set_image(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic" if alive or requested else "media-playback-start-symbolic",Gtk.IconSize.BUTTON))
        self.watch_button.set_always_show_image(True)
        self.watch_button.set_sensitive(not self.busy and not self.runtime_busy and (not stopping or restarting) and not runtime.get("cli_running", False))
        self.send_button.set_sensitive(not self.busy and bool(self.selected))
        notice = runtime.get("watch_error") or runtime.get("watch_pause_reason") or (
            "Applying saved settings; Desktop watch will restart automatically." if restarting else "")
        if notice and notice != self._runtime_notice and hasattr(self, "status"):
            self._message(notice, "error" if runtime.get("watch_error") else "warning" if runtime.get("watch_pause_reason") else "normal")
        elif self._runtime_notice and not notice and alive and hasattr(self, "status"):
            self._message("Desktop watch is running with saved settings.")
        self._runtime_notice = notice
        try:
            enabled = is_autostart_enabled()
            startup = "Enabled" if enabled else "Disabled"
            self._updating_startup = True
            try:
                self.startup_toggle.set_active(enabled)
            finally:
                self._updating_startup = False
        except OSError:
            startup = "Unavailable"
        launched = "Yes" if runtime.get("launched_at_startup") else "No" if self.runtime else "Unknown (tray unavailable)"
        self.startup_label.set_text(f"Run at login: {startup}\nThis tray started at login: {launched}")

    def _render_overview(self):
        count = len(self.selected)
        self.recipient_label.set_markup(f"<b>{count} selected</b> · " +
            ("Choose actions in the chat list." if not count else "Choose an item below to edit overrides."))
        value, detail = watch_check_summary(self.runtime, time.time())
        self.next_check_label.set_markup("<b>" + GLib.markup_escape_text(value) + "</b>")
        self.next_check_detail.set_text(detail)
        scheduled, countdown, actions = send_schedule_summary(self.runtime, time.time(), self.config.grace_seconds)
        self.send_time_label.set_markup("<b>" + GLib.markup_escape_text(scheduled) + "</b>")
        self.send_countdown_label.set_text(countdown)
        self.send_actions_label.set_text(actions)

    def toggle_startup(self, *_):
        if self._updating_startup or self.busy:
            return
        enabled = self.startup_toggle.get_active()
        def save():
            previous = is_autostart_enabled()
            config = AppConfig.load()
            config.autostart = enabled
            set_autostart(enabled)
            try:
                config.save()
            except Exception:
                set_autostart(previous)
                raise
            return config
        def show(config):
            self.config = config
            self._message("Run at login enabled." if enabled else "Run at login disabled.")
            self._background(lambda: tray_control.request("reload"), lambda *_: self.poll_runtime())
        self._work(save, show)

    def toggle_watch(self, *_):
        if self.runtime and (self.runtime.get("desktop_watch") or self.runtime.get("watch_requested")):
            command = "stop-watch"
        else:
            if self.dirty() and not self.save():
                return
            if not self.selected:
                self._message("Enable Send message or Resume goal for at least one recipient before starting Desktop watch.", "warning")
                return
            if not self._messages_ready():
                return
            command = "start-watch"
        def control():
            try:
                live = tray_control.request(timeout=1)
            except OSError:
                if command != "start-watch":
                    raise
                args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "recharge_ai_task.tray"]
                subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                deadline = time.monotonic() + 10
                while True:
                    try:
                        live = tray_control.request(timeout=1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise RuntimeError("Tray did not start; check the tray log")
                        time.sleep(.2)
            if command == "start-watch" and live.get("per_target_signals") is not True:
                raise RuntimeError("Restart the tray to use per-recipient Prompt / Goal signals; the running tray is an older version.")
            uses_policies = self.config.prompt_limit is not None or self.config.goal_limit is not None or any(
                t.custom_prompt is not None or t.prompt_limit is not None or t.goal_limit is not None for t in self.selected.values())
            if command == "start-watch" and uses_policies and not live.get("recipient_policies"):
                raise RuntimeError("Restart the tray to enforce recipient messages and continuation limits.")
            return tray_control.request(command)
        def show(value):
            self.runtime = value
            self._render_runtime()
            self._message("Desktop watch is stopping." if value.get("stopping") else "Desktop watch started." if value.get("desktop_watch") else "Desktop watch is off.")
        self._work(control, show)

    def refresh_quota(self, *_):
        if self.closed:
            return False
        if self.quota_busy:
            return True
        self.quota_busy = True
        self.quota_button.set_sensitive(False)
        self.quota_button.set_label("Checking quota…")
        if _ and self.runtime and self.runtime.get("desktop_watch"):
            if self.runtime.get("manual_quota_check"):
                def checked(value,error):
                    if error:
                        self._message("Could not wake quota monitoring: " + error,"warning")
                    self.poll_runtime()
                self._background(lambda: tray_control.request("check-quota"),checked)
            else:
                self._message("Restart the tray to enable immediate quota checks; the display will still refresh.","warning")
        def show(value, error):
            self.quota_busy = False
            self.quota_button.set_sensitive(True)
            self.quota_button.set_label("Check quota now")
            self.quota_error = error or ""
            if error and error != self._quota_notice:
                self._message("Quota refresh failed: " + error, "error")
            self._quota_notice = error or ""
            if value:
                self.quota = value
                self.quota_updated = time.time()
            self.render_quota()
        self._background(lambda: fetch_quota(discover_codex(AppConfig.load().codex_path)), show)
        return True

    def render_quota(self):
        if self.closed:
            return False
        self._render_overview()
        if self.quota is None:
            self.quota_label.set_text("Quota unavailable — see messages below" if self.quota_error else "Quota: loading…")
            return True
        colors = status_colors(self.quota_label)
        def window_text(window):
            label = "5-hour" if window.window_duration_mins == 300 else "Weekly" if window.window_duration_mins == 10080 else f"{window.window_duration_mins}-minute"
            remaining = max(0, int(window.resets_at - time.time()))
            days, remainder = divmod(remaining, 86400)
            hours, remainder = divmod(remainder, 3600)
            minutes, seconds = divmod(remainder, 60)
            countdown = (f"{days}d " if days else "") + f"{hours:02}:{minutes:02}:{seconds:02}"
            reset = time.strftime("%a %d %b %H:%M:%S", time.localtime(window.resets_at))
            text = GLib.markup_escape_text(f"{label}: {window.used_percent:g}% used")
            suffix = GLib.markup_escape_text(f" · resets {reset} ({countdown})")
            level = "error" if window.used_percent >= 100 else "warning" if window.used_percent >= 85 else None
            return (f'<span foreground="{colors[level]}">{text}</span>' if level else text) + suffix
        lines = [window_text(w) for w in (self.quota.primary, self.quota.secondary) if w is not None]
        if self.quota.has_credits or self.quota.unlimited_credits:
            lines.append("Additional credits are available" + (" · backend still reports a limit" if self.quota.rate_limit_reached or self.quota.spend_control_reached else " · usable without waiting for the included window reset"))
        age = max(0, int(time.time() - self.quota_updated))
        lines.append(f"Quota refreshed {age}s ago · automatic refresh every 60s" + (" · Latest refresh failed — see messages below" if self.quota_error else ""))
        self.quota_label.set_markup("\n".join(lines))
        return True

    def settings(self, *_):
        from .settings_ui import SettingsDialog
        config = SettingsDialog(self).edit()
        if config is not None:
            self.config = config
            self._message("Settings saved; active watch changes apply automatically.")
            self._background(lambda: tray_control.request("reload"), lambda *_: self.poll_runtime())
            self.refresh_quota()
            self._render_runtime()

    def _busy(self, active):
        self.busy = active
        for button in self.buttons:
            button.set_sensitive(not active)
        self.signal.set_sensitive(not active)
        self.startup_toggle.set_sensitive(not active)
        self.table.set_sensitive(not active)
        self.settings_button.set_sensitive(not active)
        self.recipient_panel.set_sensitive(not active)
        self.recipient_panel.default_controls.set_sensitive(not active)
        self._render_runtime()

    def _work(self, job, done):
        self._busy(True)
        def worker():
            try:
                result, error = job(), None
            except Exception as exc:
                result, error = None, str(exc)
            def finish():
                self._busy(False)
                if error:
                    self._message(error, "error")
                else:
                    done(result)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_inventory(self, inventory):
        live = {t.key: t.with_preferences(self.preferences.get(t.key)) for t in inventory.targets}
        for key, saved in list(self.selected.items()):
            self.selected[key] = live.get(key, replace(saved, task_status="Unavailable", goal_status="Unavailable")).with_preferences(saved)
        targets = {**live, **{k: t for k, t in self.selected.items() if k not in live}}
        self.targets = {t.instance + "\0" + t.id: t for t in targets.values()}
        # Update existing rows in place so refresh preserves focus and scrolling.
        rows = {}
        for index in range(len(self.store) - 1, -1, -1):
            row = self.store[index]
            key = Target(row[2], row[4], row[1], instance=row[6]).key
            if key not in targets:
                self.store.remove(row.iter)
            else:
                rows[key] = row.iter
        for key, target in targets.items():
            choice = self.selected.get(key)
            values = [choice.send_prompt if choice else False, target.title, target.kind,
                target.status if key in live else "Unavailable — saved selection",
                target.id, str(target.pid or ""), target.instance, target.deeplink, target.cwd,
                target.owner_id, target.task_status, target.goal_status, choice.send_goal if choice else False, target.project_name,
                datetime.fromtimestamp(target.last_active_at).astimezone().strftime("%Y-%m-%d %H:%M:%S") if target.last_active_at else "Unknown",
                target.last_active_at or 0.0]
            iterator = rows.get(key)
            if iterator is None:
                self.store.append(values)
            else:
                self.store.set(iterator, list(range(len(values))), values)
        self.filtered.refilter()
        warnings = "\n".join(inventory.warnings)
        if warnings and warnings != self._inventory_notice:
            self._message(warnings, "warning")
        self._inventory_notice = warnings
        self.inventory_status.set_text(f"{len(inventory.targets)} targets · Status refreshed {time.strftime('%H:%M:%S')} · Every 15 seconds"
            + (f" · {len(inventory.warnings)} warning(s); see messages below" if inventory.warnings else ""))
        self._summary()

    def refresh(self, *_, automatic=False):
        if self.closed or self.discovery_busy or self.busy:
            return
        self.discovery_busy = True
        if not automatic:
            self.inventory_status.set_text("Refreshing targets and statuses…")
        def show(inventory, error):
            self.discovery_busy = False
            if error:
                # Retain the recipients, but never display stale state as current.
                for row in self.store:
                    row[10], row[11] = "Unavailable", "Unavailable"
                self.filtered.refilter()
                self.inventory_status.set_text("Status refresh failed; see messages below")
                self._message(f"Status refresh failed: {error}", "error")
            else:
                self._apply_inventory(inventory)
        self._background(discover_targets, show)

    def refresh_statuses(self):
        if self.closed:
            return False
        self.refresh(automatic=True)
        return True

    def highlight_recipient(self, key):
        """Reveal the same stable recipient identity without changing its actions."""
        target = self.selected.get(key)
        if target is None:
            return

        def matching_path():
            for row in self.filtered:
                if row[4] == target.id and row[6] == target.instance:
                    return row.path
            return None

        path = matching_path()
        if path is None and self.search.get_text():
            self.search.set_text("")
            self.filtered.refilter()
            path = matching_path()
        if path is not None:
            self.table.get_selection().select_path(path)
            self.table.scroll_to_cell(path, self.title_column, True, .5, 0)

    def _row_target(self):
        model, iterator = self.table.get_selection().get_selected()
        if iterator is None:
            raise ValueError("Choose a row first")
        row = model[iterator]
        return self.targets[row[6] + "\0" + row[4]]

    def open_row(self, *_):
        try:
            target = self._row_target()
            self._work(lambda: open_target(target), lambda _: self._message("Chat opened in Codex. Refresh to update the list."))
        except Exception as exc:
            self._message(str(exc), "error")

    def copy_row(self, *_):
        try:
            target = self._row_target()
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(target.deeplink or target.id, -1)
            self._message("Copied.")
        except Exception as exc:
            self._message(str(exc), "error")

    def save(self, *_):
        # Save synchronously and atomically: rapid checkbox changes cannot race
        # each other, discovery, window closing, or watch startup. Empty prompt
        # drafts may be saved, but sending/watching validates them separately.
        try:
            config = AppConfig.load()
            self.preferences.update(self.selected)
            config.desktop_targets = [t.to_dict() for t in self.preferences.values()]
            config.continue_prompt = self._prompt_text()
            config.mode = "desktop"
            config.save()
        except Exception as exc:
            self.autosave_error = str(exc)
            self._summary()
            return False
        recovered_save = bool(self.autosave_error)
        self.config = config
        self.autosave_error = ""
        self.saved_signature = self._signature(self.selected.values(), config.continue_prompt)
        self._summary()
        if recovered_save:
            self._message("Settings saved after retry.")
        self._background(lambda: tray_control.request("reload"), lambda *_: self.poll_runtime())
        return True

    def _messages_ready(self):
        try:
            invalid = invalid_messages(self.selected.values(), self._prompt_text(), AppConfig.load())
        except Exception as exc:
            self._message(f"Cannot validate delivery settings: {exc}", "error")
            return False
        if invalid:
            self._message("Enter a message for recipients with Send message enabled: " +
                          ", ".join(t.title for t in invalid), "warning")
            return False
        return True

    def send(self, *_):
        if not self.selected:
            self._message("Select at least one target before sending.", "warning")
            return
        selected = list(self.selected.values())
        text = self._prompt_text()
        if not self._messages_ready():
            return
        self._message(f"Sending now to {len(selected)} selected recipients…", "success")
        def show(results):
            accepted = sum(r.success and not r.skipped for r in results)
            skipped = sum(r.skipped for r in results)
            failed = sum(not r.success for r in results)
            detail = "\n".join(f"{r.target.title} [{r.target.id}]: {r.detail}" for r in results)
            for result in results:
                self._message(f"{target_label(result.target)} [{result.target.id}]: {result.detail}",
                              "error" if not result.success else "warning" if result.skipped else "success")
            self._message(f"Signals: {accepted} accepted, {skipped} skipped, {failed} failed.",
                          "error" if failed else "warning" if skipped else "success")
            self.poll_activity()
            self.refresh_statuses()
        self._work(lambda: send_signals(selected, text, manual=True), show)


def main(*, settings=False):
    window = TargetPicker()
    window.show_all()
    if settings:
        GLib.idle_add(lambda: window.settings() or False)
    Gtk.main()
    return 0
