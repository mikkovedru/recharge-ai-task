"""Saved column migration and theme-aware inherited message previews."""
import os
import subprocess
import sys
import pytest

_SETUP = r'''

import time
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.quota import Quota,RateWindow
from gi.repository import Gtk

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'offline'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(10,300,9999999999),None,False)
target=Target('thread','demo','Demo chat',project_name='Demo project',send_prompt=True,send_goal=False)
target_ui.discover_targets=lambda:Inventory([target])
target_ui.tray_control.request=lambda *a,**kw:{'desktop_watch':False}
target_ui.send_signals=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('View changes sent signals'))
AppConfig(desktop_targets=[target.to_dict()],table_layout={'order':['send_prompt','send_goal','title','project_name'], 'widths':{'title':177}}).save()
def pump(w):
    end=time.monotonic()+.2
    while time.monotonic()<end or w.discovery_busy or w.runtime_busy or w.quota_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def make():
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    return w
'''


def run_gui(source):
    result=subprocess.run([sys.executable,'-c',_SETUP+source],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')
def test_project_moves_first_and_keeps_saved_widths():
    run_gui(r'''
w=make()
assert w.table.get_columns()[0].get_title()=='Project'
assert w.title_column.get_fixed_width()==177
w.table.move_column_after(w.title_column,None)
w.table_layout.close();w.destroy()
w=make()
assert w.table.get_columns()[0].get_title()=='Title'
assert w.title_column.get_fixed_width()==177
w.destroy()
config=AppConfig.load();config.table_layout=None;config.save()
w=make();assert w.table.get_columns()[0].get_title()=='Project';w.destroy()
''')


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')
def test_custom_preview_tracks_checkbox_in_both_themes():
    run_gui(r'''
w=make();panel=w.recipient_panel
for dark in (False,True):
    settings=Gtk.Settings.get_default()
    settings.set_property('gtk-theme-name','Adwaita')
    settings.set_property('gtk-application-prefer-dark-theme',dark)
    panel.custom.set_active(False);pump(w)
    passive=panel.message.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
    assert not panel.message.get_editable() and not panel.message.get_cursor_visible()
    assert 'Default message preview' in panel.message.get_tooltip_text()
    panel.custom.set_active(True);pump(w)
    active=panel.message.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
    assert panel.message.get_editable() and panel.message.get_cursor_visible()
    assert passive.to_string()!=active.to_string(),(dark,passive,active)
    panel.message_buffer.set_text('Custom draft')
    w._summary();pump(w)
    assert panel.message.get_editable() and 'Custom draft' in panel.message_buffer.get_text(*panel.message_buffer.get_bounds(),True)
w.destroy()
w=make()
assert w.recipient_panel.custom.get_active() and w.recipient_panel.message.get_editable()
w.destroy()
''')
