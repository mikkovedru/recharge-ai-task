"""One configured quota interval and a worker-backed dashboard snapshot."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')


def test_configured_quota_timer_and_worker_snapshot_use_same_schedule():
    run_gui(r'''
from dataclasses import asdict
calls=[]
def fetch(_):
    calls.append(time.monotonic())
    return Quota('standalone',RateWindow(21,300,9999999999),None,False)
target_ui.fetch_quota=fetch
config=AppConfig.load();config.poll_seconds=1;config.save()
w=make()
try:
    pump(w,1.2)
    assert len(calls)>=2 and 'automatic refresh every 1s' in w.quota_label.get_text()
    original_timer=w.quota_timer
    config=AppConfig.load();config.poll_seconds=2;config.save()
    w.poll_runtime();pump(w)
    assert w.quota_interval==2 and w.quota_timer!=original_timer
    before=len(calls);pump(w,1.1);assert len(calls)==before
    pump(w,1.1);assert len(calls)==before+1
    observed=Quota('worker',RateWindow(73,300,9999999999),RateWindow(18,10080,9999999999),False)
    progress=dict(phase='monitoring',checked_at=time.time(),updated_at=time.time(),next_check_at=time.time()+2,poll_seconds=2,quota_snapshot=asdict(observed),selected_recipients=2,selected_messages=1,selected_goals=1,expected_reset_at=time.time()+100)
    runtime.update(desktop_watch=True,shared_quota=True,manual_quota_check=True,watch_progress=progress,watch_settings=tray_control.watch_settings(AppConfig.load()))
    w.runtime=dict(runtime);before=len(calls)
    w.poll_runtime();pump(w)
    assert w.quota==observed and '73% used' in w.quota_label.get_text()
    assert 'automatic refresh every 2s' in w.quota_label.get_text()
    w._periodic_quota_refresh();pump(w)
    w.quota_button.clicked();pump(w)
    assert 'check-quota' in commands and len(calls)==before
    config=AppConfig.load();config.poll_seconds=5;config.save()
    progress.update(poll_seconds=5,checked_at=time.time(),updated_at=time.time(),next_check_at=time.time()+5)
    runtime['watch_settings']=tray_control.watch_settings(config)
    w.poll_runtime();pump(w)
    assert w.quota_interval==5 and 'automatic refresh every 5s' in w.quota_label.get_text()
    assert w.next_check_label.get_text()=='In 00:05'
    progress.update(phase='quota_unavailable',quota_error='offline')
    w.poll_runtime();pump(w)
    assert w.quota==observed and 'Latest refresh failed' in w.quota_label.get_text()
    assert 'offline' in w.status.text() and len(calls)==before
finally:w.destroy()
''')
