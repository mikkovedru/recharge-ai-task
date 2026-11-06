"""Native GTK checks for recipient feedback, compact monitoring and Settings."""
import os
import subprocess
import sys

import pytest


BOOT = r'''
import os,time,subprocess,cairo,gi
from dataclasses import replace
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
from recharge_ai_task import target_ui,autostart,settings_ui,tray_control
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.quota import Quota,RateWindow
from recharge_ai_task.status_display import BORDER_COLORS,status_colors

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'fixture'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(40,300,9999999999),None,False)
a=Target('thread','a','Goal recipient',instance='/fixture',endpoint='/fixture/ipc/ipc.sock',project_name='Work',send_prompt=False,send_goal=True,task_status='Idle',goal_status='Usage limited',custom_prompt='Custom')
b=replace(a,id='b',title='Message recipient',send_prompt=True,send_goal=False,custom_prompt=None)
target_ui.discover_targets=lambda:Inventory([a,b])
runtime=dict(desktop_watch=False,per_target_signals=True,recipient_policies=True,one_use_messages=True,launched_at_startup=True)
commands=[]
def control(command='status',**kw):
    commands.append(command)
    if command=='start-watch':runtime.update(desktop_watch=True,watch_settings=tray_control.watch_settings(AppConfig.load()))
    elif command=='stop-watch':runtime.update(desktop_watch=False,watch_requested=False)
    elif command=='reload' and runtime.get('desktop_watch'):runtime['watch_settings']=tray_control.watch_settings(AppConfig.load())
    return dict(runtime)
target_ui.tray_control.request=control
AppConfig(desktop_targets=[a.to_dict(),b.to_dict()],continue_prompt='Default').save()
def pump(w,delay=.22):
    end=time.monotonic()+delay
    while time.monotonic()<end or any(getattr(w,key,False) for key in ('busy','discovery_busy','runtime_busy','quota_busy','activity_busy')):
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def make():
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    return w
def rgba(hexcode):
    color=Gdk.RGBA();assert color.parse(hexcode);return color
def close_color(actual,expected):
    return max(abs(getattr(actual,k)-getattr(expected,k)) for k in ('red','green','blue'))<.035
def pos(widget,root):return widget.translate_coordinates(root,0,0)
def click(widget,w):
    xid=str(w.get_window().get_xid());x,y=pos(widget,w)
    subprocess.run(['xdotool','mousemove','--window',xid,str(x+widget.get_allocated_width()-10),str(y+widget.get_allocated_height()//2),'click','1'],check=True)
    pump(w)
'''


def run_gui(body):
    result = subprocess.run([sys.executable, '-c', BOOT + body], capture_output=True, text=True, timeout=35)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'CRITICAL' not in result.stderr, result.stderr


pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')


def test_recipient_colors_pause_and_message_information():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    assert p.once.get_label()=='Send only once' and p.once.get_parent() is p.custom_row
    assert [child.get_text() for child in p.save_status_group.get_children() if isinstance(child,Gtk.Label)]==['(',')']
    assert pos(p.once,w)[1]==pos(p.custom,w)[1]
    assert pos(p.default_goal,w)[1]<pos(p.default_prompt,w)[1]
    assert pos(p.goal_limit,w)[1]<pos(p.prompt_limit,w)[1]
    p.list.select_row(p.rows[a.key]);pump(w)
    assert p.save_status.get_icon_name()[0]=='media-playback-pause-symbolic'
    assert 'Off' in p.save_status.get_tooltip_text()
    p.prompt_limit.default.clicked();pump(w)
    assert p.save_status.get_icon_name()[0]=='emblem-ok-symbolic'
    p.default_prompt.limited.clicked();p.default_prompt.number.set_value(0);p.default_prompt.number_popover.popdown();pump(w)
    assert p.save_status.get_icon_name()[0]=='media-playback-pause-symbolic'
    p.default_prompt.unlimited.clicked();pump(w)
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w)
        p.list.select_row(p.rows[a.key]);pump(w)
        colors=status_colors(p)
        assert close_color(p.save_status.get_style_context().get_color(p.save_status.get_state_flags()),rgba(colors['success']))
        for bracket in (p.save_status_open,p.save_status_close):
            assert not any(name.startswith('recipient-save-') for name in bracket.get_style_context().list_classes())
            assert not close_color(bracket.get_style_context().get_color(bracket.get_state_flags()),rgba(colors['success']))
        assert close_color(p.prompt_limit.default.get_style_context().get_background_color(p.prompt_limit.default.get_state_flags()),rgba(colors['success']))
        assert not p.default_prompt.get_style_context().has_class('action-limit')
        assert not close_color(p.default_prompt.unlimited.get_style_context().get_background_color(p.default_prompt.unlimited.get_state_flags()),rgba(colors['success']))
        p.prompt_limit.off.clicked();pump(w)
        assert close_color(p.prompt_limit.off.get_style_context().get_background_color(p.prompt_limit.off.get_state_flags()),rgba(colors['error'])),(dark,p.prompt_limit.off.get_style_context().get_background_color(p.prompt_limit.off.get_state_flags()).to_string(),colors['error'],p.prompt_limit.off.get_state_flags())
        assert close_color(p.save_status.get_style_context().get_color(p.save_status.get_state_flags()),rgba(colors['error']))
        p.prompt_limit.default.clicked();pump(w)
        runtime["restarting"]=True;w.runtime=dict(runtime);w._summary();pump(w)
        assert close_color(p.save_status.get_style_context().get_color(p.save_status.get_state_flags()),rgba(colors['warning']))
        runtime.pop("restarting");w.runtime=dict(runtime);w._summary();pump(w)
        for key in (a.key,b.key):
            p.list.select_row(p.rows[key]);p.rows[key].indicator.grab_focus();pump(w)
            row=p.rows[key];assert row.indicator.get_visible()
            fg=row.indicator.get_image().get_style_context().get_color(row.indicator.get_image().get_state_flags())
            bg=row.indicator.get_style_context().get_background_color(row.indicator.get_state_flags())
            def luminance(c):
                return sum(weight*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for weight,v in zip((.2126,.7152,.0722),(c.red,c.green,c.blue)))
            lo,hi=sorted((luminance(fg),luminance(bg)))
            assert (hi+.05)/(lo+.05)>4.5,(dark,fg.to_string(),bg.to_string())
    row=p.rows[b.key]
    assert not row.plan.get_visible() and 'Message' in row.indicator.get_tooltip_text()
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        click(row.indicator,w)
        assert row.details.get_visible() and 'Message ready' in row.explanation.get_text()
        row.details.popdown();pump(w)
    w.resize(1120,820);pump(w)
    assert w.get_size().width<=1120 and w.get_size().height<=820
    assert pos(p.once,p.custom_row)[0]+p.once.get_allocated_width()<=p.custom_row.get_allocated_width()
finally:w.destroy()
''')


def test_monitoring_header_border_alignment_and_settings():
    run_gui(r'''
w=make()
try:
    assert not hasattr(w,'startup_label') and not hasattr(w,'startup_toggle')
    assert w.watch_label.get_parent() is w.monitoring_heading.get_parent()
    assert w.monitoring_card.get_allocated_height()<110
    assert w.monitoring_card.get_allocated_height()<=w.watch_button.get_allocated_height()+w.monitoring_heading.get_allocated_height()+32
    assert pos(w.watch_label,w)[0]>pos(w.monitoring_heading,w)[0]
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w)
        for flags,status,level in ((dict(desktop_watch=False),'Off','error'),
                                   (dict(desktop_watch=True,watch_settings=tray_control.watch_settings(AppConfig.load())),'On','success'),
                                   (dict(desktop_watch=True,restarting=True),'Reloading','warning'),
                                   (dict(desktop_watch=True,watch_error='Failed to restart'),'Error','error')):
            runtime.clear();runtime.update(flags,per_target_signals=True,recipient_policies=True,one_use_messages=True,launched_at_startup=True)
            w.runtime=dict(runtime);w._render_runtime();pump(w)
            assert w.watch_label.get_text()==status,(status,w.watch_label.get_text())
            # Check actual rendered frame pixels, including its far lower edge.
            w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface));surface.flush()
            expected=rgba(BORDER_COLORS[level]);x,y=pos(w.monitoring_card,w)
            for px,py in ((x,y+w.monitoring_card.get_allocated_height()//2),(x+w.monitoring_card.get_allocated_width()//2,y+w.monitoring_card.get_allocated_height()-1)):
                offset=py*surface.get_stride()+px*4
                blue,green,red,alpha=bytes(surface.get_data()[offset:offset+4])
                actual=Gdk.RGBA(red/255,green/255,blue/255,alpha/255)
                assert close_color(actual,expected),(status,dark,actual.to_string(),expected.to_string())
        runtime.pop("watch_error",None)
        runtime.update(desktop_watch=True,watch_settings=tray_control.watch_settings(AppConfig.load()),watch_progress=dict(phase='monitoring',updated_at=time.time(),next_check_at=time.time()+30,selected_recipients=2,selected_messages=1,selected_goals=1,expected_reset_at=time.time()+500))
        w.runtime=dict(runtime);w._render_runtime();pump(w)
        assert w.send_time_label.get_text().startswith('Next reset forecast:')
        assert pos(w.quota_heading,w)[1]==pos(w.send_time_label,w)[1]
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_monitoring-'+('dark' if dark else 'light')+'.png')
    dialog=settings_ui.SettingsDialog(w);pump(w)
    try:
        assert len(dialog.notes.get_children())==4
        assert all(row.get_children()[0].get_text()=='•' for row in dialog.notes.get_children())
        assert not dialog.autostart.get_active()
        assert dialog.startup_info.get_text()=='(This tray started at login: Yes)'
        assert dialog.startup_info.get_parent() is dialog.autostart.get_parent()
        dialog.grace.set_value(37);dialog.poll.set_value(9)
        if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
            click(dialog.grace,dialog);click(dialog.poll,dialog)
        else:
            dialog.grace.spin(Gtk.SpinType.STEP_FORWARD,1);dialog.poll.spin(Gtk.SpinType.STEP_FORWARD,1)
        assert dialog.grace.get_value_as_int()==47 and dialog.poll.get_value_as_int()==14
        dialog.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*dialog.get_size());dialog.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_monitoring-settings.png')
        dialog.autostart.set_active(True)
        original=AppConfig.save;AppConfig.save=lambda *_:(_ for _ in ()).throw(OSError('disk full'))
        try:dialog.save_settings()
        except OSError:pass
        else:raise AssertionError('save unexpectedly passed')
        AppConfig.save=original
        assert not autostart.is_autostart_enabled() and not dialog.autostart.get_active()
        dialog.autostart.set_active(True);dialog.save_settings()
        assert autostart.is_autostart_enabled()
    finally:dialog.destroy()
    w.runtime=None
    dialog=settings_ui.SettingsDialog(w)
    assert 'Unknown' in dialog.startup_info.get_text()
    dialog.destroy()
    w.resize(1120,820);pump(w)
    assert w.get_size().width<=1120 and w.get_size().height<=820
    assert pos(w.quota_heading,w)[1]==pos(w.send_time_label,w)[1]
finally:w.destroy()
''')


def test_first_added_recipient_starts_watch_without_toggling_existing_watch():
    run_gui(r'''
AppConfig(continue_prompt='Default').save()
w=make()
def toggle(identity,action):
    path=next(row.path for row in w.filtered if row[4]==identity)
    w._toggle(None,path,action);pump(w)
try:
    assert not w.selected and commands.count('start-watch')==0
    toggle('a','send_goal')
    assert commands.count('start-watch')==1 and runtime['desktop_watch']
    assert AppConfig.load().targets()[0].send_goal
    toggle('b','send_prompt')
    w.update_recipient(replace(w.selected[b.key],custom_prompt='Edit'));pump(w)
    assert commands.count('start-watch')==1 and 'stop-watch' not in commands
    w.toggle_watch();pump(w)
    assert not runtime['desktop_watch']
    w.update_recipient(replace(w.selected[b.key],custom_prompt='Another edit'));pump(w)
    assert commands.count('start-watch')==1
    toggle('a','send_goal');toggle('b','send_prompt')
    assert not w.selected
    # Do not start until the first selection has actually been saved.
    original=AppConfig.save;AppConfig.save=lambda *_:(_ for _ in ()).throw(OSError('disk full'))
    path=next(row.path for row in w.filtered if row[4]=='b')
    w._toggle(None,path,'send_prompt')
    assert commands.count('start-watch')==1 and w.autosave_error
    AppConfig.save=original
    w.save();pump(w)
    assert commands.count('start-watch')==2 and runtime['desktop_watch']
    # Loading the saved recipient or changing it never starts or stops monitoring.
    w.destroy();runtime['desktop_watch']=False;w=make()
    assert w.selected and commands.count('start-watch')==2
    w.update_recipient(replace(w.selected[b.key],custom_prompt='Loaded edit'));pump(w)
    assert commands.count('start-watch')==2
    w.update_recipient(replace(w.selected[b.key],custom_prompt=None));pump(w)
    toggle('b','send_prompt')
    w.signal_buffer.set_text('');pump(w)
    toggle('b','send_prompt')
    assert commands.count('start-watch')==2 and 'Enter a message' in w.status.latest_text
finally:w.destroy()
''')


def test_color_theme_preview_cancel_persistence_and_system_default():
    run_gui(r'''
from recharge_ai_task.theme_ui import apply_color_theme
settings=Gtk.Settings.get_default()
apply_color_theme('auto')
os_values=(settings.get_property('gtk-theme-name'),settings.get_property('gtk-application-prefer-dark-theme'))
w=make()
try:
    dialog=settings_ui.SettingsDialog(w);pump(w)
    assert [row[0] for row in dialog.theme.get_model()]==['Dark','Light','Auto (OS)']
    assert dialog.theme.get_active_id()=='auto'
    dialog.theme.set_active_id('light');pump(w)
    assert settings.get_property('gtk-theme-name')=='Adwaita'
    assert not settings.get_property('gtk-application-prefer-dark-theme')
    assert status_colors(w.monitoring_card)['success']=='#137333'
    dialog.theme.set_active_id('dark');pump(w)
    assert settings.get_property('gtk-application-prefer-dark-theme')
    assert status_colors(w.monitoring_card)['success']=='#73d99b'
    assert w.monitoring_palette[0]=='#73d99b' and w.recipient_panel.status_palette[0]=='#73d99b'
    dialog.save_settings();dialog.destroy()
    assert AppConfig.load().color_theme=='dark'
    w.destroy();w=make()
    assert settings.get_property('gtk-application-prefer-dark-theme')
    dialog=settings_ui.SettingsDialog(w);pump(w)
    assert dialog.theme.get_active_id()=='dark'
    dialog.theme.set_active_id('light');pump(w)
    assert not settings.get_property('gtk-application-prefer-dark-theme')
    # Closing without saving rolls back the live preview.
    dialog.destroy();pump(w)
    assert AppConfig.load().color_theme=='dark' and settings.get_property('gtk-application-prefer-dark-theme')
    dialog=settings_ui.SettingsDialog(w);pump(w)
    dialog.theme.set_active_id('auto');pump(w)
    assert (settings.get_property('gtk-theme-name'),settings.get_property('gtk-application-prefer-dark-theme'))==os_values
    dialog.save_settings();dialog.destroy()
    assert AppConfig.load().color_theme=='auto'
    w.destroy();w=make()
    assert (settings.get_property('gtk-theme-name'),settings.get_property('gtk-application-prefer-dark-theme'))==os_values
finally:w.destroy()
''')
