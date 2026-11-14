"""Provider button filtering and full custom-message disclosure in real GTK."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK/X11')


def test_recipient_heading_filters_badges_and_independent_selection():
    run_gui(r'''
c=replace(b,id='c',title='Claude selected',provider='claude')
m=replace(b,id='m',title='Muse selected',provider='muse')
config=AppConfig.load();config.desktop_targets += [c.to_dict(),m.to_dict()];config.save()
target_ui.discover_targets=lambda:Inventory([a,b,c,m])
target_ui.fetch_claude_quota=lambda:Quota('Claude',RateWindow(20,300,9999999999),None,False)
target_ui.fetch_muse_quota=lambda _:Quota('Muse',RateWindow(30,300,9999999999),None,False)
w=make();p=w.recipient_panel
try:
    assert p.heading.get_parent().get_parent() is p.heading_row
    assert p.provider_filter.get_parent().get_parent() is p.heading_row
    assert set(p.provider_filter.buttons)=={'all','codex','claude','muse','gemini','antigravity','opencode'}
    assert [button.caption.get_text() for button in p.provider_filter.buttons.values()]==['All (4)','Codex (2)','Claude (1)','Muse (1)','Gemini (0)','Antigravity (0)','OpenCode (0)']
    assert [column.get_title() for column in w.table.get_columns()[:2]]==['Provider','Project']
    stored=tray_control.watch_settings(AppConfig.load())
    main_filter=w.provider_filter.get_active_id()
    click(p.provider_filter.buttons['claude'],w)
    assert [row.key for row in p._visible_rows()]==[c.key]
    assert len(w.selected)==4 and tray_control.watch_settings(AppConfig.load())==stored
    assert w.provider_filter.get_active_id()==main_filter
    row=p.rows[c.key]
    assert row.provider.get_text()=='Claude'
    assert pos(row.title,w)[0]<pos(row.provider,w)[0]<pos(row.indicator,w)[0]
    assert abs(pos(row.provider,w)[1]-pos(row.indicator,w)[1])<6
    w.set_accept_focus(True);w.set_focus_on_map(True);pump(w)
    subprocess.run(['xdotool','windowactivate','--sync',str(w.get_window().get_xid())],check=True)
    pump(w);p.provider_filter.buttons['claude'].grab_focus();pump(w)
    subprocess.run(['xdotool','key','Right'],check=True);pump(w)
    assert p.provider_filter.get_active_id()=='muse' and p.selected_key==m.key
    click(w.provider_filter.buttons['codex'],w)
    assert len(w.filtered)==2 and p.provider_filter.get_active_id()=='muse'
    assert not w.table_layout.columns['provider'][0].get_visible()
    assert 'Filter visible chats only' not in w.provider_filter.buttons['codex'].get_tooltip_text()
    click(w.provider_filter.buttons['all'],w)
    assert w.table_layout.columns['provider'][0].get_visible()
    click(p.provider_filter.buttons['all'],w)
    assert len(p._visible_rows())==4 and len(w.selected)==4
    w.update_recipient(replace(c,send_prompt=False,send_goal=False));pump(w)
    assert [button.caption.get_text() for button in p.provider_filter.buttons.values()]==['All (4)','Codex (2)','Claude (1)','Muse (1)','Gemini (0)','Antigravity (0)','OpenCode (0)']
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820
        assert p.provider_filter.get_allocated_width()+pos(p.provider_filter,p)[0]<=p.get_allocated_width()
        assert pos(w.provider_filter,w.main_split)[1]>=0  # Controls must not be clipped above the pane.
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-07_provider-list-buttons-'+('dark' if dark else 'light')+'.png')
finally:w.destroy()
''')


def test_custom_message_expands_preserves_newlines_and_shortens_without_sending():
    run_gui(r'''
long='First 🌻 line\n'+'\n'.join('Full custom message line '+str(n) for n in range(18))
b=replace(b,custom_prompt=long)
config=AppConfig.load();config.desktop_targets=[a.to_dict(),b.to_dict()];config.save()
target_ui.discover_targets=lambda:Inventory([a,b])
w=make();p=w.recipient_panel
try:
    p.select_recipient(b.key);pump(w);row=p.rows[b.key]
    assert row.preview_toggle.get_visible() and not row.preview.get_visible()
    assert not row.preview_toggle.get_label() and row.preview_toggle.get_allocated_width()<=32
    assert "Expand" in row.preview_toggle.get_accessible().get_name()
    assert '<b>Custom</b> message' in row.allowance.get_label()
    stored=AppConfig.load().desktop_targets
    click(row.preview_toggle,w)
    assert row.expanded and row.preview.get_visible()
    assert row.preview.get_text()==long and row.preview_toggle.get_image().get_icon_name()[0]=='pan-up-symbolic'
    assert '<b>Custom</b> message' in row.allowance.get_label()
    assert 'First 🌻 line' not in row.allowance.get_text()
    assert 'Full custom message line' not in row.allowance.get_text()
    w._summary();pump(w)
    assert row.expanded and row.preview.get_text()==long
    assert 'First 🌻 line' not in row.allowance.get_text()
    w.resize(1120,820);pump(w)
    assert row.preview.get_text()==long and 'First 🌻 line' not in row.allowance.get_text()
    w.set_accept_focus(True);w.set_focus_on_map(True);pump(w)
    subprocess.run(['xdotool','windowactivate','--sync',str(w.get_window().get_xid())],check=True)
    pump(w);row.preview_toggle.grab_focus();pump(w)
    subprocess.run(['xdotool','key','space'],check=True);pump(w)
    assert not row.expanded and not row.preview.get_visible() and row.preview_toggle.get_image().get_icon_name()[0]=='pan-down-symbolic'
    assert 'First 🌻 line' in row.allowance.get_text()
    assert '<b>Custom</b> message' in row.allowance.get_label()
    assert AppConfig.load().desktop_targets==stored and 'start-watch' not in commands
    p.message_buffer.set_text('tiny');pump(w)
    assert not row.preview_toggle.get_visible() and not row.preview.get_visible()
    p.provider_filter.set_active_id('muse');pump(w)
    assert p.provider_filter.get_active_id()=='all' and not p.empty_label.get_visible()
    assert not p.provider_filter.buttons['muse'].get_parent().get_visible()
    assert len(w.selected)==2
finally:w.destroy()
''')
