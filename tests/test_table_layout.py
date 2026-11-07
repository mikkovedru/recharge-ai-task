"""Exercise GTK layout behavior with isolated settings and synthetic recipients."""
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires Linux GTK and a display")
def test_saved_columns_sort_wrap_and_keep_recipient_identity():
    result = subprocess.run([sys.executable, "-c", r'''
from gi.repository import Gtk, Pango
from recharge_ai_task.config import AppConfig
from recharge_ai_task.table_layout import TableLayout

def make(saved=None):
    store = Gtk.ListStore(bool, str, str, str, str, str, str)
    for row in [(False, "Zulu " * 24, "thread", "", "a", "100", "profile"),
                (False, "Alpha", "thread", "", "b", "9", "profile")]:
        store.append(row)
    filtered = store.filter_new()
    table = Gtk.TreeView(model=filtered)
    errors = []
    layout = TableLayout(table, store, saved, lambda *args: errors.append(args))
    for key, index in [("send_prompt", 0), ("title", 1), ("pid", 5)]:
        cell = Gtk.CellRendererToggle() if index == 0 else Gtk.CellRendererText()
        col = Gtk.TreeViewColumn(key, cell, **{"active" if index == 0 else "text": index})
        if index == 0:
            col.set_widget(Gtk.Label(label="Send message"))
        table.append_column(col)
        layout.register(key, col, index, 150, None if index == 0 else cell)
    layout.restore()
    return store, filtered, table, layout, errors

AppConfig(continue_prompt="Keep this message", desktop_targets=[{"kind":"thread","id":"keep","title":"Keep"}]).save()
store, filtered, table, layout, errors = make()
window = Gtk.Window()
window.set_accept_focus(False)
window.set_focus_on_map(False)
window.add(table)
window.show_all()
def events():
    import time
    earliest = time.monotonic() + .15
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        settled = not layout.geometry_pending and layout.geometry_timer is None
        for col, _index in layout.columns.values():
            for renderer in col.get_cells():
                if isinstance(renderer, Gtk.CellRendererText):
                    settled = settled and renderer.get_property("wrap-width") == max(1, col.get_width() - 6)
        if time.monotonic() >= earliest and settled:
            return
        time.sleep(.002)
events()
assert table.get_columns()[0].get_widget().get_allocation().height < 80
assert table.get_halign() == Gtk.Align.START
assert all(cell.get_property("xpad") == 2 for col in table.get_columns() for cell in col.get_cells())
assert all(col.get_resizable() and col.get_reorderable() and col.get_clickable() for col in table.get_columns())
title = layout.columns["title"][0]
pid = layout.columns["pid"][0]
# Header clicks sort both ways, including numeric process IDs.
title.clicked()
assert [r[4] for r in filtered] == ["b", "a"]
assert title.get_sort_indicator() and title.get_sort_order() == Gtk.SortType.ASCENDING
title.clicked()
assert [r[4] for r in filtered] == ["a", "b"]
pid.clicked()
assert [r[5] for r in filtered] == ["9", "100"]
# Long text increases row height after narrowing, with no ellipsis.
cell = title.get_cells()[0]
assert cell.get_property("wrap-mode") == Pango.WrapMode.WORD_CHAR
assert cell.get_property("ellipsize") == Pango.EllipsizeMode.NONE
title.set_fixed_width(310)
events()
original_header = title.get_button().get_allocated_height()
wide = table.get_background_area(Gtk.TreePath.new_from_string("1"), title).height
title.set_fixed_width(95)
events()
narrow = table.get_background_area(Gtk.TreePath.new_from_string("1"), title).height
assert narrow > wide, (narrow, wide)
# Very narrow headers must stay at two lines instead of growing the whole header.
for width in (36,60,110,310,36,310):
    title.set_fixed_width(width)
    events()
    assert title.get_button().get_allocated_height() <= original_header * 2 + 4
    assert cell.get_property("wrap-width") == title.get_width()-6
assert table.get_background_area(Gtk.TreePath.new_from_string("1"),title).height==wide
assert layout.geometry_timer is None and not layout.geometry_pending
# Reordering, resizing and sort survive closing, even before the debounce.
title.set_fixed_width(95)
events()
table.move_column_after(pid, None)
layout.close()
assert not errors
config = AppConfig.load()
assert config.continue_prompt == "Keep this message" and config.desktop_targets[0]["id"] == "keep"
assert config.table_layout["order"] == ["pid", "send_prompt", "title"]
assert config.table_layout["widths"]["title"] == 95
other_store, other_filter, other, restored, errors = make(config.table_layout)
assert [c.get_title() for c in other.get_columns()] == ["pid", "send_prompt", "title"]
assert restored.columns["title"][0].get_fixed_width() == 95
assert [r[5] for r in other_filter] == ["9", "100"]
# Sorting is retained when the source is refreshed, and a filter preserves order.
other_store.append([False,"Beta","thread","","c","20","profile"])
assert [r[5] for r in other_filter] == ["9", "20", "100"]
other_filter.set_visible_func(lambda model, it, data: model[it][4] != "b")
other_filter.refilter()
assert [r[4] for r in other_filter] == ["c", "a"]
restored.close()
# Old, damaged or stale preferences must not prevent opening the list.
_, _, _, invalid, errors = make({"order":["removed", [], "pid", "pid"], "widths":{"title":-1,"pid":True}, "sort_column":[]})
assert invalid.columns["title"][0].get_fixed_width() == 150
invalid.close()
window.destroy()
'''], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_selected_message_or_goal_is_pinned_for_every_column_and_direction():
    result = subprocess.run([sys.executable, "-c", r'''
from gi.repository import Gtk
from recharge_ai_task.table_layout import TableLayout
store=Gtk.ListStore(bool,str,str,str,str,str,str,bool)
for row in [(False,'Alpha','thread','','a','1','profile',False),
            (True,'Zulu','thread','','z','99','profile',False),
            (False,'Beta','thread','','b','20','profile',True),
            (True,'Middle','thread','','m','30','profile',True)]:
    store.append(row)
table=Gtk.TreeView(model=store)
layout=TableLayout(table,store,{},lambda *a:None,selected_columns=(0,7))
for i in range(8):
    cell=Gtk.CellRendererText();col=Gtk.TreeViewColumn(str(i),cell)
    table.append_column(col);layout.register(str(i),col,i,100)
for key in layout.columns:
    for descending in (False,True):
        layout.sort(key,descending)
        assert [bool(r[0] or r[7]) for r in store]==[True,True,True,False],(key,descending)
layout.sort('1',True)
assert [r[4] for r in store]==['z','m','b','a']
# Changing either action reorders immediately, regardless of current sort key.
for row in store:
    if row[4]=='a':store.set(row.iter,[7],[True]);break
assert [r[4] for r in store]==['z','m','b','a']
for row in store:
    if row[4]=='z':store.set(row.iter,[0],[False]);break
assert [r[4] for r in store]==['m','b','a','z']
layout.close()
'''],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stdout+result.stderr
