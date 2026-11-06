"""Compact overview feedback and user-controlled program-log export/clearing."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest
from test_monitoring_status_ui import BOOT


def run_gui(body):
    with tempfile.TemporaryDirectory(prefix='recharge-log-ui-') as root:
        env=dict(os.environ)
        for suffix in ('CONFIG','DATA','CACHE'):
            env['XDG_'+suffix+'_HOME']=str(Path(root)/suffix.lower())
        result=subprocess.run([sys.executable,'-c',BOOT+body],env=env,capture_output=True,text=True,timeout=35)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'CRITICAL' not in result.stderr,result.stderr

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')


def test_compact_overview_colors_summary_and_infinity():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    assert 'Send now acts immediately' not in w.summary.get_text()
    assert 'Send now acts immediately, even with monitoring off, and may resume paused goals.' in w.send_button.get_tooltip_text()
    assert w.send_row.get_parent() is w.default_group.get_parent().get_parent() is w.compose_group
    assert w.compose_group.get_parent() is w.compose_frame
    assert p.default_prompt.unlimited.get_label()=='∞' and p.prompt_limit.unlimited.get_label()=='∞'
    assert p.default_prompt.unlimited.get_accessible().get_name()=='Unlimited'
    assert 'unlimited' in p.default_prompt.unlimited.get_tooltip_text()
    p.list.select_row(p.rows[b.key]);pump(w)
    assert p.prompt_limit.default.get_label()=='Global default (∞)'
    assert '∞' in p.rows[b.key].allowance.get_text() and 'unlimited' not in p.rows[b.key].allowance.get_text()
    def set_runtime(**flags):
        runtime.clear();runtime.update(flags,per_target_signals=True,recipient_policies=True,one_use_messages=True)
        w.runtime=dict(runtime);w._render_runtime();pump(w)
    def color(label,level):
        actual=label.get_style_context().get_color(label.get_state_flags())
        assert close_color(actual,rgba(status_colors(label)[level])),(label.get_text(),level,actual.to_string())
    def border():
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface));surface.flush()
        x,y=pos(w.monitoring_card,w);y+=w.monitoring_card.get_allocated_height()//2
        offset=y*surface.get_stride()+x*4
        blue,green,red,alpha=bytes(surface.get_data()[offset:offset+4])
        return Gdk.RGBA(red/255,green/255,blue/255,alpha/255)
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark);pump(w)
        set_runtime(desktop_watch=False)
        assert w.send_time_label.get_text()=='No send scheduled'
        color(w.send_time_label,'warning');color(w.next_check_detail,'error');color(w.send_countdown_label,'error')
        assert close_color(border(),rgba(BORDER_COLORS['error']))
        assert not any(name in w.quota_card.get_style_context().list_classes() for name in ('watch-off','watch-on','watch-stopping','quota-status'))
        set_runtime(desktop_watch=False,watch_pause_reason='Choose recipients')
        assert w.watch_label.get_text()=='Waiting'
        color(w.watch_label,'error');assert close_color(border(),rgba(BORDER_COLORS['error']))
        set_runtime(desktop_watch=True,restarting=True)
        assert w.next_check_label.get_text()=='Updating…'
        color(w.next_check_label,'warning');color(w.send_time_label,'warning')
        assert close_color(border(),rgba(BORDER_COLORS['warning']))
        progress=dict(phase='checking_quota',updated_at=time.time(),next_check_at=time.time()+30,selected_recipients=2,selected_messages=1,selected_goals=1,expected_reset_at=time.time()+500)
        set_runtime(desktop_watch=True,watch_settings=tray_control.watch_settings(AppConfig.load()),watch_progress=progress)
        assert w.next_check_label.get_text()=='Checking…'
        color(w.next_check_label,'warning');color(w.send_time_label,'success')
        assert close_color(border(),rgba(BORDER_COLORS['success']))
        progress.update(pending_cycle=True,pending_recipients=2,pending_messages=1,pending_goals=1)
        set_runtime(desktop_watch=True,watch_settings=tray_control.watch_settings(AppConfig.load()),watch_progress=progress)
        assert w.send_time_label.get_text().startswith('Forecast:')
        color(w.send_time_label,'success')
        # Non-listed texts keep their normal theme color.
        assert not any(name.startswith('overview-') for name in w.next_check_detail.get_style_context().list_classes() if name!='overview-compact')
        for width,height in ((1440,980),(1120,820)):
            w.resize(width,height);pump(w)
            heights=[widget.get_allocated_height() for widget in (w.monitoring_card,w.quota_card,w.logo_link)]
            assert max(heights)-min(heights)<=1 and max(heights)<100,heights
            assert w.logo.get_pixbuf().get_width()==64
            assert pos(w.quota_heading,w)[1]==pos(w.send_time_label,w)[1]
            assert w.send_time_label.get_tooltip_text()==w.send_time_label.get_text()
            assert not w.send_time_label.get_line_wrap()
            assert w.get_size().width<=width and w.get_size().height<=height
            assert pos(w.send_row,w.compose_group)[1]==w.default_group.get_parent().get_allocated_height()+w.compose_group.get_spacing()
        w.check_resize();surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size());w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_compact-overview-'+('dark' if dark else 'light')+'.png')
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        Gtk.Settings.get_default().set_property('gtk-tooltip-timeout',100)
        xid=str(w.get_window().get_xid());x,y=pos(w.send_button,w)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x+10),str(y+10)],check=True);pump(w,1)
        assert any(t.get_visible() and t.get_type_hint()==Gdk.WindowTypeHint.TOOLTIP for t in Gtk.Window.list_toplevels())
finally:w.destroy()
''')
