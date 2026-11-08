"""Unified provider filtering, saved recipients and independent quota display."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK and X11')


def test_all_provider_filter_mouse_keyboard_search_resize_and_persistence():
    run_gui(r'''
# Deliberately identical kind, profile, ID and title across providers.
c=Target('session','same','Shared name',instance='fixture',provider='claude',send_prompt=True,send_goal=False)
m=replace(c,provider='muse')
config=AppConfig.load();config.desktop_targets.extend([c.to_dict(),m.to_dict()]);config.save()
target_ui.discover_targets=lambda:Inventory([a,b,c,m],providers=('codex','claude','muse'))
target_ui.fetch_claude_quota=lambda:(_ for _ in ()).throw(RuntimeError('fixture login required'))
target_ui.fetch_muse_quota=lambda _:Quota('Muse test',RateWindow(42,300,9999999999),RateWindow(30,10080,9999999999),False)
runtime['unified_providers']=True
w=make()
try:
    assert w.provider_filter.get_active_id()=='all' and len(w.filtered)==4
    assert set(w.targets)=={a.key,b.key,c.key,m.key} and len(w.selected)==4
    assert 'fixture login required' not in w.status.text()
    assert 'fixture login required' in w.monitor_tabs.pages['claude'].get_text()
    assert '42% used' in w.quota_label.get_text() and '40% used' in w.quota_label.get_text()
    settings_before=tray_control.watch_settings(AppConfig.load())
    # Real mouse opens the list; keyboard chooses Claude.
    w.set_accept_focus(True);w.set_focus_on_map(True);pump(w)
    subprocess.run(['xdotool','windowactivate','--sync',str(w.get_window().get_xid())],check=True)
    click(w.provider_filter,w)
    subprocess.run(['xdotool','key','Home','Down','Down','Return'],check=True);pump(w)
    assert w.provider_filter.get_active_id()=='claude' and len(w.filtered)==1,w.provider_filter.get_active_id()
    assert set(w.selected)=={a.key,b.key,c.key,m.key}
    assert tray_control.watch_settings(AppConfig.load())==settings_before
    w._toggle(None,'0');pump(w)
    assert not next(t for t in AppConfig.load().all_targets() if t.key==c.key).send_prompt
    assert next(t for t in AppConfig.load().all_targets() if t.key==m.key).send_prompt
    assert next(row for row in w.store if row[17]==m.key)[0]
    w.highlight_recipient(m.key);pump(w)
    assert w.provider_filter.get_active_id()=='muse' and w._row_target().key==m.key
    w.search.set_text('does not exist');pump(w);assert len(w.filtered)==0
    w.search.set_text('shared');pump(w);assert len(w.filtered)==1
    w.search.set_text('');w.provider_filter.set_active_id('all');pump(w)
    assert len(w.filtered)==4 and len(w.selected)==4
    assert not any(w.selected[c.key].signal_actions()) and len(AppConfig.load().targets())==3
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820
        assert w.table.get_parent().get_allocated_height()>=80
        x,y=pos(w.provider_filter,w)
        assert x>=0 and x+w.provider_filter.get_allocated_width()<=w.get_size().width
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-07_unified-chats-'+('dark' if dark else 'light')+'.png')
    w.provider_filter.set_active_id('muse');pump(w)
finally:w.destroy()
w=make()
try:
    assert w.provider_filter.get_active_id()=='muse' and len(w.filtered)==1
    assert set(w.selected)=={a.key,b.key,c.key,m.key}
    assert not any(w.selected[c.key].signal_actions())
    assert AppConfig.load().provider=='codex'
finally:w.destroy()
''')


def test_fresh_install_automatically_lists_every_detected_provider():
    run_gui(r'''
# No saved settings and no manual provider change.
from recharge_ai_task.config import config_path
config_path().unlink()
c=Target('session','c','Claude Code project',provider='claude')
m=Target('session','m','Muse Code project',provider='muse')
target_ui.discover_targets=lambda:Inventory([a,c,m],providers=('codex','claude','muse'))
target_ui.fetch_claude_quota=lambda:Quota('Claude',RateWindow(10,300,9999999999),None,False)
target_ui.fetch_muse_quota=lambda _:Quota('Muse',RateWindow(20,300,9999999999),None,False)
w=make()
try:
    assert w.provider_filter.get_active_id()=='all' and len(w.filtered)==3
    assert not w.selected
    assert set(w.active_providers)=={'codex','claude','muse'}
    assert 'Anthropic Claude' in w.quota_label.get_text() and 'Meta Muse Code' in w.quota_label.get_text()
finally:w.destroy()
''')
