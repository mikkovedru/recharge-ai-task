"""Compact recipient allowances, custom messages and reset controls."""
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
    assert p.reset.get_label()=="Reset current recipient's counts"
    assert p.reset_all.get_label()=='Reset counts for all'
    assert [child.get_child() for child in p.reset.get_parent().get_parent().get_children()] == [w.send_button, p.reset_all, p.reset]
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
