"""GTK provider selection and real X11 delivery to an isolated fixture window."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK and X11')


def test_settings_provider_switch_preserves_both_recipient_lists():
    run_gui(r'''
from gi.repository import GLib
from recharge_ai_task.claude import parse_usage
claude_target=Target('window','42','Claude fixture',provider='claude',pid=7,instance='fixture',send_prompt=True,send_goal=False)
config=AppConfig.load();config.desktop_targets.append(claude_target.to_dict());config.save()
target_ui.fetch_claude_quota=lambda:parse_usage({'five_hour':{'utilization':51,'resets_at':'2026-11-06T18:00:00Z'}})
target_ui.discover_targets=lambda provider='codex':Inventory([claude_target] if provider=='claude' else [a,b])
runtime['claude_support']=True
w=make()
def change(provider):
    def select():
        dialogs=[item for item in Gtk.Window.list_toplevels() if isinstance(item,settings_ui.SettingsDialog)]
        if not dialogs:return True
        d=dialogs[0]
        d.provider.set_active_id(provider)
        assert d.claude_path.get_sensitive()==(provider=='claude')
        assert d.path.get_sensitive()==(provider=='codex')
        d.claude_args.set_text('--continue')
        d.response(Gtk.ResponseType.OK)
        return False
    GLib.timeout_add(50,select)
    w.settings();pump(w)
try:
    change('claude')
    assert AppConfig.load().provider=='claude'
    assert w.get_title().endswith('Anthropic Claude')
    assert set(w.selected)=={claude_target.key}
    assert len(w.store)==1 and w.store[0][1]=='Claude fixture'
    assert '51% used' in w.quota_label.get_text()
    assert not w._uses_watch_quota()
    w.save();pump(w)
    assert {t.provider for t in AppConfig.load().all_targets()}=={'codex','claude'}
    w._apply_inventory(Inventory([claude_target]));assert len(w.store)==1
    change('codex')
    assert AppConfig.load().provider=='codex' and len(w.store)==2
    assert set(w.selected)=={a.key,b.key}
    assert AppConfig.load().claude_args==['--continue']
    d=settings_ui.SettingsDialog(w);pump(w)
    try:
        d.resize(620,420);pump(w)
        assert d.get_size().height<=420
        assert d.scroller.get_vadjustment().get_upper()>d.scroller.get_vadjustment().get_page_size()
        save=d.get_widget_for_response(Gtk.ResponseType.OK)
        assert save.get_mapped() and save.get_allocated_height()>0
        d.provider.grab_focus();pump(w)
        subprocess.run(['xdotool','windowactivate','--sync',str(d.get_window().get_xid())],check=True)
        subprocess.run(['xdotool','key','Home','Down'],check=True);pump(w)
        assert d.provider.get_active_id()=='claude'
        d.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*d.get_size());d.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_claude-settings.png')
    finally:d.destroy()
    config=AppConfig.load();config.provider='claude';config.save()
    w.poll_runtime();pump(w)
    assert w.config.provider=='claude' and set(w.selected)=={claude_target.key}
    assert len(w.store)==1 and '51% used' in w.quota_label.get_text()
finally:w.destroy()
''')


def test_real_x11_claude_identity_and_window_input():
    run_gui(r'''
from recharge_ai_task import targets,target_delivery
import os
fixture=Gtk.Window(title='Recharge Claude delivery fixture')
fixture.set_wmclass('claude','Claude')
entry=Gtk.Entry();fixture.add(entry);fixture.set_default_size(480,120);fixture.show_all();entry.grab_focus()
def pump_events(seconds=.15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
pump_events()
try:
    xid=str(fixture.get_window().get_xid())
    matches=[t for t in targets.discover_windows('claude') if t.id==xid]
    assert len(matches)==1 and matches[0].provider=='claude' and matches[0].pid==os.getpid()
    assert not any(t.id==xid for t in targets.discover_windows())
    received=[];entry.connect('activate',lambda widget:received.append(widget.get_text()))
    # Actual mouse focus, typing and Return through the production delivery path.
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True)
    subprocess.run(['xdotool','mousemove','--window',xid,'150','40','click','1'],check=True)
    pump_events()
    result=target_delivery.deliver_targets(matches,'Continue Claude',key_delay=0)[0]
    pump_events()
    assert result.success and received==['Continue Claude'],(result,received,entry.get_text())
    stale=replace(matches[0],pid=os.getpid()+1)
    assert not target_delivery.deliver_targets([stale],'Wrong recipient')[0].success
    pump_events();assert received==['Continue Claude']
finally:fixture.destroy()
''')
