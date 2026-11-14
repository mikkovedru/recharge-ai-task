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


def test_real_accessibility_protocol_against_synthetic_gtk_application(tmp_path):
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
    matches=frame.find_roles(('push button',))
    assert matches is not None and len(matches)==1 and matches[0].path==button.path
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
    from contextlib import closing
    from Xlib import display
    def root_address():
        with closing(display.Display()) as connection:
            atom=connection.intern_atom('AT_SPI_BUS',only_if_exists=True)
            value=connection.screen().root.get_full_property(atom,0) if atom else None
            return bytes(value.value) if value else None
    original_address=root_address()
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', source],
                            env=dict(os.environ, XDG_RUNTIME_DIR=str(runtime), GDK_BACKEND='x11',
                                     WAYLAND_DISPLAY='recharge-private-accessibility-test'),
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
    assert root_address()==original_address, "Private test changed the display accessibility address"


def test_connection_refreshes_a_stale_advertised_address_once(monkeypatch):
    from recharge_ai_task import scoped_accessibility as api
    addresses=iter(['unix:path=/missing/old','unix:path=/valid/new'])
    session=SimpleNamespace(call_sync=lambda *_:SimpleNamespace(unpack=lambda:(next(addresses),)))
    monkeypatch.setattr(api.Gio,'bus_get_sync',lambda *_:session)
    seen=[];connection=object()
    def connect(address,*_):
        seen.append(address)
        if len(seen)==1:
            raise api.GLib.Error.new_literal(api.Gio.io_error_quark(),'missing socket',api.Gio.IOErrorEnum.NOT_FOUND)
        return connection
    monkeypatch.setattr(api.Gio.DBusConnection,'new_for_address_sync',connect)
    monkeypatch.setattr(api.time,'sleep',lambda _:None)
    bus=api.ApplicationBus()
    assert seen==['unix:path=/missing/old','unix:path=/valid/new']
    assert bus.connection is connection and bus.owner is None


def test_persistent_missing_socket_has_actionable_bounded_error(monkeypatch):
    from recharge_ai_task import scoped_accessibility as api
    session=SimpleNamespace(call_sync=lambda *_:SimpleNamespace(unpack=lambda:('unix:path=/missing/accessibility-bus',)))
    monkeypatch.setattr(api.Gio,'bus_get_sync',lambda *_:session)
    seen=[]
    def connect(address,*_):
        seen.append(address)
        raise api.GLib.Error.new_literal(api.Gio.io_error_quark(),'No such file',api.Gio.IOErrorEnum.NOT_FOUND)
    monkeypatch.setattr(api.Gio.DBusConnection,'new_for_address_sync',connect)
    monkeypatch.setattr(api.time,'sleep',lambda _:None)
    with pytest.raises(api.AccessibilityUnavailable,match='Advertised socket is missing') as error:
        api.ApplicationBus()
    assert len(seen)==2 and 'Restore desktop accessibility' in str(error.value)


def test_transport_failure_never_replays_an_accessibility_action():
    from recharge_ai_task import scoped_accessibility as api
    methods=[];closed=[]
    def call(*args):
        methods.append(args[3])
        raise api.GLib.Error.new_literal(api.Gio.io_error_quark(),'connection closed',api.Gio.IOErrorEnum.CLOSED)
    bus=api.ApplicationBus.__new__(api.ApplicationBus)
    bus.address='unix:path=/missing/bus'
    bus.connection=SimpleNamespace(call_sync=call,is_closed=lambda:False,close_sync=lambda *_:closed.append(True))
    with pytest.raises(api.AccessibilityUnavailable):
        bus.call(':1.codex','/button','org.a11y.atspi.Action','DoAction','(i)',(0,))
    assert methods==['DoAction'] and closed==[True]


def test_exited_accessibility_owner_is_requeried_by_pid():
    from recharge_ai_task import scoped_accessibility as api
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=':1.old';bus.root=api.ROOT
    seen=[]
    def call(owner,path,interface,method,signature=None,args=()):
        seen.append((owner,method,args))
        if method=='GetChildren':return ([(':1.shell',api.ROOT),(':1.new',api.ROOT)],)
        if args==(':1.old',):
            raise api.GLib.Error.new_literal(api.Gio.dbus_error_quark(),'old owner exited',api.Gio.DBusError.NAME_HAS_NO_OWNER)
        return (42 if args==(':1.new',) else 9,)
    bus.call=call
    assert bus.application(42).owner==':1.new'
    assert all(owner in {api.DBUS,'org.a11y.atspi.Registry'} for owner,_,_ in seen)


def test_live_bus_without_codex_registration_reports_reopen_guidance():
    from recharge_ai_task import scoped_accessibility as api
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=None
    calls=[]
    def call(owner,path,interface,method,signature=None,args=()):
        calls.append((owner,method))
        if method=='GetChildren':return ([(':1.other',api.ROOT)],)
        return (9,)
    bus.call=call
    with pytest.raises(api.AccessibilityUnavailable,match='fully quit and reopen Codex') as error:
        bus.application(42)
    assert 'not registered on the current' in str(error.value)
    assert str(error.value).count('no Goal action sent')==1
    assert bus.owner is None
    assert all(owner in {api.DBUS,'org.a11y.atspi.Registry'} for owner,_ in calls)


def test_empty_registry_is_not_a_chat_identity_failure():
    from recharge_ai_task import scoped_accessibility as api
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=None
    bus.call=lambda *_: ([],)
    with pytest.raises(api.AccessibilityUnavailable,match='not registered'):
        bus.application(42)


@pytest.mark.parametrize('code',['SERVICE_UNKNOWN','SPAWN_SERVICE_NOT_FOUND','SPAWN_CHILD_EXITED'])
def test_missing_registry_is_distinguished_from_missing_application(code):
    from recharge_ai_task import scoped_accessibility as api
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=None
    def call(*_):
        raise api.GLib.Error.new_literal(api.Gio.dbus_error_quark(),'registry unavailable',getattr(api.Gio.DBusError,code))
    bus.call=call
    with pytest.raises(api.AccessibilityUnavailable,match='registry is unavailable') as error:
        bus.application(42)
    assert 'not registered' not in str(error.value)


def test_ambiguous_applications_never_authorize_native_accessibility():
    from recharge_ai_task import scoped_accessibility as api
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=None
    bus.call=lambda owner,path,interface,method,*_: ([(':1.a',api.ROOT),(':1.b',api.ROOT)],) if method=='GetChildren' else (42,)
    with pytest.raises(RuntimeError,match='More than one accessibility application'):
        bus.application(42)
    assert bus.owner is None


def test_missing_registration_launch_hint_is_specific_and_not_executed(monkeypatch):
    from recharge_ai_task import scoped_accessibility as api
    monkeypatch.setattr(api.os, 'readlink', lambda _: '/opt/Codex App/Codex')
    hint=api.accessibility_launch_hint(123)
    assert "'/opt/Codex App/Codex' --force-renderer-accessibility" in hint
    assert 'needs verification after restart' in hint
    bus=api.ApplicationBus.__new__(api.ApplicationBus);bus.owner=None;bus.call=lambda *_:([],)
    with pytest.raises(api.AccessibilityUnavailable) as error:
        bus.application(123)
    assert 'Restarting Recharge cannot' in str(error.value)
    assert 'native Resume goal button' in str(error.value)
    assert hint in str(error.value)


def test_unknown_process_has_no_guessed_launch_command(monkeypatch):
    from recharge_ai_task import scoped_accessibility as api
    monkeypatch.setattr(api.os, 'readlink', lambda _:'/usr/bin/unknown')
    assert api.accessibility_launch_hint(123)==''
    def missing(_):raise FileNotFoundError()
    monkeypatch.setattr(api.os,'readlink',missing)
    assert api.accessibility_launch_hint(123)==''


@pytest.mark.parametrize('domain,code', [('io', 'TIMED_OUT'), ('dbus', 'NO_REPLY'), ('dbus', 'TIMED_OUT')])
@pytest.mark.parametrize('method', ['GetChildren', 'DoAction', 'SetTextContents'])
def test_request_timeout_keeps_transport_and_never_replays(domain, code, method):
    from recharge_ai_task import scoped_accessibility as api
    calls, closed = [], []
    error_domain = api.Gio.io_error_quark() if domain == 'io' else api.Gio.dbus_error_quark()
    error_code = getattr(api.Gio.IOErrorEnum if domain == 'io' else api.Gio.DBusError, code)
    def call(*args):
        calls.append(args)
        raise api.GLib.Error.new_literal(error_domain, 'Timeout was reached', error_code)
    bus = api.ApplicationBus.__new__(api.ApplicationBus)
    bus.timeout_ms = 30000
    bus.address = 'unix:path=/still-present/bus'
    bus.connection = SimpleNamespace(call_sync=call, is_closed=lambda: False, close_sync=lambda *_: closed.append(True))
    with pytest.raises(api.AccessibilityTimeout) as error:
        bus.call(':1.codex', '/control', api.ACCESSIBLE, method)
    assert len(calls) == 1 and calls[0][7] == 30000
    assert not closed
    assert method in str(error.value) and '/control' in str(error.value) and 'after 30s' in str(error.value)
    assert 'does not mean accessibility is disabled' in str(error.value)
    assert 'log out' not in str(error.value) and not isinstance(error.value, api.AccessibilityUnavailable)


def test_slow_address_reply_is_not_misreported_as_a_missing_bus(monkeypatch):
    from recharge_ai_task import scoped_accessibility as api
    calls = []
    def slow(*args):
        calls.append(args)
        raise api.GLib.Error.new_literal(api.Gio.io_error_quark(), 'slow address', api.Gio.IOErrorEnum.TIMED_OUT)
    monkeypatch.setattr(api.Gio, 'bus_get_sync', lambda *_: SimpleNamespace(call_sync=slow))
    with pytest.raises(api.AccessibilityTimeout, match='GetAddress'):
        api.ApplicationBus(timeout_ms=30000)
    assert len(calls) == 1 and calls[0][7] == 30000


def test_real_delayed_reply_succeeds_with_long_deadline_and_timed_out_action_is_not_replayed(tmp_path):
    """A private D-Bus peer replies after the former 1.5-second deadline."""
    source = r'''
import os, subprocess, sys, time
from recharge_ai_task.scoped_accessibility import ApplicationBus, AccessibilityTimeout, ACCESSIBLE
from gi.repository import Gio
service = r"""
import gi
gi.require_version('Gio', '2.0')
from gi.repository import Gio, GLib
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
info = Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.a11y.atspi.Accessible"><method name="GetRole"><arg type="u" direction="out"/></method><method name="GetCounts"><arg type="au" direction="out"/></method></interface><interface name="org.a11y.atspi.Action"><method name="DoAction"><arg type="i" direction="in"/><arg type="b" direction="out"/></method></interface></node>')
counts = [0, 0]
def handle(connection, sender, path, interface, method, params, invocation):
    if method == 'GetCounts':
        invocation.return_value(GLib.Variant('(au)', (counts,)))
        return
    counts[method == 'DoAction'] += 1
    value = GLib.Variant('(b)', (True,)) if method == 'DoAction' else GLib.Variant('(u)', (123,))
    GLib.timeout_add(2200, lambda: invocation.return_value(value) or False)
for interface in info.interfaces:
    bus.register_object('/fixture', interface, handle, None, None)
print(bus.get_unique_name(), flush=True)
GLib.MainLoop().run()
"""
p = subprocess.Popen([sys.executable, '-c', service], stdout=subprocess.PIPE, text=True)
try:
    owner = p.stdout.readline().strip()
    assert owner.startswith(':'), owner
    bus = ApplicationBus.__new__(ApplicationBus)
    bus.address = os.environ['DBUS_SESSION_BUS_ADDRESS']
    bus.connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    bus.timeout_ms = 1500
    try:
        bus.call(owner, '/fixture', ACCESSIBLE, 'GetRole')
        raise AssertionError('Former deadline unexpectedly accepted a delayed reply')
    except AccessibilityTimeout:
        assert not bus.connection.is_closed()
    bus.timeout_ms = 30000
    start = time.monotonic()
    assert bus.call(owner, '/fixture', ACCESSIBLE, 'GetRole') == (123,)
    assert time.monotonic() - start >= 2
    bus.timeout_ms = 1500
    try:
        bus.call(owner, '/fixture', 'org.a11y.atspi.Action', 'DoAction', '(i)', (0,))
        raise AssertionError('Expected action acknowledgement timeout')
    except AccessibilityTimeout:
        pass
    bus.timeout_ms = 30000
    assert bus.call(owner, '/fixture', ACCESSIBLE, 'GetCounts') == ([2, 1],)
finally:
    p.terminate()
    p.wait(timeout=5)
    p.stdout.close()
'''
    result = subprocess.run(['dbus-run-session', '--', sys.executable, '-c', source],
        env=dict(os.environ, XDG_RUNTIME_DIR=str(tmp_path)), capture_output=True, text=True, timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


def test_collection_query_is_scoped_and_uses_role_bitsets():
    from recharge_ai_task.scoped_accessibility import Accessible
    from gi.repository import Atspi
    calls=[]
    def call(owner,path,interface,method,signature,args):
        calls.append((owner,path,interface,method,signature,args))
        return ([(':1.codex','/button'),(':1.codex','/menu')],)
    bus=SimpleNamespace(owner=':1.codex',call=call)
    root=Accessible(bus,':1.codex','/frame')
    matches=root.find_roles(('push button','menu'))
    assert [node.path for node in matches]==['/button','/menu']
    owner,path,interface,method,signature,args=calls[0]
    assert (owner,path,interface,method)==(':1.codex','/frame','org.a11y.atspi.Collection','GetMatches')
    assert signature=='((aiia{ss}iaiiasib)uib)'
    rule,sortby,count,traverse=args
    for role in (Atspi.Role.PUSH_BUTTON,Atspi.Role.MENU):
        assert rule[4][int(role)//32] & (1<<(int(role)%32))
    assert count==0 and traverse and not rule[-1]


def test_collection_query_rejects_foreign_application_references():
    from recharge_ai_task.scoped_accessibility import Accessible
    bus=SimpleNamespace(owner=':1.codex',call=lambda *a:([(':1.shell','/foreign')],))
    with pytest.raises(RuntimeError,match='left the verified'):
        Accessible(bus,':1.codex','/frame').find_roles(('push button',))


def test_collection_falls_back_only_for_unsupported_methods():
    from recharge_ai_task.scoped_accessibility import Accessible
    from gi.repository import GLib,Gio
    bus=SimpleNamespace(owner=':1.codex')
    for code in (Gio.DBusError.UNKNOWN_METHOD,Gio.DBusError.UNKNOWN_INTERFACE,Gio.DBusError.NOT_SUPPORTED):
        def unsupported(*a):raise GLib.Error.new_literal(Gio.dbus_error_quark(),'unsupported',code)
        bus.call=unsupported
        assert Accessible(bus,':1.codex','/frame').find_roles(('push button',)) is None
    def failed(*a):raise GLib.Error.new_literal(Gio.dbus_error_quark(),'failed',Gio.DBusError.FAILED)
    bus.call=failed
    with pytest.raises(GLib.Error):Accessible(bus,':1.codex','/frame').find_roles(('push button',))
