"""Passive target membership and the explicit main-list transfer control."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_passive_recipients_stay_pinned_and_visible_in_both_lists():
    run_gui(r'''
from gi.repository import Pango
c=replace(b,id='c',title='Other discovered chat',last_active_at=1,send_prompt=False)
target_ui.discover_targets=lambda:Inventory([a,b,c])
w=make();p=w.recipient_panel
try:
    w.update_recipient(replace(w.selected[b.key],send_prompt=False,send_goal=False));pump(w)
    for key in w.table_layout.columns:
        for descending in (False,True):
            w.table_layout.sort(key,descending)
            assert [r[18] for r in w.filtered]==[True,True,False],(key,descending)
            assert {r[17] for r in list(w.filtered)[:2]}=={a.key,b.key}
    for theme,dark in (('Mint-X',False),('Adwaita',False),('Adwaita',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for width,height in ((1920,1080),(1120,820)):
            w.resize(width,height);w.table_layout.sort('title');pump(w)
            row=p.rows[b.key]
            p.select_recipient(b.key);pump(w)
            assert row.passive_badge.get_visible() and 'Passive' in row.passive_badge.get_text()
            assert row.get_style_context().has_class('target-actions-off')
            assert row.get_state_flags() & Gtk.StateFlags.SELECTED
            model=w.filtered
            column=w.title_column;cell=column.get_cells()[0]
            for key,passive in ((b.key,True),(a.key,False),(c.key,False)):
                iterator=next(r.iter for r in model if r[17]==key)
                column.cell_set_cell_data(model,iterator,False,False)
                assert cell.get_property('cell-background-set')==passive
                assert cell.get_property('style')==Pango.Style.NORMAL
                assert cell.get_property('text')==w.targets[key].title
            for key in ('task_status','goal_status'):
                status_column=w.table_layout.columns[key][0]
                iterator=next(r.iter for r in model if r[17]==b.key)
                status_column.cell_set_cell_data(model,iterator,False,False)
                status_cell=status_column.get_cells()[0]
                assert 'Passive' not in status_cell.get_property('text')
            for button in (p.transfer,w.send_button,p.reset_all,p.reset):
                x,y=pos(button,p.editor_scroller)
                assert x>=0 and x+button.get_allocated_width()<=p.editor_scroller.get_allocated_width()
            assert len({button.get_allocated_height() for button in (w.send_button,p.reset_all,p.reset)})==1
            assert pos(p.transfer,p.actions)[0]<pos(w.send_button,p.actions)[0]
            w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/2026-11-15_passive-targets-%s-%s-%s.png'%(theme,dark,width))
    w.refresh();pump(w)
    assert next(r for r in w.store if r[17]==b.key)[18]
    assert not any(w.selected[b.key].signal_actions())
    w.destroy();w=make();p=w.recipient_panel
    assert next(r for r in w.store if r[17]==b.key)[18]
    assert p.rows[b.key].passive_badge.get_visible()
    w.update_recipient(replace(w.selected[b.key],send_prompt=True));pump(w)
    assert not p.rows[b.key].passive_badge.get_visible()
    assert not p.rows[b.key].get_style_context().has_class('target-actions-off')
finally:w.destroy()
''')


def test_transfer_arrow_adds_passively_and_removes_the_selected_identity():
    run_gui(r'''
from recharge_ai_task.delivery_policy import UsageLedger
c=replace(b,id='c',title=b.title,instance='/another-profile',send_prompt=True,custom_prompt='Retain me',prompt_limit=7)
target_ui.discover_targets=lambda:Inventory([a,b,c])
w=make();p=w.recipient_panel
def choose(key):
    path=next(r.path for r in w.filtered if r[17]==key)
    w.table.set_cursor(path,w.title_column,False);pump(w)
try:
    w.table.get_selection().unselect_all();pump(w)
    assert not p.transfer.get_sensitive()
    choose(c.key)
    assert p.transfer.get_sensitive() and p.transfer.get_image().get_icon_name()[0]=='go-next-symbolic'
    assert 'Goal and Message will stay off' in p.transfer.get_tooltip_text()
    before=list(commands)
    click(p.transfer,w)
    assert c.key in w.selected and not any(w.selected[c.key].signal_actions())
    assert w.selected[c.key].custom_prompt=='Retain me' and w.selected[c.key].prompt_limit==7
    assert p.selected_key==c.key and w._row_target().key==c.key
    assert p.transfer.get_image().get_icon_name()[0]=='go-previous-symbolic'
    assert p.transfer.get_accessible().get_name()=='Remove from Targets & actions'
    assert c.key in {t.key for t in AppConfig.load().chosen_targets()}
    assert c.key not in {t.key for t in AppConfig.load().targets()}
    ledger=UsageLedger();ledger.finish(ledger.reserve(c.key,'prompt',7),'sent')
    p.transfer.grab_focus();pump(w)
    subprocess.run(['xdotool','key','space'],check=True);pump(w)
    assert c.key not in w.selected and b.key in w.selected
    assert not any(w.preferences[c.key].signal_actions())
    assert w.preferences[c.key].custom_prompt=='Retain me' and w.preferences[c.key].prompt_limit==7
    assert ledger.usage(c.key,'prompt').used==1
    assert p.transfer.get_image().get_icon_name()[0]=='go-next-symbolic'
    choose(a.key)
    assert p.transfer.get_image().get_icon_name()[0]=='go-previous-symbolic'
    click(p.transfer,w)
    assert a.key not in w.selected and not any(w.preferences[a.key].signal_actions())
    choose(c.key);click(p.transfer,w)
    w._apply_inventory(Inventory([a,b]));pump(w)
    choose(c.key)
    assert p.transfer.get_image().get_icon_name()[0]=='go-previous-symbolic'
    w._busy(True);assert not p.transfer.get_sensitive();w._busy(False)
    assert p.transfer.get_sensitive()
    w.search.set_text('No matching chat');w.filtered.refilter();pump(w)
    assert not p.transfer.get_sensitive()
    assert [command for command in commands[len(before):] if command in ('start-watch','start-watch-blocked')]==[]
    w.search.set_text('');w.filtered.refilter();pump(w)
    w.destroy();w=make();p=w.recipient_panel
    assert c.key in w.selected and a.key not in w.selected
    assert not any(w.selected[c.key].signal_actions())
    assert not w.dirty()
finally:w.destroy()
''')
