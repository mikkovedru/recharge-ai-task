"""Target provider filters use centered, content-sized buttons."""
import os

import pytest
from test_monitoring_status_ui import run_gui

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK/X11')


def test_recipient_provider_buttons_fit_captions_and_center_text():
    run_gui(r'''
c=replace(b,id='c',provider='claude')
m=replace(b,id='m',provider='muse')
config=AppConfig.load();config.desktop_targets += [c.to_dict(),m.to_dict()];config.save()
target_ui.discover_targets=lambda:Inventory([a,b,c,m],providers=('codex','claude','muse'))
target_ui.fetch_claude_quota=lambda:Quota('fixture',RateWindow(20,300,9999999999),None,False)
target_ui.fetch_muse_quota=lambda _:Quota('fixture',RateWindow(20,300,9999999999),None,False)
w=make();group=w.recipient_panel.provider_filter
try:
    for width in (1440,1120):
        w.resize(width,820);pump(w)
        heading=w.recipient_panel.heading
        heading_center=pos(heading,w)[1]+heading.get_allocated_height()/2
        group_center=pos(group,w)[1]+group.get_allocated_height()/2
        assert abs(heading_center-group_center)<=2,(width,heading_center,group_center)
        row_positions=[]
        for key in ('all','codex','claude','muse'):
            button=group.buttons[key];caption=button.caption
            assert button.get_allocated_width()<=caption.get_allocated_width()+30,(key,button.get_allocated_width(),caption.get_allocated_width())
            x,y=pos(caption,button)
            assert abs(x+caption.get_allocated_width()/2-button.get_allocated_width()/2)<=2
            x,y=pos(button,group)
            row_positions.append(y)
            assert x>=0 and x+button.get_allocated_width()<=group.get_allocated_width()
        assert len(set(row_positions))==1,row_positions
        assert group.buttons['all'].get_allocated_width()<group.buttons['claude'].get_allocated_width()
    click(group.buttons['claude'],w)
    assert len(w.recipient_panel._visible_rows())==1
    subprocess.run(['xdotool','key','Right'],check=True);pump(w)
    assert group.get_active_id()=='muse'
    assert len(w.selected)==4
    # Exercise the actual header in a narrow window: the dashboard's other
    # controls impose a wider minimum than the heading's wrap threshold.
    header=w.recipient_panel.heading_row
    w.recipient_panel.remove(header)
    probe=Gtk.Window();probe.add(header);probe.show_all()
    group.set_counts(['codex','codex','claude','muse']);pump(probe)
    try:
        heading_width=heading.get_preferred_width().natural_width
        group_width=group.get_preferred_width().natural_width
        probe.resize(max(heading_width,group_width)+20,120);pump(probe)
        assert pos(group,probe)[1]>=pos(heading,probe)[1]+heading.get_allocated_height()
        assert len({pos(group.buttons[key],group)[1] for key in ('all','codex','claude','muse')})==1
        probe.resize(heading_width+group_width+80,120);pump(probe)
        assert abs(pos(heading,probe)[1]+heading.get_allocated_height()/2-pos(group,probe)[1]-group.get_allocated_height()/2)<=2
        # Extra categories and longer counts can force wrapping without resizing.
        group.set_counts(['codex']*1000+['claude']*1000+['muse']*1000+['gemini']*1000+['antigravity']*1000+['opencode']*1000);pump(probe)
        assert pos(group,probe)[1]>=pos(heading,probe)[1]+heading.get_allocated_height()
        group.set_counts(['codex','codex','claude','muse']);pump(probe)
        assert abs(pos(heading,probe)[1]+heading.get_allocated_height()/2-pos(group,probe)[1]-group.get_allocated_height()/2)<=2
    finally:probe.destroy()
finally:w.destroy()
''')
