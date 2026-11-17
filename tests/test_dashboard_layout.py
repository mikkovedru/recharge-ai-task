"""Editor allocation and persistence regression for the dashboard editors."""
import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS")!="1", reason="Requires GTK")
def test_editor_drag_wrapping_and_log_layout():
    result=subprocess.run([sys.executable,"-c",r'''
import time,os,subprocess
from types import SimpleNamespace
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.quota import Quota,RateWindow
from gi.repository import Gtk,Gdk

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'offline'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(98,300,int(time.time())+1800),None,False)
target_ui.discover_targets=lambda:Inventory([Target('thread',str(i),'Synthetic chat '+str(i),task_status='Error',goal_status='Usage limited') for i in range(8)])
target_ui.tray_control.request=lambda *a,**kw:{'desktop_watch':False,'delivery_history':True,'watch_progress_version':2}
AppConfig().save()
def pump(w):
    until=time.monotonic()+.2
    while time.monotonic()<until or w.quota_busy or w.runtime_busy or w.discovery_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.003)
w=target_ui.TargetPicker(quit_on_close=False)
w.set_accept_focus(False);w.set_focus_on_map(False);w.set_keep_above(True);w.show_all();pump(w)
w.main_split.set_position(330);pump(w)
# Single-line captions reserve native button height, rather than three lines.
for button in (w.copy_button,w.open_button):
    assert button.get_allocated_height() <= w.refresh_button.get_allocated_height()+2
assert w.list_toolbar.get_allocated_height() <= w.refresh_button.get_allocated_height()+2
editor=w.default_editor
def drag(delta):
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        x,y=editor.handle.translate_coordinates(w,9,9)
        xid=str(w.get_window().get_xid())
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y)],check=True)
        pump(w)
        subprocess.run(['xdotool','mousedown','1'],check=True)
        pump(w)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y+delta)],check=True)
        pump(w)
        subprocess.run(['xdotool','mouseup','1'],check=True)
        print('Actual pointer drag:',delta,flush=True)
    else:
        editor._press(editor.handle,SimpleNamespace(button=1,x_root=0,y_root=0))
        editor._motion(editor.handle,SimpleNamespace(x_root=0,y_root=delta))
        editor._release(editor.handle,SimpleNamespace(button=1))
    pump(w)
try:
    print('Initial window',w.get_size(),w.get_position(),flush=True)
    before=editor.get_allocated_height();log_before=w.status.get_allocated_height()
    drag(100)
    after=editor.get_allocated_height()
    print('Editor vertical growth:',before,after,'request',editor.editor_size(),flush=True)
    assert after>=before+90
    drag(-50)
    smaller=editor.get_allocated_height()
    print('Editor vertical shrink:',after,smaller,'log',w.status.get_allocated_height(),flush=True)
    assert smaller<=after-40
    assert not hasattr(w,'message_split')
    p=w.recipient_panel
    assert not hasattr(p,'status_rules')
    def pos(widget):return widget.translate_coordinates(w,0,0)
    for width in (1400,1120):
        w.resize(width,820);pump(w)
        assert pos(p.default_controls)[0] >= pos(editor)[0]+editor.get_allocated_width()
        assert pos(w.send_button)[0] < pos(p.reset_all)[0]
        assert [child.get_child() for child in p.actions.get_children()] == [w.send_button,p.reset_all,p.reset]
        for button in (w.send_button,p.reset_all,p.reset):
            x,y=button.translate_coordinates(p.editor_scroller,0,0)
            assert x>=0 and x+button.get_allocated_width()<=p.editor_scroller.get_allocated_width()
    p.default_prompt.limited.clicked();pump(w)
    assert p.default_prompt.limited.get_active() and not p.default_prompt.unlimited.get_active()
    p.default_prompt.number.set_value(4)
    assert AppConfig.load().prompt_limit==4 and p.default_prompt.limited.get_label()=='4'
    p.default_prompt.number_popover.popdown()
    p.default_prompt.unlimited.clicked();pump(w)
    assert p.default_prompt.unlimited.get_active() and not p.default_prompt.limited.get_active()
    assert AppConfig.load().prompt_limit is None
    # A target count label wraps inside its action column.
    w.update_recipient(Target('thread','0','Synthetic chat 0',send_prompt=True,send_goal=False));pump(w)
    assert target_ui.WrappingButton._label(w.send_button).get_layout().get_line_count()>1
    for key in w.table_layout.columns:
        for descending in (False,True):
            w.table_layout.sort(key,descending)
            assert [bool(row[0] or row[12]) for row in w.filtered]==[True]+[False]*7,(key,descending)
    pump(w)
    send_y=w.send_row.translate_coordinates(w.message_area,0,0)[1]
    log_y=w.status.translate_coordinates(w.message_area,0,0)[1]
    assert w.compose_group.get_children()[-1] is w.send_row
    assert w.log_area.get_children()[-1] is w.status
    assert log_y>send_y+w.send_row.get_allocated_height()
    assert log_y+w.status.get_allocated_height()==w.message_area.get_allocated_height()
    saved=editor.editor_size()
    w.window_layout.close();w.destroy()
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    assert w.default_editor.editor_size()==saved
    w.resize(1120,820);pump(w)
    w.workspace_split.set_position(350);pump(w)
    def label(widget):
        if isinstance(widget,Gtk.Label):return widget
        if isinstance(widget,Gtk.Container):
            for child in widget.get_children():
                found=label(child)
                if found:return found
    for button in (w.copy_button,w.open_button):
        text=label(button)
        print('Button wrap',text.get_text(),text.get_layout().get_line_count(),button.get_allocated_width(),flush=True)
        assert text.get_line_wrap()
    for caption in ('Copy link / ID','Open selected row'):
        sample=target_ui.WrappingButton(label=caption)
        sample.set_valign(Gtk.Align.CENTER)
        sample.set_image(Gtk.Image.new_from_icon_name('go-jump-symbolic',Gtk.IconSize.BUTTON))
        sample.set_always_show_image(True)
        target_ui.TargetPicker._wrap_button_label(sample)
        probe=Gtk.Window();probe.set_accept_focus(False);probe.set_focus_on_map(False);probe.set_default_size(75,75);probe.add(sample);probe.show_all();pump(w)
        assert label(sample).get_layout().get_line_count()>1,caption
        print('Constrained button wraps:',caption,label(sample).get_layout().get_line_count(),flush=True)
        narrow_height=sample.get_allocated_height()
        probe.resize(220,75);pump(w)
        assert sample.get_allocated_height()<narrow_height
        assert sample.get_allocated_height()<=w.refresh_button.get_allocated_height()+2
        probe.destroy()
    assert w.get_size().height<=820
    bounds=w.table.get_background_area(Gtk.TreePath.new_from_string('1'),w.title_column)
    x,y=w.table.convert_bin_window_to_widget_coords(8,bounds.y)
    strip=Gdk.pixbuf_get_from_window(w.table.get_window(),x,y,1,7)
    pixels=strip.get_pixels();stride=strip.get_rowstride()
    assert sum(abs(pixels[i]-pixels[5*stride+i]) for i in range(3))>100,'Missing selected-target divider'
    assert w.table.get_parent().get_allocated_height()>=59
    assert w.search.translate_coordinates(w.list_area,0,0)[1]>=0
    image=Gdk.pixbuf_get_from_window(w.get_window(),0,0,*w.get_size())
    image.savev('/tmp/2026-11-05_recharge-dashboard-layout.png','png',[],[])
finally:
    w.destroy()
'''],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert "CRITICAL" not in result.stderr,result.stderr
