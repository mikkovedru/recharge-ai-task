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


def test_inactive_main_selection_previews_saved_settings_without_reactivating():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    saved=replace(w.selected[b.key],send_prompt=False,send_goal=False,prompt_limit=7,goal_limit=3,
                  custom_prompt='Retained custom text',custom_prompt_once='saved-once-token')
    w.update_recipient(saved);w.remove_recipient(b.key);pump(w)
    before=AppConfig.load().desktop_targets;sent=list(commands)
    def choose(key):
        path=next(r.path for r in w.filtered if r[17]==key)
        w.table.set_cursor(path,w.title_column,False);pump(w)
    def contrast(fg,bg):
        def light(c):
            return sum(weight*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4)
                       for weight,v in zip((.2126,.7152,.0722),(c.red,c.green,c.blue)))
        lo,hi=sorted((light(fg),light(bg)))
        return (hi+.05)/(lo+.05)
    for theme,dark in (('Mint-X',False),('Adwaita',False),('Adwaita',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w,.4)
        for size in ((1440,980),(1120,820)):
            w.resize(*size);choose(b.key)
            assert p.preview_key==b.key and p.selected_key is None
            assert p.editor_frame.get_style_context().has_class('target-settings-preview')
            assert p.editor_notice.get_visible()
            assert p.custom.get_active() and p.once.get_active()
            assert not p.custom.is_sensitive() and not p.once.is_sensitive()
            assert p.prompt_limit.limited.get_label()=='7' and p.goal_limit.limited.get_label()=='3'
            for control in (p.prompt_limit,p.goal_limit):
                assert control.off.get_active()
                assert all(not button.get_style_context().has_class('saved-limit') for button in control.modes.values())
                button=control.off;context=button.get_style_context();flags=button.get_state_flags()
                foreground=button.get_child().get_style_context().get_color(button.get_child().get_state_flags())
                background=context.get_background_color(flags)
                assert contrast(foreground,background)>=4.5,(theme,dark,foreground,background)
            assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)=='Retained custom text'
            assert not p.message.get_editable() and p.message.is_sensitive()
            assert b.key not in w.selected and b.key not in p.rows
            assert AppConfig.load().desktop_targets==before
            w.refresh();pump(w)
            assert p.preview_key==b.key and p.custom.get_active() and p.once.get_active()
            choose(a.key)
            assert p.selected_key==a.key and p.preview_key is None and not p.editor_notice.get_visible()
            assert p.custom.is_sensitive() and p.message.get_editable()
            w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/2026-11-17_passive-settings-member-%s-%s-%s.png'%(theme,dark,size[0]))
            choose(b.key);w.check_resize();w.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/2026-11-17_passive-settings-preview-%s-%s-%s.png'%(theme,dark,size[0]))
    assert [c for c in commands[len(sent):] if c in ('start-watch','start-watch-blocked')]==[]
    w.remove_recipient(a.key);pump(w);choose(b.key)
    assert not p.rows and p.preview_key==b.key and p.once.get_active()
    w.update_recipient(replace(w.targets[b.key],custom_prompt=None,custom_prompt_once=''),include=False);pump(w)
    assert not p.custom.get_active() and not p.once.get_active()
    assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)==w._prompt_text()
finally:w.destroy()
''')


def test_passive_members_keep_editor_background_but_readonly_previews_are_distinct():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    def backgrounds():
        w.check_resize()
        image=cairo.ImageSurface(cairo.FORMAT_ARGB32,p.message.get_allocated_width(),p.message.get_allocated_height())
        p.message.draw(cairo.Context(image));image.flush()
        offset=(image.get_height()-10)*image.get_stride()+(image.get_width()-10)*4
        return (p.editor_frame.get_style_context().get_background_color(Gtk.StateFlags.NORMAL).to_string(),
                bytes(image.get_data()[offset:offset+4]))
    for theme,dark in (('Mint-X',False),('Adwaita',False),('Adwaita',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w,.4)
        saved=replace(w.targets[a.key],send_prompt=True,send_goal=True,custom_prompt='Editable custom message',prompt_limit=7,goal_limit=3)
        w.update_recipient(saved);p.select_recipient(a.key);pump(w)
        active=backgrounds()
        p.goal_limit.off.clicked();p.prompt_limit.off.clicked();pump(w)
        assert p.rows[a.key].get_style_context().has_class('target-passive')
        assert not p.editor_frame.get_style_context().has_class('target-settings-preview')
        assert backgrounds()==active,(theme,dark,'passive member background')
        assert p.message.get_editable() and p.message.get_cursor_visible()
        p.message_buffer.set_text('Edited while actions are off');pump(w)
        assert w.selected[a.key].custom_prompt=='Edited while actions are off'
        for control in (p.goal_limit,p.prompt_limit):
            for button in control.modes.values():
                assert not button.get_style_context().has_class('saved-limit')
        w.remove_recipient(a.key);pump(w)
        path=next(r.path for r in w.filtered if r[17]==a.key)
        w.table.set_cursor(path,w.title_column,False);pump(w)
        assert p.preview_key==a.key and not p.message.get_editable()
        preview=backgrounds()
        assert preview[0]==active[0],(theme,dark,'editor frame must remain unchanged')
        assert preview[1]!=active[1],(theme,dark,'read-only message must look read-only')
        assert p.message.get_style_context().has_class('inherited-message')
        assert p.message_buffer.get_text(*p.message_buffer.get_bounds(),True)=='Edited while actions are off'
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-17_readonly-target-preview-%s-%s.png'%(theme,dark))
        w.transfer_recipient();pump(w)
        assert a.key in w.selected and not any(w.selected[a.key].signal_actions())
        assert p.message.get_editable() and p.message.get_cursor_visible()
        assert not p.message.get_style_context().has_class('inherited-message')
        assert backgrounds()==active,(theme,dark,'added passive target is editable')
finally:w.destroy()
''')
