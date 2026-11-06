import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_splitters_and_window_size_survive_reopening():
    result = subprocess.run([sys.executable, "-c", '''
import gi,time
gi.require_version("Gtk","3.0")
from gi.repository import Gtk
from recharge_ai_task.config import AppConfig
from recharge_ai_task.window_layout import WindowLayout

def events():
    until=time.monotonic()+.3
    while time.monotonic()<until:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.003)
def make():
    w=Gtk.Window();w.set_accept_focus(False);w.set_focus_on_map(False)
    w.set_default_size(600,420)
    layout=WindowLayout(w)
    first,second=Gtk.ScrolledWindow(),Gtk.ScrolledWindow()
    first.add(Gtk.TextView());second.add(Gtk.TextView())
    pane=layout.pane("editor_log",first,second,position=180)
    w.add(pane);w.show_all();events()
    return w,layout,pane
AppConfig(continue_prompt="Keep message",show_technical_columns=True).save()
w,layout,pane=make()
pane.set_position(120)
w.resize(720,510)
events()
position=pane.get_position()
size=list(w.get_size())
layout.close();w.destroy()
config=AppConfig.load()
assert config.continue_prompt=="Keep message" and config.show_technical_columns
assert config.ui_layout["dashboard"]["size"]==size
w,layout,pane=make()
assert list(w.get_size())==size
assert pane.get_position()==position, (pane.get_position(),position)
layout.close();w.destroy()
'''], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_corner_drag_changes_editor_allocation_and_remembers_size():
    result = subprocess.run([sys.executable, "-c", '''
import gi,time
from types import SimpleNamespace
gi.require_version("Gtk","3.0")
from gi.repository import Gtk
from recharge_ai_task.config import AppConfig
from recharge_ai_task.window_layout import WindowLayout
from recharge_ai_task.resizable_editor import ResizableEditor

def events():
    until=time.monotonic()+.35
    while time.monotonic()<until:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.003)
def make():
    w=Gtk.Window();w.set_accept_focus(False);w.set_focus_on_map(False)
    w.set_default_size(700,600)
    layout=WindowLayout(w,version=2)
    scroll=Gtk.ScrolledWindow();scroll.add(Gtk.TextView())
    editor=layout.region("message",ResizableEditor(scroll))
    body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);body.pack_start(editor,False,False,0)
    pane=layout.pane("body",body,Gtk.Label(label="Log"),position=.7)
    w.add(pane);w.show_all();events()
    return w,layout,editor
# Old pane geometry is incompatible, but the window dimensions survive.
AppConfig(ui_layout={"dashboard":{"size":[700,600],"panes":{"body":50}}}).save()
w,layout,editor=make()
assert layout.panes["body"][0].get_position()>300
original=editor.get_allocated_width(),editor.get_allocated_height()
editor._press(editor.handle,SimpleNamespace(button=1,x_root=700,y_root=90))
editor._motion(editor.handle,SimpleNamespace(x_root=580,y_root=150))
editor._release(editor.handle,SimpleNamespace(button=1))
events()
assert editor.get_allocated_width()==original[0]-120, (editor.get_allocated_width(),original)
assert editor.get_allocated_height()==original[1]+60, (editor.get_allocated_height(),original)
saved=editor.editor_size()
layout.close();w.destroy()
assert AppConfig.load().ui_layout["dashboard"]["regions"]["message"]==saved
w,layout,editor=make()
assert editor.editor_size()==saved
assert editor.get_allocated_width()==saved[0] and editor.get_allocated_height()==saved[1]
# Saved natural dimensions allow a smaller window instead of enforcing them as minima.
w.resize(430,350);events()
assert w.get_size().width<=430
assert editor.get_allocated_width()<=430
layout.close();w.destroy()
'''], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1', reason='Requires GTK')
def test_recipient_list_takes_spare_height_and_preserves_editor():
    result=subprocess.run([sys.executable,'-c',r'''
import os,subprocess,time
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Inventory,Target
from recharge_ai_task.quota import Quota,RateWindow
from gi.repository import Gtk

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'fixture'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(40,300,9999999999),None,False)
target_ui.tray_control.request=lambda *a,**kw:{'desktop_watch':False}
target=Target('thread','fixture','Fixture',send_prompt=True,send_goal=False)
target_ui.discover_targets=lambda:Inventory([target])
AppConfig(desktop_targets=[target.to_dict()]).save()
def pump(w):
    end=time.monotonic()+.2
    while time.monotonic()<end or w.discovery_busy or w.runtime_busy or w.quota_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def make():
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    return w
w=make();p=w.recipient_panel
def pos(widget,parent=w):return widget.translate_coordinates(parent,0,0)
try:
    assert pos(p)[1]<pos(w.search)[1]
    assert pos(w.recipient_frame)[1]==pos(w.right_workspace)[1]
    assert pos(w.recipient_frame)[1]+w.recipient_frame.get_allocated_height()==w.get_size().height-14
    original=p.list_scroller.get_allocated_height();editor=p.editor_scroller.get_allocated_height()
    w.resize(1440,1100);pump(w)
    assert p.list_scroller.get_allocated_height()>original+100
    assert abs(p.editor_scroller.get_allocated_height()-editor)<=3
    for width,height in ((1400,980),(1120,820)):
        w.resize(width,height);pump(w)
        assert w.get_size().width<=width and w.get_size().height<=height
        assert pos(p.message_resize,p.editor_scroller)[1]+p.message_resize.get_allocated_height()<=p.editor_scroller.get_allocated_height()
        assert p.list_scroller.get_allocated_height()>=60
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        before=p.split.get_position();x,y=pos(p.split);x+=20;y+=before+3
        xid=str(w.get_window().get_xid())
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y),'mousedown','1'],check=True);pump(w)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y-30)],check=True);pump(w)
        subprocess.run(['xdotool','mouseup','1'],check=True);pump(w)
        assert p.split.get_position()<before-20
    saved=p.split.get_position();w.window_layout.close();w.destroy();w=make()
    assert abs(w.recipient_panel.split.get_position()-saved)<=1
finally:
    w.destroy()
'''],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr
