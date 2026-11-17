"""Rendered target state borders, compact passive rows and larger arrow glyphs."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_target_health_borders_selection_and_passive_height():
    run_gui(r'''
from gi.repository import Pango
from recharge_ai_task.status_display import target_border_colors, TARGET_BORDER_BACKING
w=make();p=w.recipient_panel
try:
    running=replace(w.selected[a.key],goal_status='Active',task_status='Running')
    passive=replace(w.selected[b.key],send_prompt=False,send_goal=False,last_active_at=1234567890)
    limited=replace(a,id='limited',title='Limit reached',goal_limit=0)
    paused=replace(a,id='paused',title='Paused Goal',goal_status='Paused')
    for target in (running,passive,limited,paused):w.update_recipient(target)
    w._apply_inventory(Inventory([running,passive,limited,paused]));pump(w)
    def padded_first():
        first=next(column for column in w.table.get_columns() if column.get_visible())
        for column in w.table.get_columns():
            assert all(cell.get_property('xpad')==(10 if column is first else 2) for cell in column.get_cells())
    padded_first()
    def pixel(surface,x,y):
        offset=y*surface.get_stride()+x*4
        blue,green,red,alpha=bytes(surface.get_data()[offset:offset+4])
        return Gdk.RGBA(red/255,green/255,blue/255,alpha/255)
    for theme,dark in (('Mint-X',False),('Adwaita',False),('Adwaita',True)):
        Gtk.Settings.get_default().set_property('gtk-theme-name',theme)
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        for width,height in ((1920,1080),(1120,820)):
            w.resize(width,height);pump(w)
            for watch in (False,True):
                runtime.update(desktop_watch=watch,watch_settings=tray_control.watch_settings(AppConfig.load()))
                w.runtime=dict(runtime);w._summary();pump(w)
                p.select_recipient(b.key);pump(w)
                assert p.heading.get_text()=='Targets & actions'
                expected={a.key:'success' if watch else 'warning',b.key:'error',limited.key:'error',paused.key:'error'}
                for key,level in expected.items():
                    row=p.rows[key]
                    assert row.health_level==level,(key,row.health_level)
                    assert row.get_style_context().get_border(row.get_state_flags()).left==4
                w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface));surface.flush();surface.write_to_png('/tmp/2026-11-17_target-state-debug.png')
                for key,level in expected.items():
                    row=p.rows[key];x,y=pos(row,w)
                    scroll_y=pos(p.list_scroller,w)[1]
                    middle=y+row.get_allocated_height()//2
                    if scroll_y<middle<scroll_y+p.list_scroller.get_allocated_height():
                        assert close_color(pixel(surface,x+2,middle),rgba(target_border_colors(w)[level])),(theme,dark,key,level)
                        assert close_color(pixel(surface,x+5,middle),rgba(TARGET_BORDER_BACKING)),(theme,key,'backing')
                        for dy in (0,1,2,row.get_allocated_height()-3,row.get_allocated_height()-2,row.get_allocated_height()-1):
                            # Neither the colored stripe nor its keylines may bridge rows.
                            assert not close_color(pixel(surface,x+2,y+dy),rgba(target_border_colors(w)[level])),(theme,key,'target gap',dy)
                            assert not close_color(pixel(surface,x+5,y+dy),rgba(TARGET_BORDER_BACKING)),(theme,key,'keyline gap',dy)
                    table_row=next(r for r in w.filtered if r[17]==key)
                    bounds=w.table.get_background_area(table_row.path,None)
                    tx,ty=w.table.convert_bin_window_to_widget_coords(0,bounds.y+bounds.height//2)
                    header=w.table.convert_bin_window_to_widget_coords(0,0)[1]
                    if header<=ty<w.table.get_allocated_height():
                        tx,ty=w.table.translate_coordinates(w,2,ty)
                        assert close_color(pixel(surface,tx,ty),rgba(target_border_colors(w)[level])),(theme,dark,key,'main')
                        for dy in (0,1,bounds.height-2,bounds.height-1):
                            gx,gy=w.table.convert_bin_window_to_widget_coords(2,bounds.y+dy)
                            if header<=gy<w.table.get_allocated_height():
                                gx,gy=w.table.translate_coordinates(w,gx,gy)
                                assert not close_color(pixel(surface,gx,gy),rgba(target_border_colors(w)[level])),(theme,key,'main gap',dy)
                x,y=pos(w.recipient_frame,w)
                frame_pixel=pixel(surface,x,y+w.recipient_frame.get_allocated_height()//2)
                assert close_color(frame_pixel,rgba(status_colors(w)['error'])) is (not watch)
                def luminance(c):
                    return sum(weight*(value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4) for weight,value in zip((.2126,.7152,.0722),(c.red,c.green,c.blue)))
                for level in ('success','warning','error'):
                    base=rgba(TARGET_BORDER_BACKING)
                    lo,hi=sorted((luminance(rgba(target_border_colors(w)[level])),luminance(base)))
                    assert (hi+.05)/(lo+.05)>=3,(theme,level)
                selected=p.rows[b.key];sx,sy=pos(selected,w);normal=p.rows[a.key];nx,ny=pos(normal,w)
                def row_background(row):
                    image=cairo.ImageSurface(cairo.FORMAT_ARGB32,row.get_allocated_width(),row.get_allocated_height())
                    row.draw(cairo.Context(image));image.flush()
                    return pixel(image,30,row.get_allocated_height()-5)
                assert not close_color(row_background(selected),row_background(normal))
                foreground=selected.title.get_style_context().get_color(selected.title.get_state_flags())
                background=selected.get_style_context().get_background_color(selected.get_state_flags())
                def light(c):
                    return sum(weight*(value/12.92 if value<=.04045 else ((value+.055)/1.055)**2.4) for weight,value in zip((.2126,.7152,.0722),(c.red,c.green,c.blue)))
                lo,hi=sorted((light(foreground),light(background)))
                assert (hi+.05)/(lo+.05)>=4.5,(theme,foreground.to_string(),background.to_string())
                column=w.title_column;cell=column.get_cells()[0]
                iterator=next(r.iter for r in w.filtered if r[17]==b.key)
                column.cell_set_cell_data(w.filtered,iterator,False,False)
                assert cell.get_property('text')==b.title and cell.get_property('style')==Pango.Style.NORMAL
                assert ', ' in next(r for r in w.store if r[17]==b.key)[14]
                surface.write_to_png('/tmp/2026-11-17_target-states-%s-%s-%s-%s.png'%(theme,dark,width,watch))
            # Equivalent single-line content must occupy the same row height.
            before=p.rows[b.key].get_allocated_height()
            w.update_recipient(replace(w.selected[b.key],send_prompt=True));pump(w)
            after=p.rows[b.key].get_allocated_height()
            assert before==after,(theme,width,before,after)
            w.update_recipient(replace(w.selected[b.key],send_prompt=False));pump(w)
            assert p.rows[b.key].get_allocated_height()==before
    w.provider_filter.set_active_id('codex');pump(w);padded_first()
    w.table.move_column_after(w.title_column,None);pump(w);padded_first()
    # Horizontal scrolling must move the stripe with the leading padded cell.
    # A viewport-fixed stripe overlays its first glyphs after a small scroll.
    for offset in (0,2,4,8,0):
        w.table.get_hadjustment().set_value(offset);pump(w)
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface));surface.flush()
        row=next(r for r in w.filtered if r[17]==a.key)
        bounds=w.table.get_background_area(row.path,None)
        sx,sy=w.table.convert_bin_window_to_widget_coords(0,bounds.y+bounds.height//2)
        x,y=w.table.translate_coordinates(w,max(0,sx+6),sy)
        assert not close_color(pixel(surface,x,y),rgba(target_border_colors(w)[p.rows[a.key].health_level])),('stripe overlapping cells',offset)
        assert not close_color(pixel(surface,x,y),rgba(TARGET_BORDER_BACKING)),('keyline overlapping cells',offset)

finally:w.destroy()
''')

