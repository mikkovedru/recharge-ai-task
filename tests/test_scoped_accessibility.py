"""Scope AT-SPI calls to the selected desktop owner; never prime shell caches."""
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1', reason='Requires GTK libraries')


def test_discovery_only_queries_registry_and_bus_daemon():
    from recharge_ai_task.scoped_accessibility import ApplicationBus, Accessible, States
    bus = ApplicationBus.__new__(ApplicationBus)
    bus.owner = None
    calls = []
    def call(owner, path, interface, method, signature=None, args=()):
        calls.append((owner, method))
        if method == 'GetChildren':
            return ([(':1.shell', '/org/a11y/atspi/accessible/root'), (':1.codex', '/org/a11y/atspi/accessible/root')],)
        assert method == 'GetConnectionUnixProcessID'
        return (42 if args == (':1.codex',) else 9,)
    bus.call = call
    app = bus.application(42)
    assert app.owner == ':1.codex'
    bus.application(42)
    assert all(owner in {'org.a11y.atspi.Registry', 'org.freedesktop.DBus'} for owner, _ in calls)
    assert not any(method == 'GetItems' for _, method in calls)
    with pytest.raises(RuntimeError, match='left the verified'):
        Accessible(bus, ':1.shell', '/shell')
    with pytest.raises(RuntimeError, match='process changed'):
        bus.application(99)
    assert States([0, 2]).contains(33) and not States([0, 2]).contains(32)


def test_real_accessibility_protocol_against_synthetic_gtk_application():
    source = r'''
import os, subprocess, sys, time
import gi
gi.require_version('Atspi','2.0')
from recharge_ai_task.scoped_accessibility import ApplicationBus
from gi.repository import Atspi
fixture = """
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
w=Gtk.Window(title='Scoped accessibility fixture')
b=Gtk.Button(label='Fixture action')
b.connect('clicked',lambda *_:b.set_label('Action accepted'))
w.add(b);w.show_all()
GLib.timeout_add(200,lambda:print('ready',flush=True) or False)
Gtk.main()
"""
bus=ApplicationBus()
env=dict(os.environ,GTK_MODULES='atk-bridge',AT_SPI_BUS_ADDRESS=bus.address,GIO_USE_VFS='local')
env.pop('NO_AT_BRIDGE',None)
p=subprocess.Popen([sys.executable,'-c',fixture],env=env,stdout=subprocess.PIPE,text=True)
try:
    assert p.stdout.readline().strip()=='ready'
    deadline=time.monotonic()+5
    while True:
        try:app=bus.application(p.pid);break
        except RuntimeError:
            if time.monotonic()>deadline:raise
            time.sleep(.1)
    frames=list(app);assert len(frames)==1
    frame=frames[0]
    assert frame.name=='Scoped accessibility fixture' and frame.getRoleName()=='frame'
    def nodes(node):
        yield node
        for child in node:yield from nodes(child)
    button=next(n for n in nodes(frame) if n.getRoleName()=='push button')
    assert button.name=='Fixture action'
    assert button.getState().contains(Atspi.StateType.ENABLED)
    assert button.parent.getRoleName()=='frame'
    assert isinstance(button.getAttributes(),list)
    assert button.queryComponent().getExtents(Atspi.CoordType.SCREEN).width>0
    assert button.queryAction().doAction(0)
    assert not Atspi.is_initialized(), "Global libatspi discovery was initialized"
    deadline=time.monotonic()+3
    while button.name!='Action accepted':
        assert time.monotonic()<deadline
        time.sleep(.05)
finally:
    p.terminate();p.wait(timeout=5)
'''
    result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', source],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
