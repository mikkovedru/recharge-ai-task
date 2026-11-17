"""OpenCode settings persistence and provider controls in native GTK."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_opencode_settings_save_and_small_window():
    run_gui(r'''
target_ui.discover_targets=lambda:Inventory([a,b],providers=('codex','opencode'),installed_providers=('codex','opencode'))
w=make()
try:
    assert 'OpenCode: wrapped terminal' in w.quota_label.get_text()
    assert 'wrapped interactive terminal' in w.monitor_tabs.pages['opencode'].get_text()
    assert 'Plan: Unavailable' not in w.monitor_tabs.pages['opencode'].get_text()
    assert not w.quota_errors.get('opencode')
    dialog=settings_ui.SettingsDialog(w)
    dialog.show_all();pump(w)
    dialog.provider.set_active_id('opencode')
    dialog.opencode_path.set_text('/custom/opencode')
    dialog.opencode_args.set_text('--session "selected chat"')
    dialog.resize(650,450);pump(w)
    assert dialog.scroller.get_vadjustment().get_upper()>dialog.scroller.get_vadjustment().get_page_size()
    assert 'desktop quota' in dialog.opencode_path.get_tooltip_text()
    dialog.save_settings()
    stored=AppConfig.load()
    assert stored.provider=='opencode' and stored.opencode_path=='/custom/opencode'
    assert stored.opencode_args==['--session','selected chat']
    assert list(w.provider_filter.buttons)[-1]=='opencode'
    assert w.provider_filter.buttons['opencode'].get_sensitive()
    assert 'no dashboard targets' in w.provider_filter.buttons['opencode'].get_tooltip_text()
    dialog.destroy();pump(w)
finally:w.destroy()
''')
