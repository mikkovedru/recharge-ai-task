"""Compact recipient editor, two-way focus, issue-only previews and save feedback."""
import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')
def test_compact_editor_selection_off_modes_and_save_feedback():
    result=subprocess.run([sys.executable,'-c',r'''
import os,subprocess,time,gi,cairo
from dataclasses import replace
from types import SimpleNamespace
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from recharge_ai_task import target_ui,autostart,tray_control,target_delivery
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.quota import Quota,RateWindow

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'fixture'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(40,300,9999999999),None,False)
a=Target('thread','a','Same title',instance='/fixture',endpoint='/fixture/ipc/ipc.sock',project_name='Work',send_prompt=True,send_goal=False,task_status='Idle',goal_status='Usage limited')
b=replace(a,id='b',custom_prompt='B draft')
c=replace(a,id='c',title='Not a recipient',send_prompt=False)
target_ui.discover_targets=lambda:Inventory([a,b,c])
runtime={'desktop_watch':False,'one_use_messages':True,'recipient_policies':True,'per_target_signals':True}
def control(*args,**kw):return dict(runtime)
target_ui.tray_control.request=control
AppConfig(desktop_targets=[a.to_dict(),b.to_dict()],continue_prompt='Default').save()
def pump(w,delay=.3):
    end=time.monotonic()+delay
    while time.monotonic()<end or w.discovery_busy or w.runtime_busy or w.quota_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def select(identity):
    path=next(row.path for row in w.filtered if row[4]==identity)
    w.table.set_cursor(path,w.title_column);pump(w)
w=target_ui.TargetPicker(quit_on_close=False)
w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
p=w.recipient_panel
try:
    assert not hasattr(w,'recipient_label') and not hasattr(p,'editor_title')
    assert not hasattr(p,'prompt') and not hasattr(p,'goal')
    assert w.default_editor.get_allocated_height()<90
    assert w._keyboard(w,SimpleNamespace(keyval=Gdk.KEY_F1,state=0)) is False
    w.table_layout.sort('id')
    select('b')
    assert p.selected_key==b.key and p.list.get_selected_row() is p.rows[b.key]
    assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)=='B draft'
    select('a');assert p.selected_key==a.key
    p.list.select_row(p.rows[b.key]);pump(w)
    assert w._row_target().id=='b'
    select('c')
    assert p.list.get_selected_row() is None and not p.custom.is_sensitive()
    select('a')
    assert not p.rows[a.key].plan.get_visible() and p.rows[a.key].indicator.get_visible()
    assert p.rows[a.key].title.get_text()=='Work · Same title'
    assert not p.rows[a.key].title.get_line_wrap()
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        pump(w)
        context=p.rows[a.key].get_style_context()
        selected=context.get_background_color(context.get_state())
        p.list.select_row(p.rows[b.key]);pump(w)
        normal=context.get_background_color(context.get_state())
        p.list.select_row(p.rows[a.key]);pump(w)
        assert sum(abs(getattr(selected,c)-getattr(normal,c)) for c in ('red','green','blue','alpha'))>.12,(dark,selected.to_string(),normal.to_string())
    assert p.prompt_limit.default.get_label()=='Global default (∞)'
    p.default_prompt.limited.clicked();p.default_prompt.number_popover.popdown();p.default_prompt.number.set_value(3);pump(w)
    assert p.prompt_limit.default.get_label()=='Global default (3)'
    p.goal_limit.limited.clicked();p.goal_limit.number_popover.popdown();p.goal_limit.number.set_value(2);pump(w)
    assert w.selected[a.key].send_goal and w.selected[a.key].goal_limit==2
    p.prompt_limit.off.clicked();pump(w)
    assert not w.selected[a.key].send_prompt and w.selected[a.key].send_goal
    assert not p.rows[a.key].preview.get_visible()
    assert 'No message selected' not in p.rows[a.key].preview.get_text()
    p.prompt_limit.default.clicked();p.goal_limit.off.clicked();pump(w)
    assert w.selected[a.key].send_prompt and not w.selected[a.key].send_goal
    p.custom.set_active(True);p.message_buffer.set_text('Only once');p.once.set_active(True);pump(w)
    token=w.selected[a.key].custom_prompt_once
    assert token and AppConfig.load().targets()[0].custom_prompt_once==token
    assert 'Saved' in p.save_status.get_tooltip_text()
    runtime.update(desktop_watch=True,watch_settings={},restarting=True)
    w.runtime=dict(runtime);w._summary()
    assert 'waiting' in p.save_status.get_tooltip_text()
    runtime.update(restarting=False,watch_settings=tray_control.watch_settings(AppConfig.load()))
    w.runtime=dict(runtime);w._summary()
    assert 'applied' in p.save_status.get_tooltip_text()
    runtime.update(restarting=True);w.runtime=dict(runtime);w._render_runtime()
    runtime.update(restarting=False);w.runtime=dict(runtime);w._render_runtime()
    log=lambda:w.status.buffer.get_text(*w.status.buffer.get_bounds(),True)
    assert 'Desktop watch is running with saved settings.' not in log()
    assert 'Applying saved settings; Desktop watch will restart automatically.' not in log()
    original=AppConfig.save
    AppConfig.save=lambda *_:(_ for _ in ()).throw(OSError('disk full'))
    p.message_buffer.set_text('Newer draft');pump(w,.1)
    assert 'Could not save' in p.save_status.get_tooltip_text() and 'disk full' in log()
    AppConfig.save=original
    runtime.update(desktop_watch=False,restarting=False)
    w.save();pump(w)
    assert 'Saved' in p.save_status.get_tooltip_text()
    assert w.selected[a.key].custom_prompt_once!=token
    # Older apply failures cannot turn a saved custom draft green accidentally.
    w.apply_error='reload failed';w._summary()
    assert 'could not be applied' in p.save_status.get_tooltip_text()
    w.apply_error=''
    # A late acknowledgement cannot hide failure of the latest apply attempt.
    callbacks=[];original_background=w._background;original_poll=w.poll_runtime
    w._background=lambda job,done:callbacks.append(done)
    w.poll_runtime=lambda:True
    w.save();older=callbacks[-1]
    w.save();newer=callbacks[-1]
    newer(None,'latest reload failed')
    older(dict(runtime),None)
    assert w.apply_error=='latest reload failed'
    assert 'latest reload failed' in p.save_status.get_tooltip_text() and 'Could not apply saved settings' in log()
    w._background=original_background;w.poll_runtime=original_poll
    w.save();pump(w)
    assert 'Saved' in p.save_status.get_tooltip_text()
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        pump(w)
        w.check_resize()
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size())
        w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_compact-'+('dark' if dark else 'light')+'.png')
    # Delivery acknowledgement clears the one-use override and the checkbox.
    sent=[];target_delivery._send_thread=lambda t,text:sent.append(text)
    notices_before=log().count('Changes differ from saved settings')
    assert target_delivery.send_signals([w.selected[a.key]],w._prompt_text(),manual=True)[0].success
    w._summary();pump(w)
    assert log().count('Changes differ from saved settings')==notices_before
    assert sent==['Newer draft'] and not p.custom.get_active() and not p.once.get_active()
    assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)=='Default'
    # A newer saved draft wins when an older one-use token completes.
    from recharge_ai_task.delivery_policy import UsageLedger
    pending=replace(w.selected[a.key],custom_prompt='Older',custom_prompt_once='older-token')
    w.update_recipient(pending)
    ledger=UsageLedger();attempt,_=ledger.reserve_prompt(pending,None,'Older','Default');ledger.finish(attempt,'sent')
    newer=replace(pending,custom_prompt='Concurrent draft',custom_prompt_once='newer-token')
    saved=AppConfig.load();saved.desktop_targets=[newer.to_dict() if t.id=='a' else t.to_dict() for t in saved.all_targets()];saved.save()
    w._summary();pump(w)
    assert w.selected[a.key].custom_prompt=='Concurrent draft'
    assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)=='Concurrent draft'
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        select('b');w.set_accept_focus(True)
        xid=str(w.get_window().get_xid())
        subprocess.run(['xdotool','windowactivate','--sync',xid],check=True)
        path=next(row.path for row in w.filtered if row[4]=='b')
        area=w.table.get_background_area(path,w.table_layout.columns['provider'][0])
        x,y=w.table.convert_bin_window_to_widget_coords(area.x+12,area.y+area.height//2)
        x,y=w.table.translate_coordinates(w,x,y)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y),'click','1'],check=True);pump(w)
        assert w._row_target().id=='b' and p.selected_key==b.key
        subprocess.run(['xdotool','key','Up'],check=True);pump(w)
        assert w._row_target().id=='a' and p.selected_key==a.key and w.table.has_focus(),(w._row_target().id,p.selected_key,type(w.get_focus()).__name__,w.table.has_focus())
    w.resize(1120,820);pump(w)
    assert w.get_size().width<=1120 and w.get_size().height<=820
finally:
    w.destroy()
'''],capture_output=True,text=True,timeout=40)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr
