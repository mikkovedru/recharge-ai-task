import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_recipient_overrides_counts_and_drafts_survive_refresh_and_reselection():
    result=subprocess.run([sys.executable,'-c',r'''
from dataclasses import replace
import time
from recharge_ai_task import target_ui,autostart,target_delivery
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.quota import Quota,RateWindow
from recharge_ai_task.delivery_policy import UsageLedger
from gi.repository import Gtk

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'codex'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(5,300,0),None,False)
target_ui.tray_control.request=lambda *a,**kw:{'desktop_watch':False,'recipient_policies':True}
a=Target('thread','private-chat-id-a','Same title',instance='one',task_status='Idle',goal_status='Paused',send_prompt=True,send_goal=False)
b=replace(a,id='private-chat-id-b',instance='two')
target_ui.discover_targets=lambda:Inventory([a,b])
sent=[]
target_delivery._send_thread=lambda t,text:sent.append((t.key,text))
AppConfig(desktop_targets=[a.to_dict(),b.to_dict()],continue_prompt='Default message').save()
def pump(w):
    until=time.monotonic()+.3
    while time.monotonic()<until or w.discovery_busy or w.runtime_busy or w.quota_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
def make():
    w=target_ui.TargetPicker(quit_on_close=False)
    w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    return w
w=make();p=w.recipient_panel
assert len(p.rows)==2
for control in (p.prompt_limit,p.goal_limit):
    assert not hasattr(control,'choice') and control.default.get_active()
    control.unlimited.clicked()
    assert control.value()==-1 and control.unlimited.get_active() and not control.default.get_active()
    control.limited.clicked();control.number_popover.popdown()
    control.number.set_value(0)
    assert control.value()==0 and control.limited.get_active() and not control.unlimited.get_active()
    control.default.clicked()
    assert control.value() is None and control.default.get_active() and not control.limited.get_active()
assert w.selected[a.key].prompt_limit is None and w.selected[a.key].goal_limit is None
assert not p.message.get_editable() and not p.message.get_cursor_visible()
passive=p.message.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
# Display labels allow row selection rather than accidental text selection.
for row in p.rows.values():
    for label in row.get_child().get_children():
        assert not label.get_selectable()
        assert 'private-chat-id' not in label.get_text()
    assert 'private-chat-id' not in row.get_tooltip_text()
# Duplicate titles are selected by stable profile/chat identity, even after sort.
w.table_layout.sort('id', True)
p.list.select_row(p.rows[b.key])
assert w._row_target().key == b.key
w.search.set_text('no matching chat');w.filtered.refilter()
assert len(w.filtered)==0
p.list.select_row(p.rows[a.key])
assert w.search.get_text()=='' and w._row_target().key==a.key
assert 'private-chat-id' not in p.editor_title.get_text()
# Activating an already selected item re-highlights it without sending anything.
w.table.get_selection().unselect_all()
p.list.emit('row-activated',p.rows[a.key])
assert w._row_target().key==a.key and sent==[]

p.list.select_row(p.rows[a.key])
p.default_prompt.limited.clicked()
p.default_prompt.number_popover.popdown()
p.default_prompt.number.set_value(3)
assert AppConfig.load().prompt_limit==3
p.custom.set_active(True)
pump(w)
active=p.message.get_style_context().get_background_color(Gtk.StateFlags.NORMAL)
assert p.message.get_editable() and p.message.get_cursor_visible()
assert passive.to_string()!=active.to_string()
p.message_buffer.set_text('Specific\nmessage')
p.prompt_limit.limited.clicked()
p.prompt_limit.number_popover.popdown()
p.prompt_limit.number.set_value(1)
assert w.selected[a.key].custom_prompt=='Specific\nmessage' and w.selected[a.key].prompt_limit==1
assert 'Custom: Specific' in p.rows[a.key].preview.get_text()
# Same-titled recipients have independent identities and inherited defaults.
assert w.selected[b.key].custom_prompt is None and w.selected[b.key].prompt_limit is None
p.message_buffer.place_cursor(p.message_buffer.get_iter_at_offset(4))
w._summary()
assert p.message_buffer.get_iter_at_mark(p.message_buffer.get_insert()).get_offset()==4
w._apply_inventory(Inventory([replace(a,title='Renamed'),b]))
assert w.selected[a.key].custom_prompt=='Specific\nmessage' and w.selected[a.key].prompt_limit==1
# Deselecting retains overrides for later reuse.
w.update_recipient(replace(w.selected[a.key],send_prompt=False))
assert a.key not in w.selected and a.key not in p.rows
w.update_recipient(replace(w.preferences[a.key],send_prompt=True))
assert w.selected[a.key].custom_prompt=='Specific\nmessage'
assert target_delivery.send_signals([w.selected[a.key]],w._prompt_text(),manual=True)[0].success
w._summary()
assert '0 left of 1' in p.rows[a.key].allowance.get_text()
assert 'limit reached' in p.rows[a.key].plan.get_text()
assert target_delivery.send_signals([w.selected[a.key]],w._prompt_text(),manual=True)[0].skipped
assert sent==[(a.key,'Specific\nmessage')]
p.list.select_row(p.rows[a.key]);p.reset.clicked()
assert not UsageLedger().snapshot()
p.prompt_limit.unlimited.clicked()
assert w.selected[a.key].prompt_limit==-1
# Clearing the default is valid when all message recipients have custom text.
w.update_recipient(replace(w.selected[b.key],custom_prompt='Other message'))
w.signal_buffer.set_text('')
w.destroy()
w=make();p=w.recipient_panel
assert w.selected[a.key].custom_prompt=='Specific\nmessage' and w.selected[a.key].prompt_limit==-1
assert w.selected[b.key].custom_prompt=='Other message'
assert AppConfig.load().prompt_limit==3
original_load=AppConfig.__dict__['load']
AppConfig.load=classmethod(lambda cls:(_ for _ in ()).throw(OSError('settings unreadable')))
w.send()
assert not w.busy and 'Cannot validate delivery settings' in w.status.latest_text
AppConfig.load=original_load
w.destroy()
'''],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr
