"""Read automatic delivery history and worker changes through real GTK widgets."""
import os
import subprocess
import sys
import pytest


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')
def test_live_schedule_and_delivery_history_survive_worker_loss_and_reopening():
    result = subprocess.run([sys.executable,'-c',r'''
import time
from types import SimpleNamespace
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.activity import ActivityLog
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.quota import Quota,RateWindow
from gi.repository import Gtk

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'offline'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(0,300,500),None,False)
target=Target('thread','sample','Sample chat',send_prompt=True,send_goal=True)
target_ui.discover_targets=lambda:Inventory([target])
progress=dict(phase='grace_period',updated_at=100,next_check_at=115,recovery_at=160,
    grace_seconds=120,pending_cycle=True,pending_recipients=1,pending_messages=1,pending_goals=1)
runtime=dict(desktop_watch=True,watch_progress_version=2,delivery_history=True,watch_progress=progress)
clock=[100]
target_ui.time=SimpleNamespace(**{name:getattr(time,name) for name in dir(time) if not name.startswith("_")})
target_ui.time.time=lambda:clock[0]
reachable=[True]
def status(*args,**kwargs):
    if not reachable[0]:raise ConnectionRefusedError('offline')
    return dict(runtime)
target_ui.tray_control.request=status
AppConfig(desktop_targets=[target.to_dict()]).save()
def pump(w):
    until=time.monotonic()+.2
    while time.monotonic()<until or w.discovery_busy or w.quota_busy or w.runtime_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def make():
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    return w
w=make()
assert '00:01:00' in w.send_countdown_label.get_text()
clock[0]=110;w.render_quota()
assert '00:00:50' in w.send_countdown_label.get_text()
progress['recovery_at']=125
w.poll_runtime();pump(w)
assert '00:00:15' in w.send_countdown_label.get_text()
history=ActivityLog()
history.record(target,'automatic','goal','attempting')
history.record(target,'automatic','goal','verified','Native Goal activation verified')
history.record(target,'automatic','prompt','attempting',message='Specific\nmessage')
history.record(target,'automatic','prompt','failed','Backend rejected it',message='Specific\nmessage')
w.poll_runtime();pump(w)
text=w.status.buffer.get_text(*w.status.buffer.get_bounds(),True)
assert 'Automatic · Sample chat [Project: not available] · Goal: attempting' in text
assert 'Goal: verified' in text and 'Message: failed — Backend rejected it' in text
assert 'Message text: Specific\nmessage' in text
cursor=w.activity_cursor
w.poll_runtime();pump(w)
assert w.activity_cursor==cursor
assert w.status.buffer.get_text(*w.status.buffer.get_bounds(),True)==text
reachable[0]=False
history.record(target,'manual','goal','skipped','Goal already active')
w.poll_runtime();pump(w)
assert w.send_time_label.get_text()=='No send scheduled'
assert 'Manual · Sample chat [Project: not available] · Goal: skipped' in w.status.buffer.get_text(*w.status.buffer.get_bounds(),True)
w.destroy()
w=make()
assert w.activity_cursor>cursor
assert 'Message: failed' in w.status.buffer.get_text(*w.status.buffer.get_bounds(),True)
w.destroy()
'''],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr
