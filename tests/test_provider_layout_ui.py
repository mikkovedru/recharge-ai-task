"""Provider overview list, passive markers and full-width compact details."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_overview_names_passive_states_and_compact_provider_details():
    run_gui(r'''
from recharge_ai_task.config import PROVIDERS,PROVIDER_LABELS
c=replace(b,id='c',provider='claude')
target_ui.discover_targets=lambda:Inventory([a,b,c],providers=('codex','claude'),installed_providers=('codex','claude'),
    provider_details={'codex':'Executable: /fixture/codex\nCodex 9.8.7'})
target_ui.fetch_claude_quota=lambda:(_ for _ in ()).throw(RuntimeError('Fixture login required'))
w=make()
try:
    markup=w.quota_label.get_label()
    for provider in PROVIDERS:
        assert '• <b>'+PROVIDER_LABELS[provider]+'</b>' in markup
    assert len([line for line in w.quota_label.get_text().splitlines() if line.startswith('• ')])==len(PROVIDERS)
    codex=w.monitor_tabs.pages['codex'].get_text().splitlines()
    assert all(part in codex[0] for part in ('Codex','Plan: test','/fixture/codex','9.8.7')),codex
    claude=w.monitor_tabs.pages['claude'].get_text().splitlines()
    assert 'Quota unavailable' in claude[1] and 'No successful quota observation yet' in claude[1],claude
    assert 'Fixture login required' in '\n'.join(claude)
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for width in (1440,1120):
            w.resize(width,820);pump(w)
            assert w.get_size().width<=width and w.get_size().height<=820
            passive=w.monitor_tabs.tab_headers['muse']
            assert passive.get_style_context().has_class('provider-tab-passive')
            assert not w.monitor_tabs.tab_headers['claude'].get_style_context().has_class('provider-tab-passive')
            assert w.monitor_tabs.tab_labels['muse'].get_text().endswith(' —')
            assert 'not installed' in w.monitor_tabs.tab_labels['muse'].get_accessible().get_name()
            click(w.monitor_tabs.tab_labels['muse'],w)
            assert w.monitor_tabs.get_current_page()==3
            assert w.monitor_tabs.pages['muse'].get_sensitive()
            assert 'Provider not detected' in w.monitor_tabs.pages['muse'].get_text()
            click(w.monitor_tabs.tab_labels['codex'],w)
            page=w.monitor_tabs.pages['codex']
            assert page.get_allocated_width()>=w.monitor_tabs.get_allocated_width()-40
            assert page.get_layout().get_pixel_size()[0]<=page.get_allocated_width()
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-14_provider-layout-'+('dark' if dark else 'light')+'.png')
    w._apply_inventory(Inventory([a,b,c],providers=('codex','claude','muse'),installed_providers=('codex','claude','muse')));pump(w)
    assert w.monitor_tabs.tab_labels['muse'].get_text()=='Muse'
    assert not w.monitor_tabs.tab_headers['muse'].get_style_context().has_class('provider-tab-passive')
    # All still contains the full provider list on a machine without installations.
    w._apply_inventory(Inventory([],providers=(),installed_providers=()));pump(w)
    assert w.quota_label.get_text().count('• ')==len(PROVIDERS)
finally:w.destroy()
''')
