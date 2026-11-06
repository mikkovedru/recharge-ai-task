"""Muse provider setup and terminal launch through the GTK dashboard."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK and X11')


def test_muse_selection_quota_and_terminal_action_preserve_other_providers():
    run_gui(r'''
from gi.repository import GLib
from recharge_ai_task.muse import parse_usage,DESKTOP_LIMITATION
from recharge_ai_task import muse
original_discovery=target_ui.discover_targets
target_ui.discover_targets=lambda provider='codex':Inventory(warnings=[DESKTOP_LIMITATION]) if provider=='muse' else original_discovery()
quota_calls=[]
def quota(path):
    quota_calls.append(path);now=time.time()
    return parse_usage({'schemaVersion':1,'allowance':{'tier':'test','asOfMs':int(now*1000),
        'window':{'usedPercent':42,'resetsAtMs':int((now+3600)*1000)},
        'weekly':{'usedPercent':30,'resetsAtMs':int((now+86400)*1000)}}})
target_ui.fetch_muse_quota=quota
original_control=target_ui.tray_control.request
runtime['muse_support']=True
def control(command='status',**kwargs):
    if command=='start-cli':
        commands.append(command);runtime['cli_running']=True
        return dict(runtime)
    return original_control(command,**kwargs)
target_ui.tray_control.request=control
w=make()
try:
    def select():
        dialogs=[item for item in Gtk.Window.list_toplevels() if isinstance(item,settings_ui.SettingsDialog)]
        if not dialogs:return True
        d=dialogs[0]
        assert [row[1] for row in d.provider.get_model()]==['codex','claude','muse']
        d.set_accept_focus(True);d.set_focus_on_map(True);pump(d)
        d.provider.grab_focus()
        subprocess.run(['xdotool','windowactivate','--sync',str(d.get_window().get_xid())],check=True)
        subprocess.run(['xdotool','key','End'],check=True)
        pump(d)
        assert d.provider.get_active_id()=='muse', (d.provider.get_active_id(), d.get_focus(), d.is_active())
        assert d.muse_path.get_sensitive() and d.muse_args.get_sensitive()
        assert not d.path.get_sensitive() and not d.claude_path.get_sensitive()
        assert not d.mode.get_sensitive() and d.mode.get_active_id()=='cli'
        d.muse_path.set_text('/test/muse');d.muse_args.set_text('resume --last')
        click(d.get_widget_for_response(Gtk.ResponseType.OK),d)
        return False
    GLib.timeout_add(50,select);w.settings();pump(w)
    stored=AppConfig.load()
    assert stored.provider=='muse' and stored.muse_path=='/test/muse' and stored.muse_args==['resume','--last']
    assert w.get_title().endswith('Meta Muse Code')
    assert not w.selected and len(w.store)==0
    assert quota_calls and all(path=='/test/muse' for path in quota_calls)
    assert '42% used' in w.quota_label.get_text() and '30% used' in w.quota_label.get_text()
    assert 'app/browser' in w.status.text()
    assert w.watch_button.get_label()=='Start Muse Code CLI' and w.watch_button.get_sensitive()
    assert not w.send_button.get_sensitive()
    w.watch_button.clicked();pump(w)
    assert 'start-cli' in commands and 'start-watch' not in commands
    assert w.watch_button.get_label()=='CLI service running' and not w.watch_button.get_sensitive()
    assert 'Muse Code CLI launched' in w.status.text()
    w.save();assert AppConfig.load().mode=='cli'
    assert {t.key for t in AppConfig.load().all_targets()}=={a.key,b.key}
    d=settings_ui.SettingsDialog(w);pump(w)
    try:
        d.resize(620,420);pump(w)
        assert d.get_size().height<=420
        assert d.scroller.get_vadjustment().get_upper()>d.scroller.get_vadjustment().get_page_size()
        for dark in (False,True):
            Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
            Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w)
            d.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*d.get_size());d.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/2026-11-07_muse-settings-'+('dark' if dark else 'light')+'.png')
    finally:d.destroy()
    runtime['cli_running']=False
    stored=AppConfig.load();stored.provider='codex';stored.save();w.poll_runtime();pump(w)
    assert set(w.selected)=={a.key,b.key} and len(w.store)==2
    assert 'Start Desktop watch'==w.watch_button.get_label()
    assert 'Muse Code' not in w.watch_button.get_tooltip_text()
finally:w.destroy()
''')
