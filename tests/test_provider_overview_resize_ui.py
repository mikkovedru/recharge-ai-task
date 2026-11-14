"""Native overview divider dragging, focus navigation and persistence."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_overview_divider_drag_keyboard_small_window_and_persistence():
    run_gui(r'''
w=make()
try:
    pane=w.overview_split
    assert pane.get_orientation()==Gtk.Orientation.VERTICAL
    assert w.window_layout.panes['provider_overview'][0] is pane
    w.resize(1440,980);pump(w)
    w.set_accept_focus(True);pump(w)
    xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True);pump(w)
    before=pane.get_position();width=w.quota_card.get_allocated_width();height=w.quota_card.get_allocated_height()
    x,y=pos(pane,w);x+=pane.get_allocated_width()//2;y+=before+3
    subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y),'mousedown','1'],check=True);pump(w)
    subprocess.run(['xdotool','mousemove','--window',xid,str(x+70),str(y+85)],check=True);pump(w)
    subprocess.run(['xdotool','mouseup','1'],check=True);pump(w)
    assert pane.get_position()>=before+75,(before,pane.get_position())
    assert w.quota_card.get_allocated_height()>=height+75
    assert w.quota_card.get_allocated_width()==width  # Horizontal motion cannot resize this region.
    # Native Paned handle supports its standard F8 keyboard interaction.
    pane.grab_focus();pump(w)
    before=pane.get_position()
    subprocess.run(['xdotool','key','Down','Down','Return'],check=True);pump(w)
    assert pane.get_position()>before,(before,pane.get_position(),w.get_focus())
    saved=pane.get_position();w.window_layout.close();w.destroy();w=make()
    deadline=time.monotonic()+2
    while not w.window_layout.ready and time.monotonic()<deadline:pump(w,.1)
    assert abs(w.overview_split.get_position()-saved)<=1,(saved,w.overview_split.get_position())
    # A tall saved overview yields enough space to the rest of a smaller window.
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820,w.get_size()
        assert w.status.get_allocated_height()>=36 and w.recipient_panel.list_scroller.get_allocated_height()>=60
        assert w.recipient_panel.split.get_position()>=60
        for page in range(w.monitor_tabs.get_n_pages()):
            w.monitor_tabs.set_current_page(page);pump(w,.04)
            assert w.monitor_tabs.get_allocated_height()<=w.quota_card.get_allocated_height()

finally:w.destroy()
''')


def test_all_workspace_dividers_share_rendered_native_style():
    run_gui(r'''
w=make()
try:
    w.set_accept_focus(True);pump(w)
    xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True);pump(w)
    panes=(w.overview_split,w.main_split,w.recipient_panel.split,w.workspace_split)
    for pane in panes:
        assert pane.get_style_context().has_class('workspace-divider')
        assert pane.get_wide_handle()
    def handle(pane):
        x,y=pos(pane,w)
        vertical=pane.get_orientation()==Gtk.Orientation.VERTICAL
        win=pane.get_handle_window()
        thickness=win.get_height() if vertical else win.get_width()
        if vertical:return x+pane.get_allocated_width()//2,y+pane.get_position()+thickness//2,thickness,vertical
        return x+pane.get_position()+thickness//2,y+pane.get_allocated_height()//2,thickness,vertical
    def sample(pane,hover):
        x,y,thickness,vertical=handle(pane)
        # Move out first so only the intended handle receives the prelight state.
        subprocess.run(['xdotool','mousemove','--window',xid,'5','5'],check=True);pump(w,.1)
        if hover == 'focus':
            pane.grab_focus();pump(w,.1)
        else:
            w.search.grab_focus();pump(w,.05)
        if hover is True:
            subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y)],check=True);pump(w,.1)
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface));surface.flush()
        if Gtk.Settings.get_default().get_property('gtk-theme-name')=='Mint-X':
            crop=cairo.ImageSurface(cairo.FORMAT_ARGB32,41,41);ctx=cairo.Context(crop);ctx.set_source_surface(surface,20-x,20-y);ctx.paint()
            crop.write_to_png('/tmp/2026-11-14_mint-divider-'+str(panes.index(pane))+'-'+str(dark)+'-'+str(hover)+'.png')
        data=surface.get_data();stride=surface.get_stride()
        # Normalize orientation: rows run across the handle thickness, columns along it.
        return tuple(bytes(data[(y+(cross if vertical else along))*stride+(x+(along if vertical else cross))*4:(y+(cross if vertical else along))*stride+(x+(along if vertical else cross))*4+3])
                     for cross in range(-(thickness//2),thickness-thickness//2) for along in range(-14,15))
    def difference(a,b):return sum(abs(x-y) for p,q in zip(a,b) for x,y in zip(p,q))/(len(a)*3)
    def contrast(row):return max(p[0] for p in row)-min(p[0] for p in row)
    for theme,dark in (('Adwaita',False),('Adwaita',True),('Mint-X',False),('Mint-X',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for size in ((1440,980),(1120,820)):
            w.resize(*size);pump(w,.4)
            dimensions=[handle(p)[2] for p in panes]
            assert len(set(dimensions))==1,(theme,dark,size,dimensions)
            for hover in (False,True,'focus'):
                rendered=[sample(p,hover) for p in panes]
                # Mint-X paints a two-pixel theme image three pixels before the
                # handle-window center. Odd/even pane lengths can interpolate its
                # centered image differently, so compare the grip row with a small
                # average tolerance rather than the adjacent widgets' backgrounds.
                if theme=='Mint-X':
                    row=dimensions[0]//2-3
                    grips=[value[row*29:(row+1)*29] for value in rendered]
                    assert all(contrast(value)>20 for value in grips),(theme,dark,size,hover)
                    assert all(difference(value,grips[0])<16 for value in grips[1:]),(theme,dark,size,hover,[difference(value,grips[0]) for value in grips])
                else:
                    assert all(value==rendered[0] for value in rendered[1:]),(theme,dark,size,hover,dimensions)
    # Removing only the grip must fail the texture check, even if the handle
    # dimensions and transparent background remain unchanged.
    provider=Gtk.CssProvider()
    provider.load_from_data(b'paned.divider-regression-probe > separator.wide { background-image: none; }')
    Gtk.StyleContext.add_provider_for_screen(w.get_screen(),provider,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    w.overview_split.get_style_context().add_class('divider-regression-probe');pump(w)
    missing=sample(w.overview_split,False);reference=sample(w.main_split,False)
    row=handle(w.overview_split)[2]//2-3
    assert contrast(reference[row*29:(row+1)*29])>20
    assert contrast(missing[row*29:(row+1)*29])<=20
    Gtk.StyleContext.remove_provider_for_screen(w.get_screen(),provider)
finally:w.destroy()
''')
