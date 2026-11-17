"""Rendered contrast for both themes, including unfocused and passive controls."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')


def test_theme_text_passive_rows_and_disclosure_contrast():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    w.update_recipient(replace(w.selected[a.key],send_goal=False,send_prompt=False))
    w.update_recipient(replace(w.selected[b.key],custom_prompt='Long message <&> '*80))
    p.select_recipient(b.key)
    def lum(c):
        return sum(k*(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4) for k,v in zip((.2126,.7152,.0722),(c.red,c.green,c.blue)))
    def contrast(fg,bg):
        lo,hi=sorted((lum(fg),lum(bg)));return (hi+.05)/(lo+.05)
    minimum=100
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w)
        for width,height in ((1440,980),(1120,820)):
            w.resize(width,height);pump(w);p.select_recipient(b.key);pump(w)
            assert w.send_button.get_label()=='Send now\n(0 goals, 1 messages)'
            label=w.send_button._label(w.send_button)
            assert label.get_layout().get_line_count()>=2
            assert w.get_size().width<=width and w.get_size().height<=height
            base=p.get_style_context().lookup_color('theme_base_color')[1]
            bg=p.get_style_context().lookup_color('theme_bg_color')[1]
            # Include normal and inactive-window state to catch Adwaita dimming.
            for state in (Gtk.StateFlags.NORMAL,Gtk.StateFlags.BACKDROP):
                for widget in (w.summary,w.inventory_status,p.heading,w.selection_help,w.send_button.get_child()):
                    if not isinstance(widget,Gtk.Label):continue
                    fg=widget.get_style_context().get_color(state)
                    ratio=contrast(fg,bg);minimum=min(minimum,ratio)
                    assert ratio>=4.5,(dark,widget.get_text(),fg.to_string(),bg.to_string(),ratio)
                passive=p.rows[a.key].title
                fg=passive.get_style_context().get_color(state)
                passive_bg=p.rows[a.key].get_style_context().get_background_color(state)
                assert passive_bg.alpha>.99
                minimum=min(minimum,contrast(fg,passive_bg))
                assert contrast(fg,passive_bg)>=4.5,(dark,fg.to_string(),passive_bg.to_string())
            border=w.send_button.get_style_context().get_border_color(Gtk.StateFlags.NORMAL)
            border=Gdk.RGBA(*(getattr(border,k)*border.alpha+getattr(bg,k)*(1-border.alpha) for k in ('red','green','blue')),1)
            assert contrast(border,bg)>=3,(dark,border.to_string(),bg.to_string())
            row=p.rows[b.key]
            assert row.preview_toggle.get_visible()
            for flags in (Gtk.StateFlags.NORMAL,Gtk.StateFlags.PRELIGHT,Gtk.StateFlags.BACKDROP):
                icon=row.preview_toggle.get_image().get_style_context().get_color(flags)
                button_bg=row.preview_toggle.get_style_context().get_background_color(flags)
                ratio=contrast(icon,button_bg);minimum=min(minimum,ratio)
                assert button_bg.alpha>.99 and ratio>=4.5,(dark,flags,icon.to_string(),button_bg.to_string(),ratio)
            row.preview_toggle.grab_focus();row.preview_toggle.clicked();pump(w)
            assert row.preview.get_visible() and row.expanded
            row.preview_toggle.clicked();pump(w)
            assert not row.preview.get_visible() and not row.expanded
            # Selected main-list status colors remain legible on the row highlight.
            selected_bg=w.table.get_style_context().get_background_color(Gtk.StateFlags.SELECTED)
            for value in status_colors(w.table).values():
                minimum=min(minimum,contrast(rgba(value),selected_bg))
                assert contrast(rgba(value),selected_bg)>=4.5,(dark,value,selected_bg.to_string())
        p.split.set_position(300);pump(w);p.select_recipient(b.key);pump(w)
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-08_readability-'+('dark' if dark else 'light')+'.png')
        config=AppConfig.load();config.color_theme="dark" if dark else "light";config.save()
        dialog=settings_ui.SettingsDialog(w);pump(w)
        for widget in (dialog.autostart.get_child(),dialog.grace,dialog.poll):
            fg=widget.get_style_context().get_color(widget.get_state_flags())
            minimum=min(minimum,contrast(fg,bg))
            assert contrast(fg,bg)>=4.5,(dark,fg.to_string(),bg.to_string())
        dialog.destroy();pump(w)
    (config_dir()/'contrast.txt').write_text(str(minimum))
    open('/tmp/2026-11-08_contrast.txt','w').write(str(minimum))
finally:w.destroy()
''')
