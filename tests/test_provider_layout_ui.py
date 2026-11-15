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
    claude=w.monitor_tabs.pages['claude'].quota.get_text().splitlines()
    assert 'Quota unavailable' in claude[0] and 'No successful quota observation yet' in claude[0],claude
    assert 'Fixture login required' in w.monitor_tabs.pages['claude'].alerts.get_text()
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for width in (1440,1120):
            w.resize(width,820);pump(w)
            assert w.get_size().width<=width and w.get_size().height<=820
            passive=w.monitor_tabs.tab_headers['muse']
            assert passive.get_style_context().has_class('provider-tab-passive')
            assert not w.monitor_tabs.tab_headers['claude'].get_style_context().has_class('provider-tab-passive')
            for provider, label in w.monitor_tabs.tab_labels.items():
                from recharge_ai_task.provider_monitor_ui import NAMES
                assert label.get_text() == NAMES[provider]
            assert 'not installed' in w.monitor_tabs.tab_labels['muse'].get_accessible().get_name()
            click(w.monitor_tabs.tab_labels['muse'],w)
            assert w.monitor_tabs.get_current_page()==3
            assert w.monitor_tabs.pages['muse'].get_sensitive()
            assert 'Provider not detected' in w.monitor_tabs.pages['muse'].get_text()
            click(w.monitor_tabs.tab_labels['codex'],w)
            page=w.monitor_tabs.pages['codex']
            assert page.get_allocated_width()>=w.monitor_tabs.get_allocated_width()-40
            assert page.identity.get_layout().get_pixel_size()[0]<=page.identity.get_allocated_width()
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


def test_initial_metadata_survives_chat_refresh_and_reports_missing_versions():
    run_gui(r'''
import threading
from recharge_ai_task import providers
executable=config_dir()/'startup codex & version'
executable.write_text('#!/usr/bin/env python3\nprint("Codex 13.2.1")\n')
executable.chmod(0o700)
failed=config_dir()/'failed claude'
failed.write_text('#!/usr/bin/env python3\nraise SystemExit(7)\n')
failed.chmod(0o700)
calls=[]
def installed():
    calls.append(threading.current_thread().name)
    return {'codex':str(executable),'claude':str(failed)}
providers.installed_providers=installed
providers.discover_windows=lambda *a:[]
target_ui.installation_details=providers.installation_details
w=make()
try:
    assert len(calls)==1 and calls[0]!=threading.current_thread().name
    page=w.monitor_tabs.pages['codex']
    assert str(executable) in page.identity.get_text() and '13.2.1' in page.identity.get_text()
    assert str(failed) in w.monitor_tabs.pages['claude'].identity.get_text() and 'Version unavailable' in w.monitor_tabs.pages['claude'].identity.get_text()
    w.refresh();pump(w)
    assert len(calls)==1 and str(executable) in page.identity.get_text() and '13.2.1' in page.identity.get_text()
    assert 'start-watch' not in commands and 'check-quota' not in commands
finally:w.destroy()
''')


def test_provider_columns_keep_all_information_and_semantic_colors():
    run_gui(r'''
from recharge_ai_task.provider_monitor import provider_status
from recharge_ai_task.provider_monitor_ui import ProviderDetails
now=time.time()
config=AppConfig.load()
status=provider_status('codex',targets=[a,b],config=config,usage={},
    quota=Quota('Pro fixture',RateWindow(87,300,now+600),RateWindow(22,10080,now+2000),False),
    checked_at=now,runtime=dict(desktop_watch=True,watch_progress={'providers':{'codex':dict(phase='grace_period',updated_at=now,checked_at=now,next_check_at=now+25,recovery_at=now+25,pending_cycle=True,pending_recipients=2,pending_messages=1,pending_goals=1)}}),now=now)
status['installation']='Executable: /very/long/custom/provider/path/codex\nCodex 15.16.17'
w=make()
current=[status]
w._render_provider_views=lambda:w.monitor_tabs.update({'codex':current[0]},30)
try:
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1920,1080);pump(w)
        assert w.get_size().width==1920 and w.get_size().height==1080,w.get_size()
        w.monitor_tabs.update({'codex':status},30)
        click(w.monitor_tabs.tab_labels['codex'],w);pump(w)
        page=w.monitor_tabs.pages['codex']
        assert '/very/long/custom/provider/path/codex' in page.identity.get_text()
        assert 'Pro fixture' in page.identity.get_text() and '15.16.17' in page.identity.get_text()
        for key in ('availability','freshness','check','check_detail','recovery','countdown','selection','stats','actions'):
            assert status[key] in page.get_text(),(key,page.get_text())
        assert '87% used' in page.quota.get_text() and '22% used' in page.quota.get_text()
        assert pos(page.automation,w)[0]>pos(page.quota,w)[0]+page.quota.get_allocated_width()
        assert abs(pos(page.quota,w)[1]-pos(page.automation,w)[1])<=2
        colors=status_colors(w)
        assert colors['success'] in page.quota.get_label()
        assert colors['warning'] in page.quota.get_label()
        assert colors['warning'] in w.monitor_tabs.tab_labels['codex'].get_label()
        for label in page.labels:
            assert label.get_layout().get_pixel_size()[0]<=label.get_allocated_width()
        for label in page.labels:label.select_region(0,0)
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-14_provider-columns-'+('dark' if dark else 'light')+'.png')
        # A real small page uses one full-width column instead of clipping.
        original=w.monitor_tabs.get_nth_page(1).get_child()
        viewport=page.get_parent();viewport.remove(page)
        probe=Gtk.Window();probe.set_default_size(500,500);probe.add(page);probe.show_all();pump(w)
        assert pos(page.automation,probe)[1]>=pos(page.quota,probe)[1]+page.quota.get_allocated_height()
        assert page.identity.get_text().endswith('15.16.17')
        probe.remove(page);viewport.add(page);probe.destroy();pump(w)
    failed=dict(status,error='Fixture refresh failed',state='error',availability='Quota unavailable')
    current[0]=failed;w._render_provider_views();pump(w)
    assert status_colors(w)['error'] in page.alerts.get_label()
    assert status_colors(w)['error'] in w.monitor_tabs.tab_labels['codex'].get_label()
    healthy=dict(status,state='enabled')
    current[0]=healthy;w._render_provider_views();pump(w)
    assert status_colors(w)['success'] in w.monitor_tabs.tab_labels['codex'].get_label()
finally:w.destroy()
''')
