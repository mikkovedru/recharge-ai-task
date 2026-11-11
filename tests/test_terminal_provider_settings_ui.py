"""Mouse and keyboard defaults in the actual settings buttons, including narrow dialogs."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK/X11')


def test_terminal_provider_buttons_explain_scope_and_save_only_on_request():
    run_gui(r'''
from recharge_ai_task.i18n import terminal_start_label
w=make()
try:
    original=AppConfig.load().provider
    dialog=settings_ui.SettingsDialog(w)
    dialog.show_all();pump(dialog)
    assert not isinstance(dialog.provider,Gtk.ComboBox)
    assert list(dialog.provider.buttons)==['codex','claude','muse','gemini','antigravity','opencode']
    assert 'all' not in dialog.provider.buttons
    click(dialog.provider.buttons['gemini'],dialog)
    assert dialog.provider.get_active_id()=='gemini'
    assert terminal_start_label('gemini') in dialog.provider_hint.get_text()
    assert '--provider is omitted' in dialog.provider_hint.get_text()
    assert 'Dashboard discovery and Desktop watch' in dialog.provider_hint.get_text()
    assert AppConfig.load().provider==original
    dialog.provider.buttons['gemini'].grab_focus();pump(dialog)
    subprocess.run(['xdotool','key','End'],check=True);pump(dialog)
    assert dialog.provider.get_active_id()=='opencode'
    subprocess.run(['xdotool','key','Left'],check=True);pump(dialog)
    assert dialog.provider.get_active_id()=='antigravity'
    assert terminal_start_label('antigravity') in dialog.provider_hint.get_text()
    for dark in (False,True):
        dialog.theme.set_active_id('dark' if dark else 'light');pump(dialog)
        dialog.resize(650,450);pump(dialog)
        assert dialog.get_size().width<=650 and dialog.get_size().height<=450,dialog.get_size()
        for provider,button in dialog.provider.buttons.items():
            x,y=pos(button,dialog.provider)
            assert x>=0 and x+button.get_allocated_width()<=dialog.provider.get_allocated_width(),(provider,x,dialog.provider.get_allocated_width())
        assert dialog.scroller.get_vadjustment().get_upper()>dialog.scroller.get_vadjustment().get_page_size()
        dialog.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*dialog.get_size());dialog.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-11_terminal-provider-settings-'+('dark' if dark else 'light')+'.png')
    dialog.save_settings()
    assert AppConfig.load().provider=='antigravity'
    dialog.destroy();pump(w)
    assert w.provider_filter.get_active_id()=='all' and len(w.selected)==2
finally:w.destroy()
''')
