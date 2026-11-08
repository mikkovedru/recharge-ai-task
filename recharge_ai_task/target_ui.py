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
from .provider_ui import ProviderButtons
from .provider_monitor import provider_status
from .provider_monitor_ui import ProviderMonitor, update_selectable_markup
from .delivery_policy import invalid_messages, clear_consumed_custom_prompt, effective_limit
from .config import AppConfig, config_path, PROVIDER_LABELS
from .quota import discover_codex, fetch_quota, quota_from_snapshot, quota_windows, quota_blocked
from .claude import fetch_claude_quota
from .muse import fetch_muse_quota
from . import tray_control
from .target_delivery import open_target, send_signals
from .targets import Target
from .providers import discover_all_targets as discover_targets
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
        self.set_title("Recharge AI-task")
        self.active_providers = ()
        self.installed_providers = ()
        self.quotas = {}
        self.quota_errors = {}
        self.quota_checked = {}
        self.provider_notices = {}
        apply_color_theme(self.config.color_theme)
        self.window_layout = WindowLayout(self, version=3)
        self.preferences = {t.key: t for t in self.config.all_targets()}
        self.selected = {t.key: t for t in self.config.recipients()}
        self.targets = dict(self.selected)
        self.busy = False
        self.closed = False
        self.runtime = None
        self.runtime_busy = False
        self.activity_busy = False
        self.activity_cursor = 0
        self.log_cleared_at = 0
        self.activity_error = ""
        self.quota_busy = False
        self.discovery_busy = False
        self.quota = None
        self.quota_error = ""
        self.quota_updated = None
        self.quota_timer = None
        self.quota_interval = max(1, self.config.poll_seconds)
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
        self.watch_label = Gtk.Label(label="Checking…", xalign=1)
        self.watch_label.get_accessible().set_name("Monitoring status")
        self.monitoring_heading = Gtk.Label(label="Monitoring", xalign=0)
        monitoring_header = Gtk.Box(spacing=12)
        monitoring_header.pack_start(self.monitoring_heading, True, True, 0)
        monitoring_header.pack_end(self.watch_label, False, False, 0)
        self.quota_label = Gtk.Label(label="Quota: loading…", xalign=0, selectable=True)
        self.quota_label.set_line_wrap(True)
        self.watch_button = Gtk.Button(label="Start Desktop watch")
        self.watch_button.connect("clicked", self.toggle_watch)
        self.watch_button.set_sensitive(False)
        watch_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        watch_row.set_valign(Gtk.Align.START)
        self.watch_label.set_halign(Gtk.Align.START)
        watch_row.pack_start(self.watch_button, False, False, 0)
        overview = Gtk.Box(spacing=10)
        self.monitoring_column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

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
        overview.remove(self.monitoring_card)
        self.monitoring_column.pack_start(self.monitoring_card, False, False, 0)
        overview.pack_start(self.monitoring_column, False, False, 0)
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
        self.quota_heading = Gtk.Label(label="All providers · earliest check", xalign=0)
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
        checks.set_tooltip_text("All providers: earliest check/recovery forecast and combined maximum action counts. Provider tabs show independent schedules.")
        summary = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin=6)
        summary.pack_start(checks, False, False, 0)
        summary.pack_start(self.quota_label, False, False, 0)
        self.monitor_tabs = ProviderMonitor(summary)
        self.quota_scroller = self.monitor_tabs.get_nth_page(0)
        self.quota_card = card(None, self.monitor_tabs)
        self.quota_card.set_valign(Gtk.Align.START)
        self.quota_button = Gtk.Button(label="Check quota now")
        self.quota_button.connect("clicked", self.refresh_quota)
        self.settings_button = Gtk.Button(label="Settings…")
        self.settings_button.connect("clicked", self.settings)
        self.quota_button.set_halign(Gtk.Align.START)
        self.monitoring_column.pack_start(self.quota_button, False, False, 0)
        dashboard_row = Gtk.Box(spacing=12)
        dashboard_row.pack_start(overview, True, True, 0)
        self.logo = Gtk.Image.new_from_pixbuf(GdkPixbuf.Pixbuf.new_from_file_at_scale(
            str(asset_path("logo-lockup.png")), 64, 64, True))
        self.logo.get_accessible().set_name("Recharge AI-task logo")
        self.logo_link = ProjectLogo(self.logo)
        self.logo_link.set_valign(Gtk.Align.START)
        self.brand_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.brand_area.set_valign(Gtk.Align.START)
        self.brand_area.pack_start(self.logo_link, False, False, 0)
        self.brand_area.pack_start(self.settings_button, False, False, 0)

        dashboard_row.pack_end(self.brand_area, False, False, 0)
        box.pack_start(dashboard_row, False, False, 0)
        self.selection_help = Gtk.Label(xalign=0)
        self.selection_help.set_markup("<b>Automatic quota recovery</b> · Choose Send message, Resume goal, or both for each recipient. "
            "Choices and message text save automatically for future quota recovery. Editing them sends nothing now.")
        self.selection_help.set_line_wrap(True)
        self.selection_help.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.selection_help.set_width_chars(1)
        self.selection_help.set_max_width_chars(32)
        self.monitoring_column.pack_start(self.selection_help, False, False, 0)

        self.search = Gtk.SearchEntry(placeholder_text="Search title, status, ID, project, process, or link…")
        self.search.connect("search-changed", lambda _: self.filtered.refilter())
        search_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        filter_toolbar = Gtk.Box(spacing=10)
        search_row.pack_start(filter_toolbar, False, False, 0)
        self.provider_filter = ProviderButtons(active=self.config.chat_provider_filter,
            purpose="")
        filter_box = Gtk.Box(spacing=6, margin=4)
        filter_label = Gtk.Label.new_with_mnemonic("_Provider:")
        filter_label.set_mnemonic_widget(self.provider_filter.buttons[self.provider_filter.get_active_id()])
        filter_box.pack_start(filter_label, False, False, 0)
        filter_box.pack_start(self.provider_filter, False, False, 0)
        filter_frame = Gtk.Frame()
        filter_frame.add(filter_box)
        filter_toolbar.pack_start(filter_frame, False, False, 0)
        search_row.pack_start(self.search, True, True, 0)
        self.technical_toggle = Gtk.CheckButton(label="Show technical\ncolumns")
        self.technical_toggle.set_tooltip_text("Show paths, recipient kind, availability, IDs, process and routing details. Search includes these fields in either view.")
        self.technical_toggle.set_active(self.config.show_technical_columns)
        self.technical_toggle.connect("toggled", self.toggle_technical_columns)
        filter_toolbar.pack_end(self.technical_toggle, False, False, 0)
        box.pack_start(search_row, False, False, 0)
        self.store = Gtk.ListStore(bool, str, str, str, str, str, str, str, str, str, str, str, bool, str, str, float, str, str)
        self.filtered = self.store.filter_new()
        self.filtered.set_visible_func(self._visible)
        self.provider_filter.connect("changed", self._provider_filter_changed)
        self.table = Gtk.TreeView(model=self.filtered)
        self._selection_pending = False
        self.table.get_selection().connect("changed", self._queue_selection_sync)
        self.table.connect("cursor-changed", self._queue_selection_sync)
        self.table.connect("row-activated", self._add_recipient)
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
        self.table_layout = TableLayout(self.table, self.store, self.config.table_layout, self._message, default_sort="last_active_at", leading_column="provider", selected_columns=(0, 12))
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
        columns = [("Provider", 16, 90), ("Title", 1, 230), ("Last active", 14, 155), ("Task status", 10, 125), ("Goal status", 11, 105),
                   ("Project", 13, 130), ("Project path", 8, 300), ("Kind", 2, 80), ("Availability", 3, 160), ("ID", 4, 295),
                   ("PID", 5, 95), ("Instance", 6, 260), ("Deep link", 7, 400),
                   ("Desktop client", 9, 300)]
        self.technical_columns = []
        self.status_info = {}
        column_keys = {1: "title", 2: "kind", 3: "availability", 4: "id", 5: "pid",
                       6: "instance", 7: "deeplink", 8: "cwd", 9: "owner_id",
                       10: "task_status", 11: "goal_status", 13: "project_name", 14: "last_active_at", 16: "provider"}
        for name, index, width in columns:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(name, renderer, text=index)
            if index == 16:
                column.set_cell_data_func(renderer, lambda _c, cell, model, iterator, _d:
                    cell.set_property("text", {"codex": "Codex", "claude": "Claude", "muse": "Muse Code"}.get(model[iterator][16], model[iterator][16])))
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
            if index not in (1, 10, 11, 13, 14, 16):
                self.technical_columns.append(column)
                column.set_visible(self.config.show_technical_columns)
            self.table.append_column(column)
            self.table_layout.register(column_keys[index], column, index, width, renderer,
                                       sort_index=15 if index == 14 else None)
            if index == 14:
                column.get_widget().set_tooltip_text("Last chat update recorded by its provider, shown in local time. Refreshes every 15 seconds; unavailable timestamps stay Unknown.")
        for index,info in self.status_info.items():
            info.bind_column(self.table_layout.columns["goal_status" if index==11 else "task_status"][0])
        self.table_layout.restore()
        if (self.config.table_layout or {}).get("leading_column") != "provider":
            self.table.move_column_after(self.table_layout.columns["project_name"][0], self.table_layout.columns["provider"][0])
        self._provider_column_visibility()
        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroller.set_min_content_height(80)
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
        self.log_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.log_header = Gtk.Box(spacing=6)
        self.log_title = Gtk.Label(label="Program log", xalign=0)
        self.log_title.set_markup("<b>Program log</b>")
        self.log_header.pack_start(self.log_title, True, True, 0)
        self.save_log_button = Gtk.Button.new_from_icon_name("document-save-symbolic", Gtk.IconSize.BUTTON)
        self.save_log_button.set_label("Save log…")
        self.save_log_button.set_always_show_image(True)
        self.save_log_button.set_tooltip_text("Save the displayed program log to a text file (Enter / Space)")
        self.save_log_button.connect("clicked", self.save_log)
        self.clear_log_button = Gtk.Button.new_from_icon_name("edit-clear-all-symbolic", Gtk.IconSize.BUTTON)
        self.clear_log_button.set_label("Clear log")
        self.clear_log_button.set_always_show_image(True)
        self.clear_log_button.set_tooltip_text("Clear this window's log; stored delivery history and counts are retained (Enter / Space)")
        self.clear_log_button.connect("clicked", self.clear_log)
        for widget in (self.save_log_button, self.clear_log_button):
            self.log_header.pack_start(widget, False, False, 0)
        self.log_area.pack_start(self.log_header, False, False, 0)
        self.log_area.pack_start(self.status, True, True, 0)
        self.message_area.pack_start(self.log_area, True, True, 0)
        self.recipient_panel = RecipientPanel(self)
        prompt.pack_start(self.recipient_panel.default_controls, False, False, 0)
        self.recipient_panel.default_controls.set_valign(Gtk.Align.START)
        self.recipient_panel.set_border_width(8)
        self.recipient_frame = Gtk.Frame()
        self.recipient_frame.get_accessible().set_name("Recipient actions and overrides")
        self.recipient_frame.add(self.recipient_panel)
        self.main_split = self.window_layout.pane("targets", self.list_area, self.message_area, position=.50)
        self.main_split.child_set_property(self.list_area, "shrink", False)
        self.main_split.child_set_property(self.message_area, "shrink", False)
        self.left_workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.left_workspace.pack_start(self.main_split, True, True, 0)
        self.right_workspace = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.right_workspace.pack_start(self.recipient_frame, True, True, 0)
        self.workspace_split = self.window_layout.pane("chat_recipients", self.left_workspace, self.right_workspace, horizontal=True, position=.50)
        box.pack_start(self.workspace_split, True, True, 0)
        self.default_editor.connect("resized", self._resize_default_message)
        self._install_shortcuts()
        self.logo_link.match_width(self.settings_button, GdkPixbuf.Pixbuf.new_from_file(str(asset_path("logo-lockup.png"))))
        WrappingButton._label(self.send_button).set_max_width_chars(24)
        self.default_editor.set_valign(Gtk.Align.FILL)
        self.connect("delete-event", lambda *_: self.busy)
        self.connect("destroy", self._destroy)
        self._timers = [GLib.timeout_add_seconds(2, self.poll_runtime),
                        GLib.timeout_add_seconds(1, self.render_quota),
                        GLib.timeout_add_seconds(15, self.refresh_statuses)]
        self._configure_quota_poll(self.config.poll_seconds)
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
        required = editor.editor_size()[1] + summary_height + self.log_area.get_preferred_height()[0] + 24
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
        tooltip.set_text(f"{row[1]}\nTask: {row[10]}\nGoal: {row[11]}\nLast active: {row[14]}\nID: {row[4]}\nPID: {row[5] or '—'}\nInstance: {row[6]}\n{row[7]}\nProject: {row[13] or '—'}\nProject path: {row[8]}\nDesktop client: {row[9]}\nDouble-click or Enter to add this item to Recipients & actions. Action checkboxes stay unchanged.")
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

    def _message(self, text, level="normal", *, provider=None):
        self.status.write(text, level, provider=provider)

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
        provider = self.provider_filter.get_active_id()
        if provider != "all" and model[iterator][16] != provider:
            return False
        query = self.search.get_text().casefold()
        return not query or query in " ".join(str(model[iterator][i]) for i in (*range(1, 12), 13, 14, 16)).casefold()

    def _provider_filter_changed(self, *_):
        self.filtered.refilter()
        self._provider_column_visibility()
        try:
            config = AppConfig.load()
            config.chat_provider_filter = self.provider_filter.get_active_id()
            config.save()
        except Exception as exc:
            self._message("Could not save chat filter: " + str(exc), "warning")

    def _provider_column_visibility(self):
        self.table_layout.columns["provider"][0].set_visible(self.provider_filter.get_active_id() == "all")

    @staticmethod
    def _goal_cell(_column, renderer, model, iterator, _data):
        available = model[iterator][2] == "thread"
        renderer.set_property("activatable", available)
        renderer.set_property("sensitive", available)

    def _toggle(self, _renderer, path, action="send_prompt"):
        if self.busy:
            return
        row = self.filtered[path]
        target = self.targets[row[17]]
        if action == "send_goal" and target.kind != "thread":
            self._message("Resume goal needs a chat ID. Window recipients support Send message only.", "warning")
            return
        prompt, goal = row[0], row[12]
        self.update_recipient(replace(target,
            send_prompt=not prompt if action == "send_prompt" else prompt,
            send_goal=not goal if action == "send_goal" else goal))

    def _add_recipient(self, _table, path, _column):
        if not self.busy:
            row = self.filtered[path]
            target = self.targets[row[17]]
            self.update_recipient(replace(target, send_prompt=row[0], send_goal=row[12]))
            self.recipient_panel.select_recipient(target.key)

    def remove_recipient(self, key):
        if self.busy or key not in self.selected:
            return
        target = replace(self.selected.pop(key), send_prompt=False, send_goal=False)
        self.update_recipient(target, include=False)

    def update_recipient(self, target, *, include=True):
        first_recipient = not any(any(t.signal_actions()) for t in self.selected.values())
        self.preferences[target.key] = target
        self.targets[target.key] = target
        if include:
            self.selected[target.key] = target
        if first_recipient and any(target.signal_actions()):
            self._auto_start_pending = True
        elif not self.selected:
            self._auto_start_pending = False
        # Locate by identity. A checkbox change can reorder the source model.
        for row in self.store:
            if row[17] == target.key:
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
                identity = target.key
                if identity in self.targets:
                    self.targets[identity] = self.targets[identity].with_preferences(normalized)
        if consumed_settings is not None:
            self.saved_signature = self._signature(consumed_settings.recipients(), consumed_settings.continue_prompt)
        prompts = sum(t.signal_actions()[0] for t in self.selected.values())
        goals = sum(t.signal_actions()[1] for t in self.selected.values())
        count = len(self.selected)
        recipients = f"{count} " + ("recipient" if count == 1 else "recipients")
        self.summary.set_text(f"{recipients} · Send message: {prompts} · Resume goal: {goals}.")
        self.send_button.set_label(f"Send now\n({goals} goals, {prompts} messages)")
        self._wrap_button_label(self.send_button)
        WrappingButton._label(self.send_button).set_max_width_chars(24)
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
        if self.quota_timer is not None:
            GLib.source_remove(self.quota_timer)
            self.quota_timer = None
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
                if saved.provider != self.config.provider and not self.busy:
                    self._apply_provider_config(saved)
                self._configure_quota_poll(saved.poll_seconds)
                self._adopt_watch_quota()
                if self.quota is None and not self._uses_watch_quota():
                    self.refresh_quota()
                if value is not None and (not value.get("desktop_watch") and not value.get("restarting") or
                        value.get("watch_settings") == tray_control.watch_settings(saved)):
                    self.apply_error = ""
                    self._apply_notice = ""
                self.saved_signature = self._signature(saved.recipients(), saved.continue_prompt) if config_path().exists() else None
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
                self.activity_cursor = max(self.activity_cursor, event["id"])
                if event["created"] <= self.log_cleared_at:
                    continue
                text, level = display_event(event)
                self.status.write(text, level, timestamp=event["created"], attributed=True)
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
        self.watch_button.set_tooltip_text("Monitor each selected recipient using its own provider's quota; the list filter does not change recipients")
        self.send_button.set_sensitive(not self.busy and any(any(t.signal_actions()) for t in self.selected.values()))
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
        self._render_provider_views()

    def _render_provider_views(self):
        if not hasattr(self, "monitor_tabs"):
            return
        panel = getattr(self, "recipient_panel", None)
        usage = getattr(panel, "last_usage", {})
        usage_error = getattr(panel, "ledger_error", "")
        statuses = {provider: provider_status(provider, targets=list(self.selected.values()),
            config=getattr(panel, "view_config", self.config), usage=usage, quota=self.quotas.get(provider),
            error=self.quota_errors.get(provider, ""), notices=self.provider_notices.get(provider, ""),
            checked_at=self.quota_checked.get(provider), runtime=self.runtime,
            installed=provider in self.installed_providers, now=time.time(), usage_error=usage_error)
            for provider in ("codex", "claude", "muse")}
        self.monitor_tabs.update(statuses, self.quota_interval)
        for provider, status in statuses.items():
            detail = status["selection"] + "\n" + (status["error"] or status["notices"] or
                ("Monitoring on" if status["monitored"] else "Monitoring off"))
            self.provider_filter.set_status(provider, status["state"], detail, installed=provider in self.installed_providers)
        states = [status["state"] for status in statuses.values()]
        level = next((level for level in ("error", "warning", "enabled") if level in states), "off")
        self.provider_filter.set_status("all", level, "All providers · " +
            "; ".join(provider.title() + ": " + status["state"] for provider, status in statuses.items()))

    def clear_log(self, *_):
        self.log_cleared_at = time.time()
        self.status.clear()

    def save_log(self, *_):
        chooser = Gtk.FileChooserDialog(title="Save program log", transient_for=self, modal=True,
            action=Gtk.FileChooserAction.SAVE)
        chooser.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Save log", Gtk.ResponseType.ACCEPT)
        chooser.set_default_response(Gtk.ResponseType.ACCEPT)
        chooser.set_do_overwrite_confirmation(True)
        chooser.set_current_name(self.status.default_filename())
        file_filter = Gtk.FileFilter()
        file_filter.set_name("Text files")
        file_filter.add_pattern("*.txt")
        chooser.add_filter(file_filter)
        try:
            if chooser.run() == Gtk.ResponseType.ACCEPT:
                filename = chooser.get_filename()
                if not filename:
                    raise OSError("Choose a file name.")
                self.status.save_to(filename)
        except OSError as exc:
            self._message("Could not save program log: " + str(exc), "error")
        finally:
            chooser.destroy()

    def toggle_watch(self, *_, ensure_started=False, wait_for_block=False):
        active_recipients = [t for t in self.selected.values() if any(t.signal_actions())]
        if ensure_started and self.runtime and (self.runtime.get("desktop_watch") or self.runtime.get("watch_requested") or self.runtime.get("restarting")):
            return
        if self.runtime and (self.runtime.get("desktop_watch") or self.runtime.get("watch_requested")):
            command = "stop-watch"
        else:
            if self.dirty() and not self.save():
                return
            if not active_recipients:
                self._message("Enable Send message or Resume goal for at least one recipient before starting Desktop watch.", "warning")
                return
            if not self._messages_ready():
                return
            command = "start-watch-blocked" if wait_for_block else "start-watch"
        def control():
            try:
                live = tray_control.request(timeout=1)
            except OSError:
                if command not in ("start-watch", "start-watch-blocked", "start-cli"):
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
            starting = command in ("start-watch", "start-watch-blocked")
            if wait_for_block and not live.get("quota_blocked_start"):
                raise RuntimeError("Restart the tray to safely start monitoring when adding a quota-blocked recipient.")
            if starting and live.get("per_target_signals") is not True:
                raise RuntimeError("Restart the tray to use per-recipient Prompt / Goal signals; the running tray is an older version.")
            if starting and any(t.provider != "codex" for t in active_recipients) and not live.get("unified_providers"):
                raise RuntimeError("Restart the tray to monitor recipients from multiple providers.")
            uses_policies = self.config.prompt_limit is not None or self.config.goal_limit is not None or any(
                t.custom_prompt is not None or t.prompt_limit is not None or t.goal_limit is not None for t in active_recipients)
            if starting and uses_policies and not live.get("recipient_policies"):
                raise RuntimeError("Restart the tray to enforce recipient messages and continuation limits.")
            if starting and any(t.custom_prompt_once for t in active_recipients) and not live.get("one_use_messages"):
                raise RuntimeError("Restart the tray to use Send only once custom messages.")
            if ensure_started and (live.get("desktop_watch") or live.get("watch_requested") or live.get("restarting")):
                return live
            return tray_control.request(command)
        def show(value):
            self.runtime = value
            self._render_runtime()
            self._message("Muse Code CLI launched in a terminal." if command == "start-cli" else
                          "Desktop watch is stopping." if value.get("stopping") else "Desktop watch started." if value.get("desktop_watch") else "Desktop watch is off.")
        self._work(control, show)

    def _configure_quota_poll(self, seconds):
        interval = max(1, int(seconds))
        if self.quota_timer is not None and self.quota_interval == interval:
            return
        if self.quota_timer is not None:
            GLib.source_remove(self.quota_timer)
        self.quota_interval = interval
        self.quota_timer = GLib.timeout_add(interval * 1000, self._periodic_quota_refresh)

    def _periodic_quota_refresh(self):
        if self.closed:
            return False
        self.refresh_quota()
        return True

    def _watch_observations(self):
        if not self.runtime or not self.runtime.get("desktop_watch") or not self.runtime.get("shared_quota"):
            return {}
        progress = self.runtime.get("watch_progress") or {}
        if isinstance(progress.get("providers"), dict):
            return progress["providers"]
        provider = (self.runtime.get("watch_settings") or {}).get("provider", "codex")
        return {provider: progress}

    def _uses_watch_quota(self):
        observations = self._watch_observations()
        return bool(observations and set(self.active_providers or ("codex",)) <= set(observations))

    def _adopt_watch_quota(self):
        for provider, progress in self._watch_observations().items():
            error = str(progress.get("quota_error") or "")
            snapshot = progress.get("quota_snapshot")
            if snapshot is not None:
                try:
                    self.quotas[provider] = quota_from_snapshot(snapshot)
                    self.quota_updated = progress.get("checked_at") or time.time()
                    self.quota_checked[provider] = progress.get("checked_at")
                except (TypeError, ValueError, KeyError) as exc:
                    error = "Invalid monitoring quota snapshot: " + str(exc)
            self.quota_errors[provider] = error
        self._sync_quota_display()

    def _sync_quota_display(self):
        self.quota = self.quotas.get("codex") or next(iter(self.quotas.values()), None)
        self.quota_error = "; ".join(f"{PROVIDER_LABELS.get(p, p)}: {e}" for p, e in self.quota_errors.items() if e)
        self.render_quota()

    def refresh_quota(self, *_):
        if self.closed:
            return False
        if self.quota_busy or self.runtime is None and self.runtime_busy:
            return True
        self._adopt_watch_quota()
        if _ and self.runtime and self.runtime.get("desktop_watch") and self.runtime.get("manual_quota_check"):
            def checked(value, error):
                if error:
                    self._message("Could not wake quota monitoring: " + error, "warning")
                self.poll_runtime()
            self._background(lambda: tray_control.request("check-quota"), checked)
        providers = tuple(p for p in self.active_providers if p not in self._watch_observations())
        if not providers:
            return True
        self.quota_busy = True
        self.quota_button.set_sensitive(False)
        self.quota_button.set_label("Checking quota…")
        def show(value, error):
            self.quota_busy = False
            self.quota_button.set_sensitive(True)
            self.quota_button.set_label("Check quota now")
            if error:
                self._message("Quota refresh failed: " + error, "error")
            for provider, (quota, problem) in (value or {}).items():
                self.quota_errors[provider] = problem or ""
                if quota is not None:
                    self.quotas[provider] = quota
                    self.quota_updated = time.time()
                    self.quota_checked[provider] = self.quota_updated
            self._sync_quota_display()
        def read_quota():
            from concurrent.futures import ThreadPoolExecutor
            config = AppConfig.load()
            def one(provider):
                try:
                    if provider == "muse":
                        value = fetch_muse_quota(config.muse_path)
                    elif provider == "claude":
                        value = fetch_claude_quota()
                    else:
                        value = fetch_quota(discover_codex(config.codex_path))
                    return provider, (value, None)
                except Exception as exc:
                    return provider, (None, str(exc))
            with ThreadPoolExecutor(max_workers=len(providers)) as pool:
                return dict(pool.map(one, providers))
        self._background(read_quota, show)
        return True

    def render_quota(self):
        if self.closed:
            return False
        self._render_overview()
        if not self.active_providers:
            self.quota_label.set_text("No installed AI providers found" if not self.discovery_busy else "Discovering installed AI providers…")
            return True
        colors = status_colors(self.quota_label)
        def window_text(window):
            label = window.label or ("5-hour" if window.window_duration_mins == 300 else "Weekly" if window.window_duration_mins == 10080 else f"{window.window_duration_mins}-minute")
            if not window.resets_at:
                return GLib.markup_escape_text(f"{label}: {window.used_percent:g}% used · window not started")
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
        lines = []
        for provider in self.active_providers or tuple(self.quotas):
            quota = self.quotas.get(provider)
            if quota is None:
                lines.append(GLib.markup_escape_text(PROVIDER_LABELS.get(provider, provider) + ": quota unavailable"))
                continue
            lines.append("<b>" + GLib.markup_escape_text(PROVIDER_LABELS.get(provider, provider)) + "</b>" + (" · last known quota" if self.quota_errors.get(provider) else "") + " · " +
                         " · ".join(window_text(w) for w in quota_windows(quota)))
            if quota.has_credits or quota.unlimited_credits:
                lines.append("Additional credits are available" + (" · backend still reports a limit" if quota.rate_limit_reached or quota.spend_control_reached else " · usable without waiting for the included window reset"))
        lines.append(f"Quota checked per provider · automatic refresh every {self.quota_interval}s" + (" · Latest refresh failed · see provider tabs" if self.quota_error else ""))
        update_selectable_markup(self.quota_label, "\n".join(lines))
        return True

    def _apply_provider_config(self, config):
        self.config = config
        self.set_title("Recharge AI-task")

    def settings(self, *_):
        from .settings_ui import SettingsDialog
        config = SettingsDialog(self).edit()
        if config is not None:
            self._apply_provider_config(config)
            self._configure_quota_poll(config.poll_seconds)
            self._reload_saved_settings()
            self.refresh()
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

    def _work(self, job, done, *, provider=None):
        self._busy(True)
        def worker():
            try:
                result, error = job(), None
            except Exception as exc:
                result, error = None, str(exc)
            def finish():
                self._busy(False)
                if error:
                    self._message(error, "error", provider=provider)
                else:
                    done(result)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=worker, daemon=True).start()

    def _apply_inventory(self, inventory):
        providers = tuple(dict.fromkeys((*inventory.providers, *(t.provider for t in inventory.targets), *(t.provider for t in self.selected.values()))))
        self.installed_providers = (inventory.installed_providers if inventory.installed_providers is not None else
            inventory.providers or tuple({target.provider for target in inventory.targets}))
        if providers != self.active_providers:
            self.active_providers = providers
            self.refresh_quota()
        live = {t.key: t.with_preferences(self.preferences.get(t.key)) for t in inventory.targets}
        for key, saved in list(self.selected.items()):
            self.selected[key] = live.get(key, replace(saved, task_status="Unavailable", goal_status="Unavailable")).with_preferences(saved)
        targets = {**live, **{k: t for k, t in self.selected.items() if k not in live}}
        self.targets = dict(targets)
        # Update existing rows in place so refresh preserves focus and scrolling.
        rows = {}
        for index in range(len(self.store) - 1, -1, -1):
            row = self.store[index]
            key = row[17]
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
                target.last_active_at or 0.0, target.provider, target.key]
            iterator = rows.get(key)
            if iterator is None:
                self.store.append(values)
            else:
                self.store.set(iterator, list(range(len(values))), values)
        self.filtered.refilter()
        self.provider_notices = {p: "\n".join(rows) for p, rows in inventory.provider_warnings.items()}
        scoped_warnings = {warning for rows in inventory.provider_warnings.values() for warning in rows}
        warnings = "\n".join(w for w in inventory.warnings if w not in scoped_warnings)
        if warnings and warnings != self._inventory_notice:
            self._message(warnings, "warning")
        self._inventory_notice = warnings
        self.inventory_status.set_text(f"{len(inventory.targets)} targets · Status refreshed {time.strftime('%H:%M:%S')} · Every 15 seconds"
            + (f" · {len(inventory.warnings)} warning(s); see provider tabs or program log" if inventory.warnings else ""))
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
        self.recipient_panel.select_recipient(target.key if target.key in self.selected else None, preserve_selection=True)

    def highlight_recipient(self, key):
        """Reveal the same stable recipient identity without changing its actions."""
        target = self.selected.get(key)
        if target is None:
            return

        def matching_path():
            for row in self.filtered:
                if row[17] == target.key:
                    return row.path
            return None

        path = matching_path()
        if path is None and self.provider_filter.get_active_id() not in ("all", target.provider):
            self.provider_filter.set_active_id(target.provider)
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
        return self.targets[row[17]]

    def open_row(self, *_):
        try:
            target = self._row_target()
            self._work(lambda: open_target(target), lambda _: self._message("Chat opened. Refresh to update the list.", provider=target.provider), provider=target.provider)
        except Exception as exc:
            self._message(str(exc), "error")

    def copy_row(self, *_):
        try:
            target = self._row_target()
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(target.deeplink or target.id, -1)
            self._message("Copied.", provider=target.provider)
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
            config.recipient_keys = list(self.selected)
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
            if self._can_auto_start_watch():
                self.toggle_watch(ensure_started=True, wait_for_block=True)
        return True

    def _can_auto_start_watch(self):
        """Only known, current exhaustion can opt a newly added recipient in."""
        now = time.time()
        for provider in {target.provider for target in self.selected.values() if any(target.signal_actions())}:
            quota = self.quotas.get(provider)
            checked = self.quota_checked.get(provider)
            if (quota is None or self.quota_errors.get(provider) or checked is None
                    or not 0 <= now - checked <= max(10, self.config.poll_seconds * 2)
                    or not quota_blocked(quota)):
                return False
        return any(any(t.signal_actions()) for t in self.selected.values())

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
        if not any(any(t.signal_actions()) for t in self.selected.values()):
            self._message("Enable at least one recipient action before sending.", "warning")
            return
        selected = [t for t in self.selected.values() if any(t.signal_actions())]
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
                self._message(f"{result.target.title} [{result.target.id}]: {result.detail}",
                              "error" if not result.success else "warning" if result.skipped else "success", provider=result.target.provider)
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
