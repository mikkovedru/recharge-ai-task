"""Native keyboard editing of default and per-target action limits."""
import os

import pytest

from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(
    os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK/X11"
)


def test_manual_limits_survive_refresh_and_save_on_enter():
    run_gui(r'''
w=make();p=w.recipient_panel
try:
    w.set_accept_focus(True)
    w.set_focus_on_map(True)
    xid=str(w.get_window().get_xid())
    subprocess.run(['xdotool','windowactivate','--sync',xid],check=True,timeout=5)
    p.select_recipient(a.key);pump(w)
    controls=(
        (p.default_prompt, 'prompt_limit', None, 27, 'Return'),
        (p.default_goal, 'goal_limit', None, 31, 'KP_Enter'),
        (p.prompt_limit, 'prompt_limit', a.key, 42, 'Return'),
        (p.goal_limit, 'goal_limit', a.key, 53, 'Return'),
    )
    def key(*keys):
        subprocess.run(['xdotool','key','--clearmodifiers',*keys],check=True)
        pump(w)
    for control, field, target_key, number, enter in controls:
        def saved():
            config=AppConfig.load()
            settings=config if target_key is None else next(t for t in config.chosen_targets() if t.key==target_key)
            return getattr(settings,field)

        control.limited.clicked();pump(w)
        assert w.get_focus() is control.number
        previous=saved()
        key('ctrl+a',*str(number))
        assert control.number.get_text()==str(number)
        old_mode=control.mode
        key('Escape');pump(w,.35)
        assert not control.number_popover.get_visible()
        assert saved()==previous and control.mode==old_mode
        control.limited.clicked();pump(w)
        key('ctrl+a',*str(number))
        w.poll_runtime();pump(w)
        w.refresh_statuses();pump(w)
        assert control.number.get_text()==str(number), (field, target_key, control.number.get_text())
        assert saved()==previous
        key(enter)
        assert saved()==number, (field, target_key, saved())
        assert control.limited.get_label()==str(number)
        pump(w,.35)
        assert not control.number_popover.get_visible()

        control.limited.clicked();pump(w)
        x,y=pos(control.number,w)
        def step(offset):
            subprocess.run(['xdotool','mousemove','--window',xid,
                            str(x+control.number.get_allocated_width()-offset),
                            str(y+control.number.get_allocated_height()//2),'click','1'],check=True)
            pump(w)
        step(10)
        assert control.number.get_value_as_int()==number+1 and saved()==number
        w.poll_runtime();pump(w)
        assert control.number.get_value_as_int()==number+1
        key('Escape');pump(w,.35)
        assert not control.number_popover.get_visible()
        assert control.number.get_value_as_int()==number and saved()==number
        control.limited.clicked();pump(w)
        step(46)
        assert control.number.get_value_as_int()==number-1 and saved()==number
        key('Return');pump(w,.35)
        assert saved()==number-1

    p.prompt_limit.limited.clicked();pump(w)
    key('ctrl+a','9','9')
    p.select_recipient(b.key);pump(w,.35)
    assert not p.prompt_limit.number_popover.get_visible()
    by_key={t.key:t for t in AppConfig.load().chosen_targets()}
    assert by_key[a.key].prompt_limit==41 and by_key[b.key].prompt_limit==b.prompt_limit

    p.default_prompt.limited.clicked();pump(w)
    key('ctrl+a','6','2')
    x,y=pos(w.next_check_label,w)
    subprocess.run(['xdotool','mousemove','--window',xid,str(x+5),str(y+5),'click','1'],check=True)
    pump(w,.35)
    assert not p.default_prompt.number_popover.get_visible()
    assert AppConfig.load().prompt_limit==62
finally:w.destroy()
''')
