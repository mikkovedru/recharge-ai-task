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
from recharge_ai_task.status_display import status_colors

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
