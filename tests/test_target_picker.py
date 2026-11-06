"""Opt-in GTK regression using synthetic targets and isolated settings."""
import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires Linux GTK and a display")
def test_picker_filters_selects_and_saves():
    result = subprocess.run([sys.executable, "-c", r'''
from recharge_ai_task import target_ui
from recharge_ai_task.targets import Inventory, Target
from recharge_ai_task.target_delivery import DeliveryResult
from recharge_ai_task.config import AppConfig, config_dir
from recharge_ai_task.quota import Quota, RateWindow
from recharge_ai_task import autostart
from pathlib import Path
from dataclasses import replace
import time
# Keep GUI tests offline and startup changes confined to this test directory.
autostart.autostart_target = lambda: config_dir() / "test.desktop"
target_ui.discover_codex = lambda _: "codex"
current_quota = Quota("test", RateWindow(42,300,int(time.time())+3600), RateWindow(23,10080,int(time.time())+86400),False)
target_ui.fetch_quota = lambda _: current_quota
runtime = {"desktop_watch": False, "launched_at_startup": True}
commands = []
def control(command="status", **kwargs):
    commands.append(command)
    if command == "start-watch":
        runtime["desktop_watch"] = True
        runtime["watch_settings"] = target_ui.tray_control.watch_settings(AppConfig.load())
    if command == "stop-watch": runtime["desktop_watch"] = False
    return dict(runtime)
target_ui.tray_control.request = control
target_ui.send_signals = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Preference edits sent signals"))
from gi.repository import GLib, Gtk
alpha = Target("thread", "alpha", "Same title", instance="profile", deeplink="codex://threads/alpha", task_status="Running", goal_status="Active", project_name="Named project", cwd="/projects/alpha")
beta = Target("thread", "beta", "Same title", instance="profile", deeplink="codex://threads/beta", task_status="Idle", goal_status="Paused", project_name="Other project", cwd="/projects/beta")
target_ui.discover_targets = lambda: Inventory([alpha, beta])
AppConfig().save()
window = target_ui.TargetPicker()
# These checks drive widgets directly and must not consume desktop typing.
window.set_accept_focus(False)
window.set_focus_on_map(False)
window.show_all()
errors = []
def idle():
    deadline = time.monotonic() + 3
    while window.busy or window.runtime_busy or window.quota_busy or window.discovery_busy:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        assert time.monotonic() < deadline
        time.sleep(.005)
def path_for(identity):
    return next(str(i) for i,row in enumerate(window.filtered) if row[4]==identity)
def check():
    if window.busy or window.runtime_busy or window.quota_busy or window.discovery_busy:
        return True
    try:
        # Sorting an action moves rows during toggles. Recipient identity and
        # both saved actions must still refer to the clicked chat.
        window.table_layout.sort("id", True)
        assert window.filtered[0][4] == "beta"
        window._toggle(None, "0", "send_goal")
        idle()
        window.table_layout.sort("send_goal", True)
        window._toggle(None, "0")
        assert [(t.id, t.send_prompt, t.send_goal) for t in window.selected.values()] == [("beta", True, True)]
        window._toggle(None, "0", "send_goal")
        beta_path = next(str(i) for i, row in enumerate(window.filtered) if row[4] == "beta")
        window._toggle(None, beta_path)
        assert not window.selected
        window.table_layout.sort("id")
        assert window.get_title() == "Recharge AI-task"
        assert window.logo.get_pixbuf().get_width() == 64
        assert {icon.get_width() for icon in window.get_icon_list()} == {16,24,32,48,64,128,256}
        assert not any(isinstance(child, Gtk.Label) and "Choose chats by ID" in child.get_text() for child in window.get_child().get_children())
        assert not hasattr(window, "save_state")
        assert "42%" in window.quota_label.get_text()
        assert "Weekly" in window.quota_label.get_text() and "resets" in window.quota_label.get_text()
        assert not hasattr(window, "startup_label")
        assert not hasattr(window,"recipient_label")
        assert window.next_check_label.get_text() == "—"
        assert "monitoring is off" in window.next_check_detail.get_text()
        visible_titles = lambda: [c.get_title() for c in window.table.get_columns() if c.get_visible()]
        assert visible_titles() == ["Project", "Send message", "Resume goal", "Title", "Last active", "Task status", "Goal status"]
        assert "Editing them sends nothing now" in window.selection_help.get_text()
        assert "monitoring off" in window.send_button.get_tooltip_text()
        assert not window.send_button.get_sensitive()
        assert "paused goal" in window.table_layout.columns["send_goal"][0].get_widget().get_tooltip_text()
        assert not window.technical_toggle.get_active()
        view_settings = AppConfig.load()
        watch_settings = target_ui.tray_control.watch_settings(view_settings)
        window.technical_toggle.set_active(True)
        assert AppConfig.load().show_technical_columns
        assert len(visible_titles()) == 15
        reopened = target_ui.TargetPicker()
        assert reopened.technical_toggle.get_active()
        assert all(c.get_visible() for c in reopened.technical_columns)
        reopened.destroy()
        # Hiding a focused technical cell retains the row and moves its cursor
        # into a visible column. Column widths and signal choices are retained.
        technical = window.technical_columns[0]
        technical.set_fixed_width(345)
        window.table.set_cursor(Gtk.TreePath.new_from_string("0"), technical)
        selected_id = window._row_target().id
        window.technical_toggle.set_active(False)
        assert not AppConfig.load().show_technical_columns
        assert window._row_target().id == selected_id
        assert window.table.get_cursor()[1] is window.title_column
        assert technical.get_fixed_width() == 345
        assert target_ui.tray_control.watch_settings(AppConfig.load()) == watch_settings
        assert AppConfig.load().desktop_targets == view_settings.desktop_targets
        assert AppConfig.load().continue_prompt == view_settings.continue_prompt
        # The toolbar immediately follows the list: Refresh, status, Copy.
        toolbar = window.list_toolbar
        assert toolbar.get_children() == [window.refresh_button, window.toolbar_spacer, window.copy_button, window.open_button]
        siblings = toolbar.get_parent().get_children()
        assert siblings[siblings.index(toolbar)-1] is window.inventory_status
        assert siblings[siblings.index(toolbar)-2] is window.table.get_parent()
        assert "Save selection" not in [button.get_label() for button in window.buttons]
        assert window.send_row.get_children() == [window.summary]
        assert window.send_button.get_parent() is window.prompt_actions
        assert window.compose_group.get_children() == [window.default_group.get_parent(), window.send_row]
        assert window.recipient_panel.default_controls.get_parent() is window.default_group.get_parent()
        assert window.main_split.get_child1() is window.list_area
        assert window.workspace_split.get_child1() is window.left_workspace
        assert window.workspace_split.get_child2() is window.right_workspace
        assert not hasattr(window, "message_split")
        assert "message_log" not in window.window_layout.panes
        assert window.log_area.get_children()[-1] is window.status
        assert not hasattr(window, "startup_toggle")
        assert window.logo_link.get_valign() == Gtk.Align.START
        assert window.monitoring_card.get_allocated_width() < 300
        assert window.prompt_scroller.get_allocated_width() < window.get_size().width * .6
        assert window.status.get_allocated_width() < window.get_size().width * .6
        assert window.recipient_frame.translate_coordinates(window,0,0)[1] > window.logo_link.translate_coordinates(window,0,0)[1]
        assert window.recipient_frame.translate_coordinates(window.right_workspace,0,0)[1]+window.recipient_frame.get_allocated_height()==window.right_workspace.get_allocated_height()
        # Narrow layouts retain the editor, send controls and log without overlap.
        window.resize(1120, 820)
        until = time.monotonic() + .2
        while time.monotonic() < until:
            while Gtk.events_pending(): Gtk.main_iteration_do(False)
            time.sleep(.003)
        assert window.get_size().width <= 1120 and window.get_size().height <= 820
        message_height = window.message_area.get_allocated_height()
        send_y = window.send_row.translate_coordinates(window.message_area, 0, 0)[1]
        assert send_y >= window.default_editor.get_allocated_height()
        assert send_y + window.send_row.get_allocated_height() <= message_height
        assert window.status.get_allocated_height() >= 36
        assert isinstance(window.signal, Gtk.TextView)
        assert window.signal.get_wrap_mode() == Gtk.WrapMode.WORD_CHAR
        assert isinstance(window.status, Gtk.ScrolledWindow)
        assert window.status.get_allocated_height() >= 36 and not window.status.view.get_editable()
        from recharge_ai_task.status_display import COLORS, TASK_STATES, GOAL_STATES, status_level
        # Each window gets its own threshold color, including recovery to normal.
        for primary, secondary in ((84.9,85), (85,100), (99.9,84.9), (100,99.9), (101,0), (0,0)):
            window.quota = replace(current_quota,
                primary=replace(current_quota.primary, used_percent=primary),
                secondary=replace(current_quota.secondary, used_percent=secondary))
            window.render_quota()
            markup_lines = window.quota_label.get_label().split("\n")
            for line, percent in zip(markup_lines[:2], (primary,secondary)):
                if percent >= 100:
                    assert line.startswith('<span foreground="' + COLORS["error"] + '">')
                elif percent >= 85:
                    assert line.startswith('<span foreground="' + COLORS["warning"] + '">')
                else:
                    assert "<span" not in line
                assert f"{percent:g}% used" in line
                if percent >= 85:
                    assert "% used</span> · resets" in line
            assert "<span" not in markup_lines[2]
            # GTK parses the colors while selectable text stays free of markup.
            assert "<span" not in window.quota_label.get_text()
            layout = window.quota_label.get_layout()
            attributes = layout.get_attributes()
            foregrounds = [line for line in attributes.to_string().splitlines() if " foreground " in line]
            expected = []
            offset = 0
            for line, percent in zip(window.quota_label.get_text().split("\n")[:2], (primary,secondary)):
                length = len(line.encode("utf-8"))
                if percent >= 85:
                    color = COLORS["error" if percent >= 100 else "warning"]
                    pango_color = "#" + "".join(color[i:i+2]*2 for i in (1,3,5))
                    used_length = len(line.split(" · resets", 1)[0].encode("utf-8"))
                    expected.append(f"{offset} {offset+used_length} foreground {pango_color}")
                offset += length + 1
            assert foregrounds == expected, (foregrounds, expected)
        window.quota = current_quota
        window.render_quota()
        from datetime import datetime
        from unittest.mock import patch
        from recharge_ai_task import status_log
        local_time = datetime(2026,10,10,14,23,45).astimezone()
        with patch.object(status_log, "datetime") as clock:
            clock.now.return_value = local_time
            for level in ("normal", "warning", "error", "success"):
                window._message("Message " + level, level)
                assert window.status.latest_text == "Message " + level
                assert window.status.latest_level == level
                last = window.status.buffer.get_end_iter()
                last.backward_char()
                assert [tag.get_property("name") for tag in last.get_tags()] == [level]
                assert window.status.buffer.get_tag_table().lookup(level).get_property("foreground-set") == (level != "normal")
            window._message("First line\nSecond line", "warning")
        log_text = window.status.buffer.get_text(window.status.buffer.get_start_iter(), window.status.buffer.get_end_iter(), True)
        assert log_text.endswith("\n".join("[2026-10-10 14:23:45] Message " + level for level in ("normal", "warning", "error", "success")) + "\n[2026-10-10 14:23:45] First line\nSecond line")
        window._message("")
        assert window.status.buffer.get_text(window.status.buffer.get_start_iter(), window.status.buffer.get_end_iter(), True) == log_text
        window._message("\n".join("Long diagnostic line " + str(i) for i in range(60)), "error")
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        adjustment = window.status.get_vadjustment()
        assert adjustment.get_upper() > adjustment.get_page_size()
        assert window.get_allocated_height() < 1000
        window._message("\n".join("Bounded line " + str(i) for i in range(1100)))
        assert window.status.buffer.get_line_count() <= 1000
        for index, states in ((10, TASK_STATES), (11, GOAL_STATES)):
            column = next(c for c in window.table.get_columns() if c.get_title() == ("Task status" if index == 10 else "Goal status"))
            header = column.get_widget()
            assert isinstance(header, Gtk.Box)
            assert " ".join(header.get_children()[0].get_text().split()) == column.get_title()
            info = header.get_children()[1]
            assert isinstance(info, Gtk.Button) and info.get_can_focus()
            assert info.get_image().get_icon_name()[0] == "dialog-information-symbolic"
            assert "F1" not in info.get_tooltip_text() and "Enter" in info.get_tooltip_text()
            info._build()
            assert len(info.badges) == 2*(len(states)+1)
            renderer = column.get_cells()[0]
            original = window.store[0][index]
            for value in states:
                window.store[0][index] = value
                window._status_cell(column, renderer, window.store, window.store[0].iter, index)
                assert renderer.get_property("foreground-set") == (status_level(value, goal=index == 11) != "normal")
                if value == "Complete":
                    assert renderer.get_property("text") == "✓ Complete"
                    attributes = renderer.get_property("attributes")
                    attr_iterator = attributes.get_iterator()
                    attrs = attr_iterator.get_attrs()
                    assert len(attrs) == 1 and attrs[0].start_index == 0 and attrs[0].end_index == 3
                # Exercise the actual hover hit-testing against rendered cells.
                cell = window.table.get_cell_area(Gtk.TreePath.new_from_string("0"), column)
                x, y = window.table.convert_bin_window_to_widget_coords(cell.x + 8, cell.y + cell.height//2)
                class Tooltip:
                    def set_text(self, value): self.text = value
                tooltip = Tooltip()
                original_cell = window.table.set_tooltip_cell
                window.table.set_tooltip_cell = lambda *args: None
                assert window._tooltip(window.table, x, y, False, tooltip)
                window.table.set_tooltip_cell = original_cell
                assert value in tooltip.text and "statuses" in tooltip.text
            window.store[0][index] = original
        assert "watch-off" in window.monitoring_card.get_style_context().list_classes()
        window.runtime = {"desktop_watch": True, "watch_settings": target_ui.tray_control.watch_settings(AppConfig.load()),
            "watch_progress": {"phase": "waiting_quota", "next_check_at": time.time()+30}}
        window.render_quota()
        assert window.next_check_label.get_text() == "In 00:30"
        assert "Waiting for quota" in window.next_check_detail.get_text()
        window.runtime = dict(runtime)
        window._render_runtime()
        window.search.set_text("Named project")
        window.filtered.refilter()
        assert len(window.filtered) == 1 and window.filtered[0][4] == "alpha"
        assert window.filtered[0][13] == "Named project" and window.filtered[0][8] == "/projects/alpha"
        window.search.set_text("beta")
        window.filtered.refilter()
        assert len(window.filtered) == 1
        window._toggle(None, "0")
        idle()
        assert list(window.selected.values()) == [replace(beta, send_prompt=True, send_goal=False)]
        assert not hasattr(window,"recipient_label")
        assert window.send_button.get_label() == "Send now to 1 recipient"
        assert window.send_button.get_sensitive()
        assert not window.dirty() and not hasattr(window, "save_state")
        assert [c.get_title() for c in window.table.get_columns()][:9] == ["Project", "Send message", "Resume goal", "Title", "Last active", "Task status", "Goal status", "Project path", "Kind"]
        window.table.get_selection().select_path("0")
        target_ui.discover_targets = lambda: Inventory([alpha, replace(beta, task_status="Waiting for input", goal_status="Blocked")])
        window.refresh_statuses()
        assert not window.busy and window.table.get_sensitive()
        idle()
        assert window._row_target().id == "beta"
        assert not window.dirty() and list(window.selected) == [beta.key]
        assert window.filtered[0][10:12] == ["Waiting for input", "Blocked"]
        assert "Every 15 seconds" in window.inventory_status.get_text()
        window.search.set_text("blocked")
        window.filtered.refilter()
        assert len(window.filtered) == 1
        # Selected recipients remain visible when discovery no longer finds them.
        target_ui.discover_targets = lambda: Inventory([alpha])
        window.search.set_text("beta")
        window.filtered.refilter()
        window.refresh_statuses()
        idle()
        assert list(window.selected) == [beta.key]
        assert window.filtered[0][10:12] == ["Unavailable", "Unavailable"]
        assert window.filtered[0][3] == "Unavailable — saved selection"
        target_ui.discover_targets = lambda: Inventory([alpha, beta])
        window.refresh_statuses()
        idle()
        window.toggle_watch()
        idle()
        assert "Restart the tray" in window.status.latest_text
        assert "start-watch" not in commands
        window.search.set_text("")
        window.filtered.refilter()
        window._toggle(None, path_for("alpha"))
        window.signal_buffer.set_text("Continue")
        saved = AppConfig.load()
        assert {t.id for t in saved.targets()} == {"alpha", "beta"}
        assert saved.continue_prompt == "Continue"
        assert all(t.send_prompt and not t.send_goal for t in saved.targets())
        assert not window.dirty() and not hasattr(window, "save_state")
        window.signal_buffer.set_text("First line\nSecond line\n\nFinal line")
        assert AppConfig.load().continue_prompt == "First line\nSecond line\n\nFinal line"
        assert window._prompt_text() == AppConfig.load().continue_prompt
        assert not window.dirty()
        window.signal_buffer.set_text("Continue")
        assert not window.dirty()
        # Each row independently persists Prompt and Goal through refreshes.
        deliveries = []
        def send_signals(targets, text, *, manual=False):
            deliveries.append(([(t.id, t.send_prompt, t.send_goal) for t in targets], text, manual))
            return [DeliveryResult(t, True, "Selected signals accepted") for t in targets]
        target_ui.send_signals = send_signals
        assert window.send_button.get_label() == "Send now to 2 recipients"
        assert not hasattr(window, "goal")
        window._toggle(None, path_for("beta"), "send_goal")  # beta: both
        assert {t.id: t.signal_actions() for t in AppConfig.load().targets()}["beta"] == (True, True)
        window._toggle(None, path_for("beta"), "send_prompt")  # beta: Goal only
        assert window.selected[beta.key].signal_actions() == (False, True)
        window.refresh_statuses()
        idle()
        assert window.selected[beta.key].signal_actions() == (False, True)
        assert not window.dirty()
        assert window.send_button.get_sensitive() and "monitoring off" in window.send_button.get_tooltip_text()
        window.send_button.clicked()
        assert window.status.latest_level == "success"
        idle()
        assert deliveries == [([("beta", False, True), ("alpha", True, False)], "Continue", True)]
        assert "Signals: 2 accepted, 0 skipped, 0 failed" in window.status.latest_text
        window.signal_buffer.set_text("First line\nSecond line\n\nFinal line")
        window.send()
        idle()
        assert deliveries[-1][1] == "First line\nSecond line\n\nFinal line"
        assert AppConfig.load().continue_prompt == deliveries[-1][1]
        window.signal_buffer.set_text("Continue")
        idle()
        assert {t.id: t.signal_actions() for t in AppConfig.load().targets()} == {"alpha": (True, False), "beta": (False, True)}
        assert not window.dirty()
        window.toggle_watch()
        idle()
        assert "Restart the tray" in window.status.latest_text
        assert "start-watch" not in commands
        runtime["per_target_signals"] = True
        # Blank text is valid for Goal-only recipients, and invalid for Prompt.
        window._toggle(None, path_for("alpha"), "send_prompt")
        window.signal_buffer.set_text(" ")
        window.send()
        idle()
        assert deliveries[-1] == ([("beta", False, True)], " ", True)
        window._toggle(None, path_for("alpha"), "send_prompt")
        window.send()
        assert "Enter a message" in window.status.latest_text and window.status.latest_level == "warning"
        window.signal_buffer.set_text("Continue")
        idle()
        # Monitoring status shares the heading; startup information lives in Settings.
        assert window.watch_label.get_parent().get_children()[0] is window.monitoring_heading
        assert not hasattr(window, "startup_toggle")
        # A failed automatic refresh must not show the last statuses as live.
        target_ui.discover_targets = lambda: (_ for _ in ()).throw(RuntimeError("disconnected"))
        window.refresh_statuses()
        idle()
        assert all(row[10:12] == ["Unavailable", "Unavailable"] for row in window.store)
        assert "failed" in window.inventory_status.get_text()
        assert "disconnected" in window.status.latest_text and window.status.latest_level == "error"
        assert not window.dirty()
        from recharge_ai_task.settings_ui import SettingsDialog
        dialog = SettingsDialog(window)
        assert not hasattr(dialog, "language")
        assert not any(isinstance(widget, Gtk.Label) and widget.get_text() == "Language" for widget in dialog.get_content_area().get_children()[0].get_children())
        dialog.grace.set_value(37)
        dialog.poll.set_value(9)
        dialog.autostart.set_active(True)
        dialog.save_settings()
        dialog.destroy()
        settings = AppConfig.load()
        assert settings.grace_seconds == 37 and settings.poll_seconds == 9
        assert {t.id for t in settings.targets()} == {"alpha", "beta"}
        assert "--autostart" in autostart.autostart_target().read_text()
        window._render_runtime()
        assert autostart.is_autostart_enabled()
        idle()
        window.toggle_watch()
        idle()
        assert window.watch_label.get_text() == "On"
        assert window.watch_button.get_label() == "Stop Desktop watch"
        assert "watch-on" in window.monitoring_card.get_style_context().list_classes()
        changed = AppConfig.load()
        changed.poll_seconds += 1
        changed.save()
        window.poll_runtime()
        idle()
        assert window.watch_label.get_text() == "Reloading"
        runtime["stopping"] = True
        window.poll_runtime()
        idle()
        assert "Stopping" in window.watch_label.get_text()
        assert not window.watch_button.get_sensitive()
        assert "watch-stopping" in window.monitoring_card.get_style_context().list_classes()
        runtime["stopping"] = False
        window.toggle_watch()
        idle()
        assert window.watch_label.get_text() == "Off"
        assert "watch-off" in window.monitoring_card.get_style_context().list_classes()
        # Deselecting the last action removes that recipient on disk immediately.
        window._toggle(None, path_for("beta"), "send_goal")
        assert {t.id for t in AppConfig.load().targets()} == {"alpha"}
        window._toggle(None, path_for("beta"), "send_goal")
        assert {t.id: t.signal_actions() for t in AppConfig.load().targets()} == {"alpha": (True, False), "beta": (False, True)}
        # Failed writes remain visibly unsaved and retry without losing choices.
        idle()
        before = AppConfig.load().desktop_targets
        original_save = AppConfig.save
        AppConfig.save = lambda _: (_ for _ in ()).throw(OSError("disk unavailable <test>"))
        window._toggle(None, path_for("beta"), "send_prompt")
        assert AppConfig.load().desktop_targets == before
        assert window.dirty() and window.status.latest_level == "error" and "Could not save automatically" in window.status.latest_text
        assert "<test>" in window.status.latest_text
        AppConfig.save = original_save
        window.poll_runtime()
        idle()
        assert not window.dirty() and not window.autosave_error and not hasattr(window, "save_state")
        assert {t.id: t.signal_actions() for t in AppConfig.load().targets()}["beta"] == (True, True)
        changed = AppConfig.load()
        changed.continue_prompt = "External edit"
        changed.save()
        window.poll_runtime()
        idle()
        assert window.dirty() and window.status.latest_level == "warning" and "differ from saved settings" in window.status.latest_text
        assert AppConfig.load().continue_prompt == "External edit"
        target_ui.fetch_quota = lambda _: (_ for _ in ()).throw(RuntimeError("offline"))
        window.refresh_quota()
        idle()
        assert "42%" in window.quota_label.get_text()
        assert "Latest refresh failed" in window.quota_label.get_text()
        assert "offline" in window.status.latest_text and window.status.latest_level == "error"
    except Exception as exc:
        import traceback
        errors.append(traceback.format_exc())
    finally:
        window.destroy()
    return False
GLib.timeout_add(100, check)
Gtk.main()
assert not errors, errors
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert "CRITICAL" not in result.stderr, result.stderr
