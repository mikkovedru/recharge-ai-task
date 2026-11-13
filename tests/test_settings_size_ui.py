"""Content-sized Settings defaults, screen bounds and saved manual resizing."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_settings_default_fits_content_or_screen_and_keeps_user_resize():
    run_gui(r'''
w=make()
try:
    config=AppConfig.load();config.ui_layout={'settings':{'size':[620,620],'layout_version':1}};config.save()
    d=settings_ui.SettingsDialog(w);pump(d,.5)
    area=d.get_screen().get_monitor_workarea(d.get_screen().get_primary_monitor())
    width,height=d.get_size()
    assert width>620 and height>620,(width,height)
    assert width<=area.width and height<=area.height-30,(width,height,area)
    adj=d.scroller.get_vadjustment()
    assert adj.get_upper()<=adj.get_page_size()+2 or height>=area.height-55,(height,area.height,adj.get_upper(),adj.get_page_size())
    d.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*d.get_size());d.draw(cairo.Context(surface))
    surface.write_to_png('/tmp/2026-11-14_settings-default.png')
    d.resize(760,600);pump(d,.5)
    size=list(d.get_size());assert size==[760,600],size
    d.destroy();pump(w)
    d=settings_ui.SettingsDialog(w);pump(d,.5)
    assert list(d.get_size())==size,(d.get_size(),size)
    assert d.scroller.get_vadjustment().get_upper()>d.scroller.get_vadjustment().get_page_size()
    # Scrolling exposes the final content; action buttons always remain visible.
    adj=d.scroller.get_vadjustment();adj.set_value(adj.get_upper());pump(d)
    assert adj.get_value()>0 and d.get_widget_for_response(Gtk.ResponseType.OK).get_mapped()
    d.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*d.get_size());d.draw(cairo.Context(surface))
    surface.write_to_png('/tmp/2026-11-14_settings-resized.png')
    d.destroy()
finally:w.destroy()
''')
