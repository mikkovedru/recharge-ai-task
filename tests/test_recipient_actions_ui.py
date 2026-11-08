"""Saved passive recipients, explicit removal and scoped count resets."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')


def test_passive_membership_removal_and_once_caption():
    run_gui(r'''
from recharge_ai_task.delivery_policy import UsageLedger
w=make();p=w.recipient_panel
try:
    w.update_recipient(replace(w.selected[b.key], send_prompt=False, send_goal=False));pump(w)
    assert b.key in p.rows and p.rows[b.key].get_style_context().has_class('recipient-passive')
    assert 'No actions selected' in p.rows[b.key].plan.get_text()
    assert b.key in {t.key for t in AppConfig.load().recipients()}
    assert b.key not in {t.key for t in AppConfig.load().targets()}
    w._apply_inventory(Inventory([a,b]));pump(w)
    assert b.key in p.rows and not w.selected[b.key].send_prompt
    w.destroy();w=make();p=w.recipient_panel
    assert b.key in p.rows and not w.selected[b.key].send_prompt
    p.select_recipient(b.key);p.prompt_limit.default.clicked();p.custom.set_active(True)
    p.message_buffer.set_text('Custom <tag> & text');p.once.set_active(True);pump(w)
    row=p.rows[b.key]
    assert 'Custom message (once): Custom <tag> & text' in row.allowance.get_text()
    assert '<b>Message</b>:' in row.allowance.get_label() and '(<b>once</b>)' in row.allowance.get_label()
    p.once.set_active(False);pump(w)
    assert 'Custom message: Custom <tag> & text' in row.allowance.get_text()
    assert 'turn off both Goal and Message' in row.remove.get_tooltip_text()
    assert pos(row.remove,w)[1]>pos(row.indicator,w)[1]
    p.list.emit('row-activated',row);pump(w)
    assert b.key not in w.selected and b.key not in p.rows
    table_row=next(r for r in w.store if r[17]==b.key)
    assert not table_row[0] and not table_row[12]
    assert b.key not in {t.key for t in AppConfig.load().recipients()}
    path=next(r.path for r in w.filtered if r[17]==b.key)
    w.table.emit('row-activated',path,w.title_column);pump(w)
    assert b.key in p.rows and not any(w.selected[b.key].signal_actions())
    assert w.selected[b.key].custom_prompt=='Custom <tag> & text'
    w.table.emit('row-activated',path,w.title_column);pump(w)
    assert len(p.rows)==2
    p.rows[a.key].remove.clicked();pump(w)
    assert a.key not in p.rows and a.key not in w.selected
    assert not AppConfig.load().targets() and not w.send_button.get_sensitive()
    w.destroy();w=make();p=w.recipient_panel
    assert set(p.rows)=={b.key}
    assert not w.dirty()
    previous=list(commands);w.toggle_watch();pump(w)
    assert 'Enable Send message or Resume goal' in w.status.text()
    assert [c for c in commands[len(previous):] if c in ('start-watch','start-watch-blocked')]==[]
finally:w.destroy()
''')


def test_multiselection_reset_scope_tooltips_and_send_caption():
    run_gui(r'''
from recharge_ai_task.delivery_policy import UsageLedger
w=make();p=w.recipient_panel;ledger=UsageLedger()
try:
    for target,action,n in ((a,'goal',2),(b,'prompt',3)):
        for _ in range(n):ledger.finish(ledger.reserve(target.key,action,None),'sent')
    removed=replace(b,id='removed',title='Removed recipient',prompt_limit=4)
    w.update_recipient(removed);w.remove_recipient(removed.key)
    ledger.finish(ledger.reserve(removed.key,'prompt',4),'uncertain')
    w._summary();pump(w)
    assert w.send_button.get_label()=='Send now\n(1 goals, 1 messages)'
    assert pos(w.send_button,w)[0]<pos(p.reset_all,w)[0]
    p.select_recipient(a.key);p.list.select_row(p.rows[b.key]);pump(w)
    assert p.selected_keys=={a.key,b.key}
    assert p.reset.get_label()=="Reset current recipients' (2) counts"
    w._summary();w._apply_inventory(Inventory([a,b]));pump(w)
    assert {row.key for row in p.list.get_selected_rows()}=={a.key,b.key}
    tip=p.reset.get_tooltip_text()
    assert '2 recipient(s)' in tip and 'Goal recipient' in tip and 'Message recipient' in tip
    assert 'used 2 → 0' in tip and 'used 3 → 0' in tip and 'Nothing is sent' in tip
    tip=p.reset_all.get_tooltip_text()
    assert '3 recipient(s)' in tip and 'Removed recipient' in tip and 'unconfirmed 1 → 0' in tip
    assert 'Remaining 3 → 4 of 4' in tip and 'not rearmed' in tip
    # Query-time preview reflects deliveries after the last row render.
    ledger.finish(ledger.reserve(b.key,'prompt',None),'sent')
    class Tooltip:
        def set_text(self,text):self.text=text
    tip=Tooltip();assert p._reset_tooltip(p.reset,0,0,False,tip,False)
    assert 'used 4 → 0' in tip.text
    p.reset.clicked();pump(w)
    assert ledger.usage(a.key,'goal').used==0 and ledger.usage(b.key,'prompt').used==0
    assert ledger.usage(removed.key,'prompt').used==1
    p.reset_all.clicked();pump(w);assert not ledger.snapshot()
    assert len(p.selected_keys)==2
    p.list.unselect_all();pump(w)
    assert not p.reset.get_sensitive()
    p.select_recipient(b.key);pump(w)
    assert p.reset.get_label()=="Reset current recipient's counts"
    assert '1 recipient(s)' in p.reset.get_tooltip_text()
finally:w.destroy()
''')


def test_pointer_double_click_multiselect_trash_and_narrow_window():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    w.set_accept_focus(True);w.set_focus_on_map(True);pump(w)
    xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True)
    def pointer(widget, *, twice=False, modifier=None):
        x,y=pos(widget,w)
        args=['xdotool','mousemove','--window',xid,str(x+min(30,widget.get_allocated_width()//2)),str(y+widget.get_allocated_height()//2)]
        if modifier:args+=['keydown',modifier]
        args+=['click']+(['--repeat','2','--delay','90'] if twice else [])+['1']
        if modifier:args+=['keyup',modifier]
        subprocess.run(args,check=True);pump(w)
    pointer(p.rows[a.key].title)
    pointer(p.rows[b.key].title,modifier='ctrl')
    assert p.selected_keys=={a.key,b.key},p.selected_keys
    pointer(p.rows[a.key].title)
    pointer(p.rows[b.key].title,modifier='shift')
    assert p.selected_keys=={a.key,b.key},p.selected_keys
    pointer(p.rows[b.key].title,twice=True)
    assert b.key not in p.rows
    path=next(r.path for r in w.filtered if r[17]==b.key)
    cell=w.table.get_cell_area(path,w.title_column)
    x,y=w.table.convert_bin_window_to_widget_coords(cell.x+25,cell.y+cell.height//2)
    x,y=w.table.translate_coordinates(w,x,y)
    subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y),'click','--repeat','2','--delay','90','1'],check=True);pump(w)
    assert b.key in p.rows
    pointer(p.rows[b.key].remove)
    assert b.key not in p.rows
    for width,height in ((1440,980),(1120,820),(1000,760)):
        w.resize(width,height);pump(w)
        assert w.get_size().width<=width and w.get_size().height<=height, w.get_size()
        for button in (w.send_button,p.reset_all,p.reset):
            x,y=pos(button,p.editor_scroller)
            assert x>=0 and x+button.get_allocated_width()<=p.editor_scroller.get_allocated_width()
finally:w.destroy()
''')
