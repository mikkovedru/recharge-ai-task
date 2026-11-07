"""Provider and program scopes remain explicit in displayed and exported logs."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')


def test_provider_activity_and_program_messages_are_attributed_once():
    run_gui(r'''
from recharge_ai_task.activity import ActivityLog
from pathlib import Path
w=make()
try:
    w.clear_log()
    w._message('Global setting saved')
    w._message('Native delivery failed','error',provider='muse')
    history=ActivityLog()
    history.record(replace(b,provider='claude'),'manual','prompt','accepted','Verified by fixture')
    w.poll_activity();pump(w)
    text=w.status.text()
    assert '[Program] Global setting saved' in text
    assert '[Muse] Native delivery failed' in text
    assert '[Claude] Manual' in text and '[Program] [Claude]' not in text
    saved=config_dir()/'provider-export.txt';w.status.save_to(saved)
    assert saved.read_text().strip()==text.strip()
finally:w.destroy()
''')
