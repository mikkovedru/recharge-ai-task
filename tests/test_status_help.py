from types import SimpleNamespace
import os
import subprocess
import sys

import pytest
from recharge_ai_task.status_display import continuation_allowed,status_rows,COLORS,DARK_COLORS


@pytest.mark.parametrize('goal',[False,True])
def test_unknown_and_error_statuses_are_allowed_in_the_info_list(goal):
    assert continuation_allowed('futureStatus',goal=goal)
    assert continuation_allowed('Error',goal=goal)
    assert ('Other / new statuses',True,True) in [row[:3] for row in status_rows(goal=goal)]
    assert not continuation_allowed('Unavailable',goal=goal)
    assert continuation_allowed('Paused',goal=True,manual=True)
    assert not continuation_allowed('Paused',goal=True)


def test_light_and_dark_status_text_have_readable_contrast():
    def lum(color):
        values=[int(color[i:i+2],16)/255 for i in (1,3,5)]
        linear=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in values]
        return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))
    for palette,bg in ((COLORS,'#ffffff'),(DARK_COLORS,'#242424')):
        for fg in palette.values():
            values=sorted([lum(fg),lum(bg)])
            assert (values[1]+.05)/(values[0]+.05)>=4.5


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')
def test_status_popup_shortcuts_and_immediate_quota_check():
    result=subprocess.run([sys.executable,'-c',r'''
import time,threading
from types import SimpleNamespace
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Inventory
from recharge_ai_task.quota import Quota,RateWindow
from recharge_ai_task.settings_ui import SettingsDialog
from gi.repository import Gtk,Gdk
from recharge_ai_task.status_help import status_markup

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'codex'
q=Quota('test',RateWindow(0,300,9999999999),None,False)
target_ui.fetch_quota=lambda _:q
target_ui.discover_targets=lambda:Inventory([])
commands=[]
def control(command='status',**kwargs):
    commands.append(command)
    return {'desktop_watch':True,'manual_quota_check':True}
target_ui.tray_control.request=control
AppConfig().save()
w=target_ui.TargetPicker(quit_on_close=False)
w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all()
def pump():
    until=time.monotonic()+.2
    while time.monotonic()<until or w.quota_busy or w.runtime_busy or w.discovery_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
pump()
assert w.get_default_widget() is None # Enter in a multiline editor does not send.
assert 'Ctrl+Enter' in w.send_button.get_tooltip_text()
assert w._keyboard(w,SimpleNamespace(keyval=Gdk.KEY_f,state=Gdk.ModifierType.CONTROL_MASK))
assert w.get_focus() is w.search
# Trigger the real accelerator; the check goes to the worker, not just the display.
assert Gtk.accel_groups_activate(w,Gdk.KEY_r,Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK)
assert w.quota_busy and not w.quota_button.get_sensitive() and 'Checking' in w.quota_button.get_label()
pump()
assert 'check-quota' in commands
button=w.status_info[11]
# Hover over the actual header info region without clicking or losing focus.
root_x,root_y=button.translate_coordinates(w,0,0)
_,wx,wy=w.get_window().get_origin()
event=SimpleNamespace(x_root=wx+root_x+3,y_root=wy+root_y+3)
old_sort=w.table_layout.sort_column
button._header_motion(button,event);pump()
assert button.popover.get_visible() and w.get_focus() is w.search
assert w.table_layout.sort_column==old_sort
# Nested crossing events and slower travel into the popup do not dismiss it.
button._pointer_inside=lambda:True
button._leave(button.popover,SimpleNamespace(detail=Gdk.NotifyType.INFERIOR))
assert button.hide_timer is None
button._leave()
end=time.monotonic()+.8
while time.monotonic()<end:pump()
assert button.popover.get_visible()
# Expanding an explanation keeps it open even after the pointer leaves.
button.expanders[0].set_expanded(True)
button._pointer_inside=lambda:False
button._leave()
end=time.monotonic()+.8
while time.monotonic()<end:pump()
assert button.popover.get_visible() and button.pinned
assert button._header_press(button,event) and w.table_layout.sort_column==old_sort
button.open();pump()
assert button.popover.get_relative_to() is w.table
assert button.popover.get_visible() and w.get_focus() is button.close_button
assert any('Continue' in label.get_text() for label,allowed in button.badges if allowed)
assert any('Skip' in label.get_text() for label,allowed in button.badges if not allowed)
assert all('foreground=' in label.get_label() for label,_ in button.badges)
assert 'futureStatus' in status_markup('futureStatus',goal=True,widget=w)
for expander in button.expanders:expander.set_expanded(True)
pump()
button._scroll_keys(button,SimpleNamespace(keyval=Gdk.KEY_Page_Down))
assert button.rules_scroll.get_vadjustment().get_value()>0
button.close_button.clicked();pump()
d=SettingsDialog(w)
assert d.get_default_widget() is d.get_widget_for_response(Gtk.ResponseType.OK)
cancel=d.get_widget_for_response(Gtk.ResponseType.CANCEL)
cancel.grab_focus()
assert d._dialog_keys(d,SimpleNamespace(keyval=Gdk.KEY_Right))
assert d.get_focus() is d.get_widget_for_response(Gtk.ResponseType.OK)
d.path.grab_focus()
assert not d._dialog_keys(d,SimpleNamespace(keyval=Gdk.KEY_Left))
d.destroy();w.destroy()
'''],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr
