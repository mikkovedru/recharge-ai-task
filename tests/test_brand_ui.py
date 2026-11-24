import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_logo_version_repository_and_copy_menu():
    result = subprocess.run([sys.executable, "-c", '''
from types import SimpleNamespace
import gi
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from recharge_ai_task import __version__
from recharge_ai_task.brand_ui import ProjectLogo, Gtk, Gdk, REPOSITORY_URL
window = Gtk.Window()
logo = ProjectLogo(Gtk.Image())
window.add(logo)
assert logo.get_tooltip_text().splitlines()[0] == f"Recharge AI-task {__version__}"
assert logo.menu.get_children()[0].get_label() == f"Copy GitHub repository link ({REPOSITORY_URL})"
calls = []
Gtk.show_uri_on_window = lambda *args: calls.append(args)
assert logo.get_can_focus()
logo.clicked()
assert calls == [(window,REPOSITORY_URL,Gdk.CURRENT_TIME)]
logo.menu.get_children()[0].activate()
assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() == REPOSITORY_URL
assert not logo._press(logo, SimpleNamespace(button=2))
window.destroy()
'''], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')
@pytest.mark.parametrize('scale', ['1', '2'])
def test_logo_matches_settings_width_with_native_pixel_scaling(scale):
    result = subprocess.run([sys.executable, '-c', '''
import time,gi,cairo
gi.require_version('Gtk','3.0')
gi.require_version('Gdk','3.0')
from recharge_ai_task.brand_ui import ProjectLogo
from recharge_ai_task.branding import asset_path
from gi.repository import Gtk,Gdk,GdkPixbuf
window=Gtk.Window();window.set_accept_focus(False);window.set_focus_on_map(False)
window.set_default_size(420,320)
row=Gtk.Box(spacing=8,margin=10);row.pack_start(Gtk.Label(label='Dashboard'),True,True,0)
column=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6,valign=Gtk.Align.START)
settings=Gtk.Button(label='Settings…');settings.set_image(Gtk.Image.new_from_icon_name('emblem-system-symbolic',Gtk.IconSize.BUTTON));settings.set_always_show_image(True)
artwork=GdkPixbuf.Pixbuf.new_from_file(str(asset_path('logo-lockup.png')))
image=Gtk.Image.new_from_pixbuf(artwork.scale_simple(64,64,GdkPixbuf.InterpType.HYPER))
logo=ProjectLogo(image);logo.match_width(settings,artwork)
column.pack_start(logo,False,False,0);column.pack_start(settings,False,False,0);row.pack_end(column,False,False,0)
window.add(row);window.show_all()
def pump():
    end=time.monotonic()+.3
    while time.monotonic()<end:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
pump()
try:
    for width in (420,340):
        window.resize(width,320);pump()
        assert artwork.get_width()==512
        assert logo.get_allocated_width()==settings.get_allocated_width()==image.get_allocated_width(),(logo.get_allocated_width(),settings.get_allocated_width(),image.get_allocated_width(),logo.scaled_size)
        assert logo.scaled_size==(settings.get_allocated_width(),window.get_scale_factor())
        assert image.get_allocated_height()==image.get_allocated_width(),(image.get_allocated_width(),image.get_allocated_height(),logo.scaled_size)
        assert image.get_storage_type()==Gtk.ImageType.SURFACE
        assert settings.translate_coordinates(column,0,0)[1]>=logo.get_allocated_height()
    Gdk.pixbuf_get_from_window(window.get_window(),0,0,*window.get_size()).savev('/tmp/2026-11-07_scaled-logo-'+str(window.get_scale_factor())+'.png','png',[],[])
finally:window.destroy()
'''], env=dict(os.environ, GDK_SCALE=scale), capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'CRITICAL' not in result.stderr, result.stderr
