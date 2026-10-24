"""Codex activity timestamps and default chat ordering."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from recharge_ai_task.targets import Target, _activity_timestamp, _saved_threads, _thread_target


@pytest.mark.parametrize(("record", "expected"), [
    ({"updatedAt": 1792800000}, 1792800000),
    ({"updated_at": 1792800000}, 1792800000),
    ({"updated_at_ms": 1792800000123, "updated_at": 1792800000}, 1792800000.123),
    ({"updated_at_ms": None, "updated_at": 1792800000}, 1792800000),
    ({"updated_at_ms": 0, "updated_at": 1792800000}, 1792800000),
    ({}, None), ({"updatedAt": None}, None), ({"updatedAt": True}, None),
    ({"updatedAt": "1792800000"}, None), ({"updatedAt": -1}, None),
    ({"updatedAt": float("nan")}, None), ({"updatedAt": float("inf")}, None),
    ({"updatedAt": 253402300800}, None),
])
def test_activity_timestamp_units_and_missing_metadata(record, expected):
    assert _activity_timestamp(record) == expected
    target = _thread_target({"id": "chat", **record}, Path("/profile"), "")
    assert target.last_active_at == expected
    assert Target.from_dict(target.to_dict()) == target


def test_database_keeps_millisecond_activity_read_only(tmp_path):
    database = tmp_path / "state_5.sqlite"
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE threads(id TEXT, title TEXT, archived INT, updated_at INT, updated_at_ms INT)")
        db.execute("INSERT INTO threads VALUES ('chat','Title',0,1792800000,1792800000789)")
    before = database.read_bytes()
    record, = _saved_threads(tmp_path)
    assert _thread_target(record, tmp_path, "").last_active_at == 1792800000.789
    assert database.read_bytes() == before


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires Linux GTK and a display")
def test_activity_column_default_sort_refresh_and_saved_override():
    result = subprocess.run([sys.executable, "-c", r'''
from dataclasses import replace
from datetime import datetime
import time
from recharge_ai_task import target_ui, autostart
from recharge_ai_task.targets import Target, Inventory
from recharge_ai_task.config import AppConfig, config_dir
from recharge_ai_task.quota import Quota, RateWindow
from gi.repository import Gtk

autostart.autostart_target = lambda: config_dir() / "test.desktop"
target_ui.discover_codex = lambda _: "codex"
target_ui.fetch_quota = lambda _: Quota("test", RateWindow(10,300,0), None, False)
target_ui.tray_control.request = lambda *args, **kwargs: {"desktop_watch": False}
target_ui.send_signals = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Table changes sent signals"))
a = Target("thread", "a", "Zulu", instance="profile", last_active_at=1792800000.2)
b = Target("thread", "b", "Alpha", instance="profile", last_active_at=1792800000.8)
unknown = Target("window", "window", "Window", instance="desktop")
target_ui.discover_targets = lambda: Inventory([a, unknown, b])
AppConfig().save()
def pump(window):
    deadline = time.monotonic() + 3
    while window.discovery_busy or window.runtime_busy or window.quota_busy or Gtk.events_pending():
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        assert time.monotonic() < deadline
        time.sleep(.002)
window = target_ui.TargetPicker(quit_on_close=False)
window.set_accept_focus(False)
window.set_focus_on_map(False)
window.show_all()
pump(window)
assert [r[4] for r in window.filtered] == ["b", "a", "window"]
column = window.table_layout.columns["last_active_at"][0]
assert column.get_visible() and column not in window.technical_columns
assert column.get_sort_indicator() and column.get_sort_order() == Gtk.SortType.DESCENDING
assert window.filtered[0][14] == datetime.fromtimestamp(b.last_active_at).astimezone().strftime("%Y-%m-%d %H:%M:%S")
assert window.filtered[2][14] == "Unknown"
# Displayed seconds match, while underlying milliseconds still sort correctly.
assert window.filtered[0][14] == window.filtered[1][14]
window.table.get_selection().select_path("0")
window._apply_inventory(Inventory([replace(a,last_active_at=1792800300), b, unknown]))
assert [r[4] for r in window.filtered] == ["a", "b", "window"]
assert window._row_target().id == "b"
window.search.set_text("profile")
window.filtered.refilter()
column.clicked()
assert [r[4] for r in window.filtered] == ["b", "a"]
# Saved sorting takes precedence over the newest-first default on reopening.
window.table_layout.columns["title"][0].clicked()
window.destroy()
assert AppConfig.load().table_layout["sort_column"] == "title"
reopened = target_ui.TargetPicker(quit_on_close=False)
pump(reopened)
assert reopened.table_layout.sort_column == "title" and not reopened.table_layout.descending
assert [r[4] for r in reopened.filtered] == ["b", "window", "a"]
reopened.destroy()
'''], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "CRITICAL" not in result.stderr, result.stderr
