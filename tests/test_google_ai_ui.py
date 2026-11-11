"""Google provider pages, persistence and narrow layout in native GTK."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK/X11')


def test_google_tabs_configuration_and_terminal_only_capabilities():
    run_gui(r'''
target_ui.discover_targets=lambda:Inventory([a,b],providers=('codex','gemini','antigravity','opencode'),installed_providers=('codex','gemini','antigravity','opencode'))
w=make()
try:
    assert list(w.monitor_tabs.pages)==['codex','claude','muse','gemini','antigravity','opencode']
    assert list(w.provider_filter.buttons)==['all','codex','claude','muse','gemini','antigravity','opencode']
    for provider in ('gemini','antigravity'):
        page=w.monitor_tabs.pages[provider]
        assert 'recharge-ai-task run --provider '+provider in page.get_text()
        assert 'Shared dashboard quota' in page.get_text()
        assert 'Used: 0' not in page.get_text() and 'Plan: Unavailable' not in page.get_text()
        assert not w.quota_errors.get(provider)
        click(w.provider_filter.buttons[provider],w)
        assert len(w.filtered)==0 and len(w.selected)==2
        assert 'wrapped interactive terminal' in w.provider_filter.buttons[provider].get_tooltip_text()
    dialog=settings_ui.SettingsDialog(w)
    dialog.show_all();pump(w)
    for provider in ('gemini','antigravity'):
        dialog.provider.set_active_id(provider)
        path,args=dialog.google_fields[provider]
        path.set_text('/custom/'+provider)
        args.set_text('--model "selected model"')
    dialog.save_settings()
    stored=AppConfig.load()
    assert stored.provider=='antigravity'
    assert stored.gemini_path=='/custom/gemini' and stored.antigravity_path=='/custom/antigravity'
    assert stored.gemini_args==stored.antigravity_args==['--model','selected model']
    dialog.destroy();pump(w)
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        deadline=time.monotonic()+2
        while (w.get_size().width>1120 or w.get_size().height>820) and time.monotonic()<deadline:pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820,(w.get_size(),w.get_preferred_width(),w.get_preferred_height(),w.recipient_panel.provider_filter.get_preferred_width(),w.provider_filter.get_preferred_width())
        for key,button in w.provider_filter.buttons.items():
            x,y=pos(button,w.provider_filter)
            assert x>=0 and x+button.get_allocated_width()<=w.provider_filter.get_allocated_width(),(key,x,w.provider_filter.get_allocated_width())
        for key,header in w.monitor_tabs.tab_headers.items():
            click(header,w)
            assert w.monitor_tabs.get_current_page()==list(w.monitor_tabs.pages).index(key)+1,key
            x,y=pos(header,w.monitor_tabs)
            assert x>=0 and x+header.get_allocated_width()<=w.monitor_tabs.get_allocated_width(),(key,x,w.monitor_tabs.get_allocated_width())
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-11_google-tabs-'+('dark' if dark else 'light')+'.png')
finally:w.destroy()
''')
