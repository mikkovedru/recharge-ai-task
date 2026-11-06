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
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango

from .brand_ui import ProjectLogo
from .table_layout import TableLayout
from .wrapping_button import WrappingButton
from .window_layout import WindowLayout
from .theme_ui import apply_color_theme
from .resizable_editor import ResizableEditor
from .recipient_ui import RecipientPanel
from .delivery_policy import invalid_messages, clear_consumed_custom_prompt, effective_limit
from .config import AppConfig, config_path
from .quota import discover_codex, fetch_quota
from . import tray_control
from .target_delivery import open_target, send_signals
from .targets import Target, discover_targets
from .status_display import BORDER_COLORS, COLORS, overview_status_level, status_colors, status_level, status_tooltip, watch_check_summary, send_schedule_summary
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
        apply_color_theme(self.config.color_theme)
        self.window_layout = WindowLayout(self, version=3)
        self.preferences = {t.key: t for t in self.config.all_targets()}
        self.selected = {t.key: t for t in self.config.targets()}
        self.targets = dict(self.selected)
        self.busy = False
        self.closed = False
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
        self.apply_error = ""
        self.apply_revision = 0
        self._auto_start_pending = False
        self._apply_notice = ""
        self._save_notice = ""
        self._runtime_notice = None
        self._inventory_notice = ""
        self._quota_notice = ""
        self.saved_signature = self._signature(self.config.targets(), self.config.continue_prompt) if config_path().exists() else None
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_border_width(14)
        self.add(box)
        dashboard = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.watch_label = Gtk.Label(label="Checking…", xalign=1)
        self.watch_label.get_accessible().set_name("Monitoring status")
        self.monitoring_heading = Gtk.Label(label="Monitoring", xalign=0)
        monitoring_header = Gtk.Box(spacing=12)
        monitoring_header.pack_start(self.monitoring_heading, True, True, 0)
        monitoring_header.pack_end(self.watch_label, False, False, 0)
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
        overview = Gtk.Box(spacing=10)

        def card(title, content, *, expand=True):
            frame = Gtk.Frame()
            body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin=10)
            if title is not None:
                body.pack_start(Gtk.Label(label=title, xalign=0) if isinstance(title, str) else title, False, False, 0)
            body.pack_start(content, True, True, 0)
            frame.add(body)
            overview.pack_start(frame, expand, expand, 0)
            return frame

        self.monitoring_card = card(monitoring_header, watch_row, expand=False)
        self.monitoring_css = Gtk.CssProvider()
        self.monitoring_palette = None
        self.monitoring_card.get_style_context().add_provider_for_screen(self.get_screen(), self.monitoring_css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.monitoring_card.get_style_context().add_class("monitoring-card")
        self.monitoring_card.connect("style-updated", self._recolor_monitoring)
        self.connect("destroy", lambda *_: Gtk.StyleContext.remove_provider_for_screen(self.get_screen(), self.monitoring_css))
        self._recolor_monitoring()
        self.monitoring_card.set_size_request(260, -1)
        self.monitoring_card.set_valign(Gtk.Align.START)
        self.next_check_label = Gtk.Label(label="Checking…", xalign=0)
        self.next_check_detail = Gtk.Label(xalign=0)
        self.next_check_detail.set_line_wrap(True)
        self.next_check_detail.set_max_width_chars(32)
        self.send_time_label = Gtk.Label(xalign=0)
        self.send_countdown_label = Gtk.Label(xalign=0)
        self.send_actions_label = Gtk.Label(xalign=0)
        for label in (self.send_time_label, self.send_countdown_label, self.send_actions_label):
            label.set_line_wrap(True)
            label.set_max_width_chars(30)
        self.quota_heading = Gtk.Label(label="Quota checks & recovery", xalign=0)
        checks = Gtk.Grid(column_spacing=12, row_spacing=1)
        for row, (left, right) in enumerate(((self.quota_heading, self.send_time_label),
                                           (self.next_check_label, self.send_countdown_label),
                                           (self.next_check_detail, self.send_actions_label))):
            for column, label in ((0, left), (2, right)):
                label.set_line_wrap(False)
                label.set_single_line_mode(True)
                label.set_ellipsize(Pango.EllipsizeMode.END)
                label.get_style_context().add_class("overview-compact")
                label.set_valign(Gtk.Align.START)
                label.set_hexpand(True)
                checks.attach(label, column, row, 1, 1)
        checks.attach(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), 1, 0, 1, 3)
        self.quota_card = card(None, checks)
        self.quota_card.set_valign(Gtk.Align.START)
        dashboard.pack_start(overview, False, False, 0)
        dashboard.pack_start(self.quota_label, False, False, 0)
        self.quota_button = Gtk.Button(label="Check quota now")
        self.quota_button.connect("clicked", self.refresh_quota)
        self.settings_button = Gtk.Button(label="Settings…")
        self.settings_button.connect("clicked", self.settings)
        for widget in (self.quota_button, self.settings_button):
            controls.pack_start(widget, False, False, 0)
        dashboard.pack_start(controls, False, False, 0)
        dashboard_row = Gtk.Box(spacing=12)
        dashboard.remove(overview)
        dashboard_row.pack_start(overview, True, True, 0)
        self.logo = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(asset_path("logo-lockup.png")), 64, 64, True))
        self.logo.get_accessible().set_name("Recharge AI-task logo")
        self.logo_link = ProjectLogo(self.logo)
        self.logo_link.set_halign(Gtk.Align.END)
        self.logo_link.set_valign(Gtk.Align.START)
        self.brand_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.brand_area.set_valign(Gtk.Align.START)
        self.brand_area.pack_start(self.logo_link, False, False, 0)
        self.overview_height = Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL)
        for widget in (self.monitoring_card, self.quota_card, self.logo_link):
            self.overview_height.add_widget(widget)

        dashboard_row.pack_end(self.brand_area, False, False, 0)
        box.pack_start(dashboard_row, False, False, 0)
        self.selection_help = Gtk.Label(xalign=0)
        self.selection_help.set_markup("<b>Automatic quota recovery</b> · Choose Send message, Resume goal, or both for each recipient.\n"
            "Choices and message text save automatically for future quota recovery. Editing them sends nothing now.")
        self.selection_help.set_line_wrap(True)

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
        self._selection_pending = False
        self.table.get_selection().connect("changed", self._queue_selection_sync)
        self.table.connect("cursor-changed", self._queue_selection_sync)
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
                header.set_tooltip_text("Hover over ⓘ for status recovery rules; focus the icon and press Enter for details.")
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
        self.default_group = Gtk.Box(spacing=8, valign=Gtk.Align.START)
        self.default_group.pack_start(self.prompt_actions, False, False, 0)
        prompt.pack_start(self.default_group, True, True, 0)
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
        self.default_editor = self.window_layout.region("default_message", ResizableEditor(self.prompt_scroller, height=56))
        if self.default_editor.editor_size()[1] == 90:
            self.default_editor.restore_size(self.default_editor.editor_size()[0], 56)
        self.default_group.pack_start(self.default_editor, True, True, 0)
        box.pack_start(prompt, False, False, 0)
        self.signal_buffer.connect("changed", self._preferences_changed)
        self.summary = Gtk.Label(xalign=0)
        self.summary.set_line_wrap(True)
        self.summary.set_max_width_chars(80)
        self.send_row = Gtk.Box(spacing=8)
        self.send_row.pack_start(self.summary, True, True, 0)
        self.send_button = WrappingButton(label="Send now", valign=Gtk.Align.END)
        self.send_button.set_tooltip_text("Send now acts immediately, even with monitoring off, and may resume paused goals. If both actions are selected, Goal activation is verified before sending the message.")
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
        self.compose_group = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, margin=4)
        for widget in (prompt, self.send_row):
            box.remove(widget)
            self.compose_group.pack_start(widget, False, False, 0)
        self.compose_frame = Gtk.Frame()
        self.compose_frame.get_accessible().set_name("Default message and Send now")
        self.compose_frame.add(self.compose_group)
        self.message_area.pack_start(self.compose_frame, False, False, 0)
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
        self.left_workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.left_workspace.pack_start(dashboard, False, False, 0)
        self.left_workspace.pack_start(self.selection_help, False, False, 0)
        self.left_workspace.pack_start(self.main_split, True, True, 0)
        self.right_workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.right_workspace.pack_start(self.recipient_frame, True, True, 0)
        self.workspace_split = self.window_layout.pane("chat_recipients", self.left_workspace, self.right_workspace, horizontal=True, position=.50)
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
            (self.send_button,Gdk.KEY_Return,Gdk.ModifierType.CONTROL_MASK,"Send now acts immediately, even with monitoring off, and may resume paused goals. If both actions are selected, Goal activation is verified first. Recipient limits still apply (Ctrl+Enter)"),
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
        required = editor.editor_size()[1] + summary_height + self.status.get_preferred_height()[0] + 24
        if self.message_area.get_allocated_height() < required:
            extent = self.main_split.get_allocated_height()
            minimum_list = self.list_area.get_preferred_height()[0]
            self.main_split.set_position(max(minimum_list, extent - required - 5))

    def _keyboard(self,_window,event):
        if event.keyval == Gdk.KEY_f and event.state & Gdk.ModifierType.CONTROL_MASK:
            self.search.grab_focus()
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
        first_recipient = not self.selected
        self.preferences[target.key] = target
        self.targets[target.instance + "\0" + target.id] = target
        if any(target.signal_actions()):
            self.selected[target.key] = target
        else:
            self.selected.pop(target.key, None)
        if first_recipient and self.selected:
            self._auto_start_pending = True
        elif not self.selected:
            self._auto_start_pending = False
        # Locate by identity. A checkbox change can reorder the source model.
        for row in self.store:
            if row[4] == target.id and row[6] == target.instance:
                self.store.set(row.iter, [0, 12], [target.send_prompt, target.send_goal])
                break
        self._preferences_changed()
        self._main_selection_changed()

    def _preferences_changed(self, *_):
        return self.save()

    def _prompt_text(self):
        return self.signal_buffer.get_text(*self.signal_buffer.get_bounds(), True)

    @staticmethod
    def _signature(targets, text):
        return (frozenset((t.key, *t.signal_actions(), t.custom_prompt, t.prompt_limit, t.goal_limit, t.custom_prompt_once) for t in targets), text)

    def dirty(self):
        return self._signature(self.selected.values(), self._prompt_text()) != self.saved_signature

    def _summary(self):
        consumed_settings = None
        for key, target in list(self.preferences.items()):
            normalized = clear_consumed_custom_prompt(target)
            if normalized != target:
                if consumed_settings is None:
                    consumed_settings = AppConfig.load()
                latest = next((t for t in consumed_settings.all_targets() if t.key == key), None)
                if latest is not None:
                    normalized = replace(normalized, custom_prompt=latest.custom_prompt, custom_prompt_once=latest.custom_prompt_once)
                self.preferences[key] = normalized
                if key in self.selected:
                    self.selected[key] = normalized
                identity = target.instance + "\0" + target.id
                if identity in self.targets:
                    self.targets[identity] = self.targets[identity].with_preferences(normalized)
        if consumed_settings is not None:
            self.saved_signature = self._signature(consumed_settings.targets(), consumed_settings.continue_prompt)
        prompts = sum(t.signal_actions()[0] for t in self.selected.values())
        goals = sum(t.signal_actions()[1] for t in self.selected.values())
        count = len(self.selected)
        recipients = f"{count} " + ("recipient" if count == 1 else "recipients")
        self.summary.set_text(f"{recipients} · Send message: {prompts} · Resume goal: {goals}.")
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
                if value is not None and (not value.get("desktop_watch") and not value.get("restarting") or
                        value.get("watch_settings") == tray_control.watch_settings(saved)):
                    self.apply_error = ""
                    self._apply_notice = ""
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
        pending_settings = False
        try:
            pending_settings = alive and runtime.get("watch_settings") != tray_control.watch_settings(AppConfig.load())
        except Exception:
            pass
        state = ("Error" if runtime.get("watch_error") else "Stopping" if stopping and not restarting else
                 "Reloading" if restarting or pending_settings else "Waiting" if runtime.get("watch_pause_reason") else
                 "CLI" if runtime.get("cli_running") else "On" if alive else "Off")
        details = ("The tray is not running or is unavailable." if self.runtime is None else
                   runtime.get("watch_error") or runtime.get("watch_pause_reason") or
                   ("Applying saved monitoring settings." if restarting or pending_settings else
                    "Stopping Desktop watch." if stopping else
                    "Quota recovery is managed by the CLI service." if runtime.get("cli_running") else
                    "Desktop watch is on." if alive else "Desktop watch is off."))
        self._overview_label(self.watch_label, state, "error" if state in {"Off", "Error", "Waiting"} else "success" if state == "On" else "warning")
        self.watch_label.set_tooltip_text(details)
        self.monitoring_card.set_tooltip_text(details)
        self._render_overview()
        context = self.monitoring_card.get_style_context()
        for name in ("watch-off", "watch-on", "watch-stopping"):
            context.remove_class(name)
        context.add_class("watch-off" if state in {"Off", "Error", "Waiting"} else "watch-on" if state == "On" else "watch-stopping")
        self.watch_button.set_label("Stop Desktop watch" if alive or requested else "Start Desktop watch")
        self.watch_button.set_image(Gtk.Image.new_from_icon_name("media-playback-stop-symbolic" if alive or requested else "media-playback-start-symbolic",Gtk.IconSize.BUTTON))
        self.watch_button.set_always_show_image(True)
        self.watch_button.set_sensitive(not self.busy and not self.runtime_busy and (not stopping or restarting) and not runtime.get("cli_running", False))
        self.send_button.set_sensitive(not self.busy and bool(self.selected))
        notice = runtime.get("watch_error") or runtime.get("watch_pause_reason") or ""
        if notice and notice != self._runtime_notice and hasattr(self, "status"):
            self._message(notice, "error" if runtime.get("watch_error") else "warning" if runtime.get("watch_pause_reason") else "normal")
        self._runtime_notice = notice

    def _recolor_monitoring(self, *_):
        colors = status_colors(self.monitoring_card)
        palette = tuple(colors.values())
        if palette == self.monitoring_palette:
            return
        self.monitoring_palette = palette
        self.monitoring_css.load_from_data(f"""
            frame.monitoring-card > border {{ border: 2px solid; border-radius: 4px; }}
            frame.monitoring-card.watch-on > border {{ border-color: {BORDER_COLORS['success']}; }}
            frame.monitoring-card.watch-off > border {{ border-color: {BORDER_COLORS['error']}; }}
            frame.monitoring-card.watch-stopping > border {{ border-color: {BORDER_COLORS['warning']}; }}
            .overview-success {{ color: {colors['success']}; }}
            .overview-warning {{ color: {colors['warning']}; }}
            .overview-error {{ color: {colors['error']}; }}
            .overview-compact {{ font-size: .9em; }}
        """.encode())

    @staticmethod
    def _overview_label(label, text, level, *, bold=False):
        context = label.get_style_context()
        for old in ("success", "warning", "error"):
            context.remove_class("overview-" + old)
        if level != "normal":
            context.add_class("overview-" + level)
        label.set_markup(("<b>" if bold else "") + GLib.markup_escape_text(text) + ("</b>" if bold else ""))
        label.set_tooltip_text(text)

    def _render_overview(self):
        value, detail = watch_check_summary(self.runtime, time.time())
        scheduled, countdown, actions = send_schedule_summary(self.runtime, time.time(), self.config.grace_seconds)
        values = ((self.next_check_label, value, True), (self.next_check_detail, detail, False),
                  (self.send_time_label, scheduled, True), (self.send_countdown_label, countdown, False))
        for label, text, bold in values:
            level = overview_status_level(text)
            self._overview_label(label, text, level, bold=bold)
        self.send_actions_label.set_text(actions)
        self.send_actions_label.set_tooltip_text(actions)

    def toggle_watch(self, *_, ensure_started=False):
        if ensure_started and self.runtime and (self.runtime.get("desktop_watch") or self.runtime.get("watch_requested") or self.runtime.get("restarting")):
            return
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
            if command == "start-watch" and any(t.custom_prompt_once for t in self.selected.values()) and not live.get("one_use_messages"):
                raise RuntimeError("Restart the tray to use Send only once custom messages.")
            if ensure_started and (live.get("desktop_watch") or live.get("watch_requested") or live.get("restarting")):
                return live
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
            self._reload_saved_settings()
            self.refresh_quota()
            self._render_runtime()

    def _busy(self, active):
        self.busy = active
        for button in self.buttons:
            button.set_sensitive(not active)
        self.signal.set_sensitive(not active)
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

    def _queue_selection_sync(self, *_):
        # Finish GTK's cursor/selection update before changing editor widgets.
        # One idle callback also coalesces the signals emitted by one key press.
        if self._selection_pending:
            return
        self._selection_pending = True
        def sync():
            self._selection_pending = False
            if not self.closed:
                self._main_selection_changed()
            return False
        GLib.idle_add(sync)

    def _main_selection_changed(self, *_):
        if not hasattr(self, "recipient_panel") or self.recipient_panel.updating or not self.recipient_panel.rows:
            return
        try:
            target = self._row_target()
        except ValueError:
            return
        self.recipient_panel.select_recipient(target.key if target.key in self.selected else None)

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
        self.config = config
        self.autosave_error = ""
        self.saved_signature = self._signature(self.selected.values(), config.continue_prompt)
        self._summary()
        self._reload_saved_settings()
        if self._auto_start_pending and self.selected:
            self._auto_start_pending = False
            self.toggle_watch(ensure_started=True)
        return True

    def _reload_saved_settings(self):
        self.apply_error = ""
        self.apply_revision += 1
        revision = self.apply_revision
        def applied(value, error):
            if revision != self.apply_revision:
                return
            self.apply_error = error or ""
            if error and error != self._apply_notice:
                self._message("Could not apply saved settings: " + error, "error")
            self._apply_notice = error or ""
            if value is not None:
                self.runtime = value
            self._summary()
            self.poll_runtime()
        self._background(lambda: tray_control.request("reload"), applied)

    def custom_message_status(self, target):
        if target is not None:
            reason = "Send messages is Off for this recipient." if not target.signal_actions()[0] else ""
            try:
                limit = effective_limit(target, "prompt", self.config)
                if not reason and limit == 0:
                    reason = "The effective message limit is 0."
            except ValueError:
                return "error", "The message limit is invalid."
            if reason:
                extra = (" Could not save changes: " + self.autosave_error if self.autosave_error else
                         " Saved changes could not be applied: " + self.apply_error if self.apply_error else
                         " The custom text is retained for when messages are enabled.")
                return "paused", "Message sending is paused. " + reason + extra
        if self.autosave_error:
            return "error", "Could not save changes: " + self.autosave_error
        if target is None or target.custom_prompt is None:
            return "default", "Default message is in use; no custom message is enabled."
        try:
            saved = next((t for t in AppConfig.load().all_targets() if t.key == target.key), None)
        except Exception as exc:
            return "error", "Could not verify the saved custom message: " + str(exc)
        if saved is None or (saved.custom_prompt, saved.custom_prompt_once) != (target.custom_prompt, target.custom_prompt_once):
            return "error", "This custom message differs from saved settings; its save has not been confirmed."
        if self.apply_error:
            return "error", "Saved, but changes could not be applied: " + self.apply_error
        runtime = self.runtime
        if runtime is None:
            return "unknown", "Saved. The tray is unavailable, so application by an active watch cannot be verified."
        if target.custom_prompt_once and runtime.get("desktop_watch") and not runtime.get("one_use_messages"):
            return "error", "Saved, but the running tray must be restarted to support Send only once messages."
        error = runtime.get("watch_error") or runtime.get("watch_pause_reason")
        if error:
            return "error", "Saved, but Desktop watch needs attention: " + error
        if runtime.get("restarting") or runtime.get("desktop_watch") and runtime.get("watch_settings") != tray_control.watch_settings(self.config):
            return "pending", "Saved; waiting for Desktop watch to apply these settings."
        return "saved", ("Saved and applied by Desktop watch." if runtime.get("desktop_watch") else
                         "Saved. Desktop watch is off; the custom message is ready for Send now or the next watch start.")

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
