"""Compact target allowances, custom messages and reset controls."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK')


def test_usage_custom_preview_large_infinity_and_reset_labels():
    run_gui(r'''
from recharge_ai_task.delivery_policy import UsageLedger
w=make();p=w.recipient_panel
try:
    p.select_recipient(b.key);pump(w)
    row=p.rows[b.key]
    assert row.allowance.get_text()=='Message: used 0 / ∞ (default)'
    assert not row.preview.get_visible() and 'Default:' not in row.allowance.get_text()
    assert p.reset.get_label()=="Reset current target's counts"
    assert p.reset_all.get_label()=='Reset counts for all'
    groups=[child.get_child() for child in p.actions.get_children()]
    assert groups[0].get_children()==[p.transfer,w.send_button]
    assert groups[1:]==[p.reset_all,p.reset]
    assert pos(w.send_button,w)[0]<pos(p.reset_all,w)[0]
    normal=Gtk.Label(label='∞')
    plain_height=normal.get_layout().get_pixel_extents()[0].height
    scaled_height=p.prompt_limit.unlimited.get_child().get_layout().get_pixel_extents()[0].height
    assert scaled_height>=plain_height*1.3,(plain_height,scaled_height)
    assert 'x-large' in p.prompt_limit.default.get_child().get_label()
    p.custom.set_active(True);p.message_buffer.set_text('Custom 🌻\nsecond line');pump(w)
    assert '    |    Custom message: Custom 🌻 second line' in row.allowance.get_text()
    assert 'Custom 🌻\nsecond line' in row.allowance.get_tooltip_text()
    assert row.allowance.get_layout().get_line_count()==1
    p.prompt_limit.limited.clicked();p.prompt_limit.number.set_value(5);p.prompt_limit.number_popover.popdown();pump(w)
    ledger=UsageLedger()
    for _ in range(2):ledger.finish(ledger.reserve(b.key,'prompt',5),'sent')
    ledger.finish(ledger.reserve(a.key,'goal',None),'sent')
    w._summary();pump(w)
    assert 'Message: used 2 / 5' in row.allowance.get_text()
    p.goal_limit.default.clicked();pump(w)
    assert row.allowance.get_text().startswith('Goal: used 0 / ∞')
    assert row.allowance.get_text().splitlines()[1].startswith('Message: used 2 / 5')
    p.custom.set_active(False);pump(w)
    assert 'Custom message:' not in row.allowance.get_text() and not row.preview.get_visible()
    p.reset.clicked();pump(w)
    assert ledger.usage(b.key,'prompt').used==0 and ledger.usage(a.key,'goal').used==1
    p.reset_all.clicked();pump(w);assert not ledger.snapshot()
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820
        assert pos(p.reset,p.editor_scroller)[0]+p.reset.get_allocated_width()<=p.editor_scroller.get_allocated_width()
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_usage-'+('dark' if dark else 'light')+'.png')
finally:w.destroy()
''')


def test_recipient_action_toolbar_wraps_and_keeps_button_heights():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    buttons=(w.send_button,p.reset_all,p.reset)
    for theme,dark in (('Adwaita',False),('Adwaita',True),('Mint-X',False)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for width,height in ((1920,1080),(1120,820)):
            w.resize(width,height);pump(w,.5)
            for position in (int(width*.35),int(width*.70)):
                w.workspace_split.set_position(position);pump(w,.5)
                assert len({button.get_allocated_height() for button in buttons})==1, [(b.get_allocated_width(),b.get_allocated_height()) for b in buttons]
                for button in buttons:
                    x,y=pos(button,p.actions)
                    assert x>=0 and x+button.get_allocated_width()<=p.actions.get_allocated_width()
                w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
                surface.write_to_png("/tmp/recharge-actions-%s-%s-%s-%s.png" % (theme,dark,width,position))
                assert max(pos(button,p.editor)[1]+button.get_allocated_height() for button in buttons) < pos(p.editor.get_children()[1],p.editor)[1]
                children=p.actions.get_children()
                natural=sum(child.get_preferred_width()[1] for child in children)+2*p.actions.get_column_spacing()
                if p.actions.get_allocated_width()>=natural:
                    assert len({pos(button,p.actions)[1] for button in buttons})==1
                    style=children[0].get_style_context();pad=style.get_padding(children[0].get_state_flags());border=style.get_border(children[0].get_state_flags())
                    assert p.actions.get_allocated_height() <= buttons[0].get_allocated_height()+pad.top+pad.bottom+border.top+border.bottom+2, (p.actions.get_allocated_height(),buttons[0].get_allocated_height(),pad,border)
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        click(p.reset_all,w)
        p.reset.grab_focus();pump(w)
        assert w.get_focus() is p.reset
        subprocess.run(['xdotool','key','space'],check=True);pump(w)
    # Exercise the same toolbar below the normal editor's minimum width.
    fixture=Gtk.Window();p.actions.reparent(fixture);fixture.set_default_size(250,300);fixture.show_all();pump(w,.5)
    assert len({pos(button,p.actions)[1] for button in buttons})>1
    assert len({button.get_allocated_height() for button in buttons})==1
    narrow_height=buttons[0].get_allocated_height()
    fixture.resize(650,300);pump(w,.5)
    assert len({pos(button,p.actions)[1] for button in buttons})==1
    assert len({button.get_allocated_height() for button in buttons})==1
    assert buttons[0].get_allocated_height()<=narrow_height
    p.actions.reparent(p.editor);fixture.destroy()
    p.list.select_all();pump(w)
    assert p.reset.get_label().startswith('Reset current targets')
    assert p.reset._label(p.reset).get_line_wrap()
finally:w.destroy()
''')
