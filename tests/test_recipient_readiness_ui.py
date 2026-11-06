"""Recipient list space, passive actions, issue highlighting and accessible help."""
import os
import subprocess
import sys

import pytest


@pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK')
def test_recipient_space_readiness_and_help_remain_usable():
    result = subprocess.run([sys.executable, '-c', r'''
import os,subprocess,time,cairo,gi
gi.require_version("Gtk","3.0")
from dataclasses import replace
from gi.repository import Gtk,Gdk
from recharge_ai_task import target_ui,autostart
from recharge_ai_task.config import AppConfig,config_dir
from recharge_ai_task.targets import Target,Inventory
from recharge_ai_task.quota import Quota,RateWindow
from recharge_ai_task.delivery_policy import UsageLedger

autostart.autostart_target=lambda:config_dir()/'test.desktop'
target_ui.discover_codex=lambda _:'fixture'
target_ui.fetch_quota=lambda _:Quota('test',RateWindow(40,300,9999999999),None,False)
target_ui.tray_control.request=lambda *a,**kw:{'desktop_watch':False}
target_ui.send_signals=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Editing sent signals'))
a=Target('thread','message','Message allowance exhausted',instance='/fixture',endpoint='/fixture/ipc/ipc.sock',send_prompt=True,send_goal=False,task_status='Idle',goal_status='No goal',prompt_limit=1)
b=replace(a,id='goal',title='Paused Goal',send_prompt=False,send_goal=True,goal_status='Paused')
c=replace(a,id='both',title='Message ready · Goal blocked',send_goal=True,goal_status='Blocked',prompt_limit=None)
target_ui.discover_targets=lambda:Inventory([a,b,c])
AppConfig(desktop_targets=[t.to_dict() for t in (a,b,c)]).save()
ledger=UsageLedger();attempt=ledger.reserve(a.key,'prompt',1);ledger.finish(attempt,'sent')
def pump(w,delay=.2):
    deadline=time.monotonic()+delay
    while time.monotonic()<deadline or w.discovery_busy or w.runtime_busy or w.quota_busy or w.activity_busy:
        while Gtk.events_pending():Gtk.main_iteration_do(False)
        time.sleep(.002)
w=target_ui.TargetPicker(quit_on_close=False)
w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
p=w.recipient_panel
try:
    def pos(widget,parent=w):return widget.translate_coordinates(parent,0,0)
    def context(row):return row.get_style_context()
    for dark in (False,True):
        Gtk.Settings.get_default().set_property('gtk-theme-name','Adwaita')
        Gtk.Settings.get_default().set_property('gtk-application-prefer-dark-theme',dark)
        w._summary();pump(w)
        ra,rb,rc=(p.rows[t.key] for t in (a,b,c))
        assert context(ra).has_class('recipient-passive')
        assert context(rb).has_class('recipient-passive') and rb.manual.ready and not rb.automatic.ready
        assert not context(rc).has_class('recipient-passive') and rc.automatic.ready
        assert ra.get_sensitive() and ra.indicator.get_can_focus()
        assert 'foreground=' in ra.allowance.get_label() and '⚠' in ra.allowance.get_text()
        assert 'Blocked' in rc.plan.get_text() and 'foreground=' in rc.plan.get_label()
        assert 'Message ready' not in rc.plan.get_text()
        assert 'Message limit reached' in ra.indicator.get_tooltip_text()
        assert 'Paused' in rb.indicator.get_tooltip_text() and 'Send now' in rb.indicator.get_tooltip_text()
        assert 'live' in rb.indicator.get_tooltip_text()
        # Clicking the icon is a keyboard-accessible route to the same explanation.
        rb.indicator.grab_focus();rb.indicator.clicked();pump(w)
        assert rb.details.get_visible() and 'intentional pauses' in rb.explanation.get_text()
        rb.details.popdown();pump(w,.4)
        # Passive rows still select their editor. Counts reset makes the row ready.
        p.list.select_row(ra);assert p.selected_key==a.key and p.editor.get_sensitive()
        p.reset.clicked();pump(w)
        assert not context(ra).has_class('recipient-passive') and ra.automatic.ready
        attempt=ledger.reserve(a.key,'prompt',1);ledger.finish(attempt,'sent');p.render()
        # Changing a custom message to empty updates the actual blocker.
        p.list.select_row(rc);p.custom.set_active(True);p.message_buffer.set_text(' ');pump(w)
        assert context(rc).has_class('recipient-passive') and 'Message is empty' in rc.indicator.get_tooltip_text()
        p.message_buffer.set_text('Continue');pump(w)
        assert not context(rc).has_class('recipient-passive')
        w.get_window().invalidate_rect(None,True);w.queue_draw();pump(w)
        image=Gdk.pixbuf_get_from_window(w.get_window(),0,0,*w.get_size())
        image.savev('/tmp/2026-11-06_recipient-native-'+('dark' if dark else 'light')+'.png','png',[],[])
        w.check_resize()
        surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,*w.get_size())
        w.draw(cairo.Context(surface))
        surface.write_to_png('/tmp/2026-11-06_recipient-'+('dark' if dark else 'light')+'.png')
        assert not any(row.details.get_visible() for row in p.rows.values())
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        # A native key press opens focused help, and a real hover shows its tooltip.
        p.list.select_row(ra);pump(w)
        w.set_accept_focus(True)
        xid=str(w.get_window().get_xid())
        subprocess.run(['xdotool','windowfocus',xid],check=True)
        ra.indicator.grab_focus()
        subprocess.run(['xdotool','key','--window',xid,'Return'],check=True);pump(w,.4)
        assert ra.details.get_visible()
        ra.details.popdown();pump(w,.4)
        Gtk.Settings.get_default().set_property('gtk-tooltip-timeout',100)
        x,y=pos(ra.indicator);x+=10;y+=10
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y)],check=True);pump(w,1)
        assert any(t.get_visible() and t.get_type_hint()==Gdk.WindowTypeHint.TOOLTIP for t in Gtk.Window.list_toplevels())
        subprocess.run(['xdotool','mousemove','--window',xid,'10','10'],check=True);pump(w)
    # Space above the panel is used only by the logo.
    assert pos(p)[1] < pos(w.search)[1]
    assert pos(w.recipient_frame)[1]==pos(w.right_workspace)[1]
    assert pos(w.recipient_frame)[1]+w.recipient_frame.get_allocated_height()==w.get_size().height-14
    list_height=p.list_scroller.get_allocated_height()
    editor_height=p.editor_scroller.get_allocated_height()
    w.resize(1440,1100);pump(w)
    assert p.list_scroller.get_allocated_height()>list_height+100
    assert abs(p.editor_scroller.get_allocated_height()-editor_height)<=3
    # Shrinking retains the editor; its controls remain inside the viewport.
    for width,height in ((1400,980),(1120,820)):
        w.resize(width,height);pump(w)
        assert w.get_size().width<=width and w.get_size().height<=height
        assert pos(p.message_resize,p.editor_scroller)[1]+p.message_resize.get_allocated_height()<=p.editor_scroller.get_allocated_height()
        assert p.list_scroller.get_allocated_height()>=60
        assert pos(w.recipient_frame)[1]+w.recipient_frame.get_allocated_height()==w.get_size().height-14
    # A native mouse drag adjusts the list/editor divider and saves its position.
    if os.environ.get('RECHARGE_AI_TASK_POINTER_TESTS')=='1':
        before=p.split.get_position();x,y=pos(p.split);x+=20;y+=before+3
        xid=str(w.get_window().get_xid())
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y),'mousedown','1'],check=True);pump(w)
        subprocess.run(['xdotool','mousemove','--window',xid,str(x),str(y-30)],check=True);pump(w)
        subprocess.run(['xdotool','mouseup','1'],check=True);pump(w)
        assert p.split.get_position()<before-20
    saved=p.split.get_position();w.window_layout.close();w.destroy()
    w=target_ui.TargetPicker(quit_on_close=False);w.set_accept_focus(False);w.set_focus_on_map(False);w.show_all();pump(w)
    assert abs(w.recipient_panel.split.get_position()-saved)<=1
finally:
    w.destroy()
'''], capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'CRITICAL' not in result.stderr, result.stderr
