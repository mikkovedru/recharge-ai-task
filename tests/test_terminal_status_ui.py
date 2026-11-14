"""Live terminal observations appear in native provider pages without fake account quota."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK/X11')


def test_live_session_countdown_and_cancellation_in_provider_page():
    run_gui(r'''
from recharge_ai_task.terminal_status import TerminalObservation
observation=TerminalObservation('gemini')
observation.update('waiting',time.time()+120)
w=make()
try:
    w._render_provider_views();pump(w)
    header=w.monitor_tabs.tab_headers['gemini']
    click(header,w)
    page=w.monitor_tabs.pages['gemini']
    assert 'remaining' in page.get_text() and 'not shared account quota' in page.get_text()
    assert '0 continuations sent' in page.get_text()
    assert header.get_sensitive()
    observation.update('cancelled');w._render_provider_views();pump(w)
    assert 'cancelled by typing' in page.get_text() and 'remaining' not in page.get_text()
    observation.close();w._render_provider_views();pump(w)
    assert 'No live wrapped sessions' in page.get_text()
finally:
    observation.close();w.destroy()
''')
