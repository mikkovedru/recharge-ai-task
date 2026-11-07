"""Real provider tabs, scoped notices, status icons, mouse/keyboard and resizing."""
import os
import pytest
from test_monitoring_status_ui import run_gui

pytestmark=pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS')!='1',reason='Requires GTK/X11')


def test_provider_notices_tabs_schedules_counts_icons_and_recovery():
    run_gui(r'''
from dataclasses import asdict
from gi.repository import Gdk
c=replace(b,id='c',provider='claude',title='Claude selected')
m=replace(b,id='m',provider='muse',title='Muse selected')
config=AppConfig.load();config.desktop_targets += [c.to_dict(),m.to_dict()];config.save()
error='Claude usage requires a Claude Code subscription login. Run claude auth login on this machine.'
muse_error='Cannot read Muse allowance. Run muse login, then muse usage --json. Muse Code 1.4.13+ is required.'
target_ui.discover_targets=lambda:Inventory([a,b,c,m],providers=('codex','claude','muse'),warnings=['Codex daemon fallback'],provider_warnings={'codex':['Codex daemon fallback']})
target_ui.fetch_claude_quota=lambda:(_ for _ in ()).throw(RuntimeError(error))
target_ui.fetch_muse_quota=lambda _:(_ for _ in ()).throw(RuntimeError(muse_error))
w=make()
try:
    assert w.monitor_tabs.get_n_pages()==4
    assert error not in w.status.text() and muse_error not in w.status.text()
    assert 'Codex daemon fallback' not in w.status.text()
    assert error in w.monitor_tabs.pages['claude'].get_text()
    assert muse_error in w.monitor_tabs.pages['muse'].get_text()
    assert error not in w.monitor_tabs.pages['codex'].get_text()
    assert w.provider_filter.buttons['claude'].provider_state=='error'
    assert w.provider_filter.buttons['codex'].provider_state=='warning'
    question=w.provider_filter.buttons['codex'].notice
    exclamation=w.provider_filter.buttons['claude'].notice
    assert question.icon.get_icon_name()[0]=='dialog-question-symbolic'
    assert exclamation.icon.get_icon_name()[0]=='dialog-warning-symbolic'
    for notice in (question,exclamation):
        assert notice.get_visible() and isinstance(notice.icon,Gtk.Image)
        assert [notice.get_children()[i].get_text() for i in (0,2)]==['(',')']
    assert close_color(question.icon.get_style_context().get_color(question.icon.get_state_flags()),rgba(status_colors(w)['warning']))
    assert close_color(exclamation.icon.get_style_context().get_color(exclamation.icon.get_state_flags()),rgba(status_colors(w)['error']))
    assert w.technical_toggle.get_label()=='Show technical\ncolumns'
    for _ in range(3):w.poll_runtime();pump(w)
    assert error not in w.status.text() and muse_error not in w.status.text()
    # Real tab click; provider names are retained when an error changes its icon.
    click(w.monitor_tabs.tab_labels['claude'],w)
    assert w.monitor_tabs.get_current_page()==2
    assert w.monitor_tabs.pages['claude'].get_mapped()
    assert not w.monitor_tabs.pages['claude'].get_selection_bounds()[0]
    header=w.monitor_tabs.tab_headers['claude']
    assert error in header.get_tooltip_text() and not w.monitor_tabs.get_tooltip_text()
    assert not w.monitor_tabs.tab_labels['claude'].get_tooltip_text()
    assert not w.monitor_tabs.tab_notices['claude'].get_tooltip_text()
    assert not w.monitor_tabs.tab_notices['claude'].icon.get_tooltip_text()
    now=time.time()
    cq=Quota('Claude Pro fixture',RateWindow(51,300,now+500),None,False)
    mq=Quota('Muse fixture',RateWindow(8,300,now+900),None,False)
    progress={
      'codex':dict(phase='grace_period',checked_at=now,updated_at=now,next_check_at=now+15,recovery_at=now+15,pending_cycle=True,pending_recipients=2,pending_messages=1,pending_goals=1,quota_snapshot=asdict(Quota('Codex Plus',RateWindow(20,300,now+500),None,False))),
      'claude':dict(phase='waiting_quota',checked_at=now,updated_at=now,next_check_at=now+25,expected_reset_at=now+500,pending_cycle=True,pending_recipients=1,pending_messages=1,pending_goals=0,quota_snapshot=asdict(cq)),
      'muse':dict(phase='monitoring',checked_at=now,updated_at=now,next_check_at=now+40,selected_recipients=1,selected_messages=1,selected_goals=0,quota_snapshot=asdict(mq))}
    runtime.update(desktop_watch=True,shared_quota=True,watch_progress={'providers':progress},watch_settings=tray_control.watch_settings(AppConfig.load()))
    w.poll_runtime();pump(w)
    assert error not in w.monitor_tabs.pages['claude'].get_text()
    assert 'Claude Pro fixture' in w.monitor_tabs.pages['claude'].get_text()
    assert 'Forecast:' in w.monitor_tabs.pages['claude'].get_text()
    assert 'Send:' in w.monitor_tabs.pages['codex'].get_text()
    assert 'Send:' not in w.monitor_tabs.pages['muse'].get_text()
    assert '1 selected recipient' in w.monitor_tabs.pages['claude'].get_text()
    assert 'Used:' in w.monitor_tabs.pages['claude'].get_text()
    assert w.provider_filter.buttons['claude'].provider_state=='enabled'
    assert not w.provider_filter.buttons['claude'].status_image.get_visible()
    assert not w.provider_filter.buttons['claude'].notice.get_visible()
    assert not w.monitor_tabs.tab_notices['claude'].get_visible()
    w.set_accept_focus(True);w.set_focus_on_map(True);pump(w)
    subprocess.run(['xdotool','windowactivate','--sync',str(w.get_window().get_xid())],check=True)
    pump(w);w.monitor_tabs.grab_focus();pump(w)
    subprocess.run(['xdotool','key','ctrl+Page_Down'],check=True);pump(w)
    assert w.monitor_tabs.get_current_page()==3
    assert not w.monitor_tabs.pages['muse'].get_selection_bounds()[0]
    pump(w,1.2)
    assert not w.monitor_tabs.pages['muse'].get_selection_bounds()[0]
    click(w.monitor_tabs.get_tab_label(w.monitor_tabs.get_nth_page(0)),w)
    assert not w.quota_label.get_selection_bounds()[0]
    pump(w,1.2)
    assert not w.quota_label.get_selection_bounds()[0]
    # Deliberate selections remain available for copying between updates.
    w.quota_label.select_region(0,10);pump(w)
    assert w.quota_label.get_selection_bounds()[0]
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w.resize(1120,820);pump(w)
        assert w.get_size().width<=1120 and w.get_size().height<=820,(w.get_size(),w.main_split.get_preferred_height(),w.quota_card.get_allocated_height(),w.selection_help.get_allocated_height())
        for p in ('codex','claude','muse'):
            button=w.provider_filter.buttons[p]
            assert button.status_image is not None and button.get_tooltip_text()
        for page in range(4):
            w.monitor_tabs.set_current_page(page);pump(w)
            w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
            surface.write_to_png('/tmp/2026-11-07_provider-monitor-'+str(page)+'-'+('dark' if dark else 'light')+'.png')
            if page==2:
                Gdk.pixbuf_get_from_window(w.get_window(),0,0,*w.get_size()).savev('/tmp/2026-11-07_provider-monitor-native-'+('dark' if dark else 'light')+'.png','png',[],[])
    # Drag with spare width; small-window limits keep both panels usable.
    w.resize(1440,980);pump(w)
    x=w.workspace_split.get_position();y=w.workspace_split.get_allocated_height()//2
    sx,sy=pos(w.workspace_split,w);xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','mousemove','--window',xid,str(sx+x+3),str(sy+y),'mousedown','1','mousemove_relative','--sync','30','0','mouseup','1'],check=True);pump(w)
    assert abs(w.workspace_split.get_position()-x)>=15
    assert w.monitor_tabs.get_current_page()==3
finally:w.destroy()
''')


def test_off_buttons_remain_filterable_and_allowance_changes_update_status():
    run_gui(r'''
target_ui.discover_targets=lambda:Inventory([a,b],providers=('codex','claude'))
target_ui.fetch_claude_quota=lambda:Quota('Claude fixture',RateWindow(20,300,9999999999),None,False)
w=make()
try:
    assert not w.provider_filter.buttons['muse'].get_sensitive()
    assert w.provider_filter.buttons['codex'].provider_state=='enabled'
    assert w.provider_filter.buttons['claude'].provider_state=='off'
    click(w.provider_filter.buttons['claude'],w)
    assert len(w.filtered)==0 and len(w.selected)==2
    assert w.provider_filter.buttons['claude'].get_sensitive()
    w.provider_filter.buttons['claude'].grab_focus();pump(w)
    subprocess.run(['xdotool','key','Right'],check=True);pump(w)
    assert w.provider_filter.get_active_id()=='all'  # Skip uninstalled Muse.
    subprocess.run(['xdotool','key','Left'],check=True);pump(w)
    assert w.provider_filter.get_active_id()=='claude'
    config=AppConfig.load();config.prompt_limit=0;config.goal_limit=0;config.save()
    w.poll_runtime();pump(w)
    assert w.provider_filter.buttons['codex'].provider_state=='off'
    assert w.provider_filter.buttons['codex'].status_image.get_icon_name()[0]=='media-playback-stop-symbolic'
    config.prompt_limit=None;config.goal_limit=None;config.save();w.poll_runtime();pump(w)
    assert w.provider_filter.buttons['codex'].provider_state=='enabled'
    assert w.provider_filter.buttons['codex'].status_image.get_icon_name()[0]=='media-playback-start-symbolic'
    assert w.provider_filter.get_active_id()=='claude'  # Status updates do not select another tab.
finally:w.destroy()
''')


def test_tab_text_and_notice_icon_share_the_same_native_tooltip():
    run_gui(r'''
c=replace(b,id='c',provider='claude')
config=AppConfig.load();config.desktop_targets.append(c.to_dict());config.save()
target_ui.discover_targets=lambda:Inventory([a,b,c],providers=('codex','claude'))
target_ui.fetch_claude_quota=lambda:(_ for _ in ()).throw(RuntimeError('Fixture login required'))
w=make()
def labels(widget):
    if isinstance(widget,Gtk.Label):return [widget.get_text()]
    if isinstance(widget,Gtk.Container):return [s for c in widget.get_children() for s in labels(c)]
    return []
try:
    w.set_accept_focus(True);pump(w)
    xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True);pump(w)
    Gtk.Settings.get_default().set_property('gtk-tooltip-timeout',100)
    expected=w.monitor_tabs.tab_headers['claude'].get_tooltip_text()
    for widget in (w.monitor_tabs.tab_labels['claude'],w.monitor_tabs.tab_notices['claude'].icon):
        subprocess.run(['xdotool','mousemove','--window',xid,'5','5'],check=True);pump(w,.4)
        x,y=pos(widget,w)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x+widget.get_allocated_width()//2),str(y+widget.get_allocated_height()//2)],check=True)
        deadline=time.monotonic()+2.5
        text=[]
        while expected not in text and time.monotonic()<deadline:
            pump(w,.1)
            text=[s for t in Gtk.Window.list_toplevels() if t.get_visible() and t.get_type_hint()==Gdk.WindowTypeHint.TOOLTIP for s in labels(t)]
        assert expected in text,(expected,text)
        pump(w,1.2)  # Cross a quota refresh while keeping the pointer still.
        text=[s for t in Gtk.Window.list_toplevels() if t.get_visible() and t.get_type_hint()==Gdk.WindowTypeHint.TOOLTIP for s in labels(t)]
        assert expected in text,(expected,text)
finally:w.destroy()
''')
