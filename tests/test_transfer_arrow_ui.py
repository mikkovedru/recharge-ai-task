"""Native arrow glyph size, allocation and transfer interactions."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_transfer_chevron_grows_inside_the_same_button():
    run_gui(r'''
from recharge_ai_task.transfer_arrow import TransferArrow
w=make();p=w.recipient_panel
try:
    for theme,dark in (('Mint-X',False),('Adwaita',False),('Adwaita',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1440,980);pump(w)
        for icon in ('go-next-symbolic','go-previous-symbolic'):
            old=Gtk.Image.new_from_icon_name(icon,Gtk.IconSize.BUTTON)
            new=TransferArrow(icon)
            p.transfer.set_image(old);pump(w)
            reference=(p.transfer.get_allocated_width(),p.transfer.get_allocated_height())
            def bounds(widget,draw=None):
                surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,widget.get_allocated_width(),widget.get_allocated_height())
                (draw or widget.draw)(cairo.Context(surface));surface.flush();data=surface.get_data();points=[]
                for y in range(surface.get_height()):
                    for x in range(surface.get_width()):
                        if data[y*surface.get_stride()+x*4+3]>40:points.append((x,y))
                return max(x for x,y in points)-min(x for x,y in points)+1,max(y for x,y in points)-min(y for x,y in points)+1
            old_bounds=bounds(old)
            p.transfer.set_image(new);pump(w)
            assert (p.transfer.get_allocated_width(),p.transfer.get_allocated_height())==reference
            new_bounds=bounds(p.transfer,p.transfer.draw_glyph)
            assert new_bounds[1]>=old_bounds[1]*1.3,(theme,old_bounds,new_bounds)
            assert new_bounds[0]>old_bounds[0],(theme,old_bounds,new_bounds)
            assert new_bounds[1]<=26 and new_bounds[0]<=16,(theme,new_bounds)
    path=next(r.path for r in w.filtered if r[17]==b.key)
    w.table.set_cursor(path,w.title_column,False);pump(w)
    click(p.transfer,w)
    assert b.key not in w.selected
    p.transfer.grab_focus();pump(w)
    subprocess.run(['xdotool','key','space'],check=True);pump(w)
    assert b.key in w.selected and not any(w.selected[b.key].signal_actions())
finally:w.destroy()
''')
