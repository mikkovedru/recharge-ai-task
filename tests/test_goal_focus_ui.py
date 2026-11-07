"""Verify window ownership, frame matching and focus loss before Goal actions."""
import os
from types import SimpleNamespace

import pytest

if os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1':
    pytest.skip('Requires Linux GTK/X11 libraries', allow_module_level=True)

from recharge_ai_task import desktop_goal_ui as ui


def x11(monkeypatch, windows):
    class Window:
        def __init__(self, xid): self.xid = xid
        def get_full_property(self, name, _):
            pid, kind = windows[self.xid]
            value = [pid] if name == '_NET_WM_PID' else kind
            return None if value is None else SimpleNamespace(value=value)
    root = SimpleNamespace(get_full_property=lambda *_: SimpleNamespace(value=list(windows)))
    connection = SimpleNamespace(screen=lambda: SimpleNamespace(root=root),
        intern_atom=lambda name: name, create_resource_object=lambda _, xid: Window(xid), close=lambda: None)
    monkeypatch.setattr(ui.display, 'Display', lambda: connection)


def test_initial_focus_uses_only_the_verified_pid_and_normal_window(monkeypatch):
    x11(monkeypatch, {1: (999, ['_NET_WM_WINDOW_TYPE_NORMAL']),
                      2: (123, ['_NET_WM_WINDOW_TYPE_DIALOG']),
                      3: (123, ['_NET_WM_WINDOW_TYPE_NORMAL'])})
    calls = []
    active = iter([None, 3])
    def foreground(pid):
        assert pid == 123
        xid = next(active)
        if xid is None: raise ui.FocusChanged('Another application has focus')
        return xid
    monkeypatch.setattr(ui, 'active_window', foreground)
    monkeypatch.setattr(ui.subprocess, 'run', lambda args, **kw: calls.append((args, kw)))
    assert ui.focus_codex(123) == 3
    assert calls == [(['xdotool', 'windowactivate', '--sync', '3'], {'check': True, 'timeout': 5})]


@pytest.mark.parametrize('owners', [{1: (999, None)}, {1: (123, None), 2: (123, None)}])
def test_missing_or_ambiguous_window_never_activates(monkeypatch, owners):
    x11(monkeypatch, owners)
    monkeypatch.setattr(ui, 'active_window', lambda _: (_ for _ in ()).throw(ui.FocusChanged('not foreground')))
    monkeypatch.setattr(ui.subprocess, 'run', lambda *a, **kw: pytest.fail('Activated an unverified window'))
    with pytest.raises(RuntimeError, match='one Codex window'): ui.focus_codex(123)


def test_already_focused_codex_does_not_reactivate(monkeypatch):
    monkeypatch.setattr(ui, 'active_window', lambda _: 3)
    monkeypatch.setattr(ui.display, 'Display', lambda: pytest.fail('Unnecessary discovery'))
    assert ui.focus_codex(123) == 3


@pytest.mark.parametrize('result', [None, 4])
def test_focus_must_be_confirmed_after_activation(monkeypatch, result):
    x11(monkeypatch, {3: (123, None)})
    states = iter([None, result])
    def foreground(_):
        xid = next(states)
        if xid is None: raise ui.FocusChanged('not foreground')
        return xid
    commands = []
    monkeypatch.setattr(ui, 'active_window', foreground)
    monkeypatch.setattr(ui.subprocess, 'run', lambda args, **kw: commands.append(args))
    with pytest.raises(ui.FocusChanged): ui.focus_codex(123)
    assert len(commands) == 1


def frame(bounds, *, showing=True):
    return SimpleNamespace(getRoleName=lambda: 'frame',
        getState=lambda: SimpleNamespace(contains=lambda state: state == ui.Atspi.StateType.SHOWING and showing),
        queryComponent=lambda: SimpleNamespace(getExtents=lambda _: SimpleNamespace(
            **dict(zip(('x', 'y', 'width', 'height'), bounds)))))


def frame_discovery(monkeypatch, children):
    monkeypatch.setattr(ui, 'active_window', lambda _: 3)
    monkeypatch.setattr(ui, 'window_bounds', lambda _: (10, 20, 800, 600))
    monkeypatch.setattr(ui, '_application_bus', SimpleNamespace(application=lambda _: children))


def test_missing_active_state_matches_exact_x11_bounds(monkeypatch):
    selected = frame((10, 20, 800, 600))
    frame_discovery(monkeypatch, [frame((0, 0, 960, 720)), selected, frame((10, 20, 800, 599))])
    assert ui.visible_frame(123) is selected


@pytest.mark.parametrize('children', [[], [frame((0, 0, 960, 720))],
    [frame((10, 20, 800, 600)), frame((10, 20, 800, 600))],
    [frame((10, 20, 800, 600), showing=False)]])
def test_geometry_match_fails_closed_when_absent_hidden_or_ambiguous(monkeypatch, children):
    frame_discovery(monkeypatch, children)
    with pytest.raises(RuntimeError, match='active Codex window'): ui.visible_frame(123)


def test_focus_loss_during_geometry_discovery_aborts(monkeypatch):
    frame_discovery(monkeypatch, [frame((10, 20, 800, 600))])
    active = iter([3, 4])
    monkeypatch.setattr(ui, 'active_window', lambda _: next(active))
    with pytest.raises(ui.FocusChanged): ui.visible_frame(123)


@pytest.mark.parametrize('stage', ['frame', 'identity', 'candidate'])
def test_navigation_never_retries_or_reacquires_after_focus_loss(monkeypatch, stage):
    from recharge_ai_task.targets import Target
    calls = []
    monkeypatch.setattr(ui, 'preflight_accessibility', lambda _: None)
    monkeypatch.setattr(ui, 'focus_codex', lambda _: calls.append('focus'))
    monkeypatch.setattr(ui.subprocess, 'run', lambda *a, **kw: calls.append('deeplink'))
    def lost(*_):
        calls.append('lost')
        raise ui.FocusChanged('Another application has focus; no Goal action sent')
    monkeypatch.setattr(ui, 'visible_frame', lost if stage == 'frame' else lambda _: object())
    monkeypatch.setattr(ui, 'current_chat_id', lost if stage == 'identity' else lambda _: 'other')
    monkeypatch.setattr(ui, 'sidebar_rows', lambda _: [object()])
    monkeypatch.setattr(ui, '_title_candidate', lambda *_: True)
    monkeypatch.setattr(ui, 'row_chat_id', lost)
    with pytest.raises(ui.FocusChanged): ui.show_chat(Target('thread', 'chosen', 'Fixture'), 123)
    assert calls == ['focus', 'deeplink', 'lost']


def test_native_focus_acquisition_and_loss_between_two_applications(monkeypatch):
    """Exercise real WM activation without querying or acting on user chats."""
    import select
    import subprocess
    import sys
    from contextlib import closing
    from recharge_ai_task.targets import Target
    source = '''
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib
w = Gtk.Window(title='Recharge focus regression fixture')
w.set_default_size(320, 180)
w.show_all()
GLib.timeout_add(150, lambda: print('ready', flush=True) or False)
Gtk.main()
'''
    processes = []
    with closing(ui.display.Display()) as connection:
        value = connection.screen().root.get_full_property(connection.intern_atom('_NET_ACTIVE_WINDOW'), 0)
        previous = int(value.value[0]) if value is not None and len(value.value) else None
    run = subprocess.run
    try:
        for _ in range(2):
            process = subprocess.Popen([sys.executable, '-c', source], stdout=subprocess.PIPE,
                text=True, env=dict(os.environ, NO_AT_BRIDGE='1', GIO_USE_VFS='local'))
            processes.append(process)
            assert select.select([process.stdout], [], [], 5)[0], 'Fixture did not map'
            assert process.stdout.readline().strip() == 'ready'
        chosen, other = processes
        other_xid = ui.focus_codex(other.pid)
        chosen_xid = ui.focus_codex(chosen.pid)
        assert chosen_xid != other_xid
        assert ui.active_window(chosen.pid) == chosen_xid
        bounds = ui.window_bounds(chosen_xid)
        assert bounds[2:] == (320, 180)
        opened = []
        monkeypatch.setattr(ui, 'preflight_accessibility', lambda _: None)
        monkeypatch.setattr(ui, 'visible_frame', lambda pid: ui.active_window(pid))
        monkeypatch.setattr(ui, 'current_chat_id', lambda _: 'synthetic-fixture')
        target = Target('thread', 'synthetic-fixture', 'Fixture')
        def successful_dispatch(args, **kwargs):
            if args[0] == 'xdg-open':
                assert ui.active_window(chosen.pid) == chosen_xid
                opened.append(args)
                return SimpleNamespace(returncode=0)
            return run(args, **kwargs)
        monkeypatch.setattr(ui.subprocess, 'run', successful_dispatch)
        ui.focus_codex(other.pid)
        assert ui.show_chat(target, chosen.pid) == chosen_xid
        assert opened == [['xdg-open', 'codex://threads/synthetic-fixture']]
        opened.clear()
        def dispatch(args, **kwargs):
            if args[0] == 'xdg-open':
                opened.append(args)
                ui.focus_codex(other.pid)
                return SimpleNamespace(returncode=0)
            return run(args, **kwargs)
        monkeypatch.setattr(ui.subprocess, 'run', dispatch)
        with pytest.raises(ui.FocusChanged):
            ui.show_chat(target, chosen.pid)
        assert opened == [['xdg-open', 'codex://threads/synthetic-fixture']]
        assert ui.active_window(other.pid) == other_xid
    finally:
        for process in processes:
            process.terminate()
            process.wait(timeout=5)
            process.stdout.close()
        if previous:
            run(['xdotool', 'windowactivate', '--sync', str(previous)], check=False, timeout=5)
