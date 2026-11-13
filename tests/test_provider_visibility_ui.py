"""Provider visibility, explicit checks and Settings sizing in real GTK."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_empty_categories_hide_and_selection_returns_to_all():
    run_gui(r'''
c=replace(b,id='claude',provider='claude')
target_ui.discover_targets=lambda:Inventory([a,b,c],providers=('codex','claude'),installed_providers=('codex','claude'))
w=make();p=w.recipient_panel
try:
    def visible(group):return [key for key,button in group.buttons.items() if button.get_parent().get_visible()]
    assert visible(p.provider_filter)==['all','codex']
    assert visible(w.provider_filter)==['all','codex','claude']
    assert not w.monitor_tabs.tab_headers['muse'].get_sensitive()
    assert w.monitor_tabs.tab_headers['codex'].get_sensitive()
    w.update_recipient(c);pump(w)
    assert visible(p.provider_filter)==['all','codex','claude']
    click(p.provider_filter.buttons['claude'],w)
    assert len(p._visible_rows())==1
    w.remove_recipient(c.key);pump(w)
    assert p.provider_filter.get_active_id()=='all'
    assert visible(p.provider_filter)==['all','codex']
    w.show_all();pump(w)
    assert visible(p.provider_filter)==['all','codex']
    w._apply_inventory(Inventory([a,b,c],providers=('codex','claude'),installed_providers=('codex',)))
    pump(w)
    assert visible(w.provider_filter)==['all','codex']
    assert len(w.filtered)==3  # History stays accessible through All.
    assert w.monitor_tabs.get_n_pages()==7
    p.provider_filter.buttons['codex'].grab_focus();pump(w)
    subprocess.run(['xdotool','key','Right'],check=True);pump(w)
    assert p.provider_filter.get_active_id()=='all'
    w.remove_recipient(a.key);w.remove_recipient(b.key);pump(w)
    assert visible(p.provider_filter)==['all'] and p.empty_label.get_visible()
finally:w.destroy()
''')


def test_provider_check_refreshes_installation_versions_chats_and_quota():
    run_gui(r'''
import threading
started=threading.Event();release=threading.Event();calls=[];quota_calls=[]
c=replace(b,id='claude',provider='claude')
def check():
    calls.append(threading.current_thread().name)
    started.set();assert release.wait(5)
    return Inventory([a,b,c],providers=('codex','claude'),installed_providers=('codex','claude'),
        provider_details={'codex':'Executable: /fixture/codex\nCodex 9.8.7','claude':'Claude 2.3.4'})
target_ui.check_providers=check
target_ui.fetch_claude_quota=lambda:quota_calls.append('claude') or Quota('Claude fixture',RateWindow(30,300,9999999999),None,False)
w=make()
try:
    assert w.refresh_button.get_label()=='Check chats and statuses'
    assert w.monitor_tabs.get_action_widget(Gtk.PackType.END) is w.providers_button
    # Exercise an actual click, but release the background fixture before pump waits.
    release.set();click(w.providers_button,w)
    assert started.is_set() and len(calls)==1 and calls[0]!=threading.current_thread().name
    assert w.installed_providers==('codex','claude') and len(w.targets)==3
    assert quota_calls and 'Claude fixture' in w.monitor_tabs.pages['claude'].get_text()
    assert 'Codex 9.8.7' in w.monitor_tabs.pages['codex'].get_text()
    assert 'Codex 9.8.7' in w.monitor_tabs.tab_headers['codex'].get_tooltip_text()
    assert w.provider_filter.buttons['claude'].get_parent().get_visible()
    assert not w.provider_filter.buttons['muse'].get_parent().get_visible()
    assert w.providers_button.get_sensitive() and w.providers_button.get_label()=='Check providers'
    assert 'start-watch' not in commands and 'check-quota' not in commands
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820,w.get_size()
        assert pos(w.providers_button,w)[0]+w.providers_button.get_allocated_width()<=w.get_size().width
        assert pos(w.providers_button,w.monitor_tabs)[1]<w.monitor_tabs.get_tab_label(w.monitor_tabs.get_nth_page(0)).get_allocated_height()+20
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-14_provider-check-'+('dark' if dark else 'light')+'.png')
finally:w.destroy()
''')
