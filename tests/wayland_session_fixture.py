"""Private compositor/DBus integration driver; launched by test_wayland.py."""
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import time


def wait_for(check, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise AssertionError("Timed out waiting for fixture")


runtime = Path(os.environ["XDG_RUNTIME_DIR"])
module_dir = os.environ.get("WESTON_TEST_MODULE_DIR")
if module_dir:
    os.environ["WESTON_MODULE_MAP"] = (
        f"x11-backend.so={module_dir}/libweston-13/x11-backend.so;"
        f"desktop-shell.so={module_dir}/weston/desktop-shell.so;")
config = runtime / "weston.ini"
if module_dir:
    prefix = Path(module_dir).parent.parent
    os.environ["WESTON_DATA_DIR"] = str(prefix / "share/weston")
    config.write_text(f"[shell]\nclient={prefix}/libexec/weston-desktop-shell\n"
                      f"[input-method]\npath={prefix}/libexec/weston-keyboard\n")
else:
    config.write_text("[shell]\n")
log = (runtime / "weston.log").open("w+")
weston = subprocess.Popen([os.environ["WESTON_BINARY"], "--backend=x11-backend.so", "--shell=desktop-shell.so",
                           "--use-pixman", "--socket=recharge-test", "--idle-time=0", "--config=" + str(config)],
                          env=dict(os.environ, DISPLAY=os.environ["WESTON_TEST_X11_DISPLAY"]),
                          stdout=log, stderr=log)
fixture = None
try:
    wait_for(lambda: (runtime / "recharge-test").exists())
    from recharge_ai_task import tray_backend
    tray_backend.prepare_backend()
    assert os.environ["PYSTRAY_BACKEND"] == "appindicator"
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, Gdk, GLib, Gio
    assert Gtk.init_check()[0]
    assert Gdk.Display.get_default().__gtype__.name == "GdkWaylandDisplay"
    import pystray
    assert pystray.Icon.__module__ == "pystray._appindicator"
    from recharge_ai_task.scoped_accessibility import ApplicationBus
    from recharge_ai_task import wayland_input, targets
    with_bus = ApplicationBus()
    source = '''
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk,GLib,Gdk
w=Gtk.Window(title="Private Wayland AI fixture")
w.set_default_size(480,240)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
text=Gtk.TextView()
button=Gtk.Button(label="Send")
def send(*_):
    b=text.get_buffer()
    message=b.get_text(b.get_start_iter(),b.get_end_iter(),True)
    assert message=="Continue — ää\\n第二行", repr(message)
    b.set_text("")
    print("sent",flush=True)
button.connect("clicked",send)
box.pack_start(text,True,True,0)
box.pack_start(button,False,False,0)
w.add(box)
w.show_all()
assert Gdk.Display.get_default().__gtype__.name=="GdkWaylandDisplay"
GLib.timeout_add(250,lambda:print("ready",flush=True) or False)
Gtk.main()
'''
    fixture = subprocess.Popen([sys.executable, "-c", source], stdout=subprocess.PIPE, text=True,
                               env=dict(os.environ, GTK_MODULES="atk-bridge", AT_SPI_BUS_ADDRESS=with_bus.address))
    assert select.select([fixture.stdout], [], [], 8)[0]
    assert fixture.stdout.readline().strip() == "ready"
    # The fixture is Python, not an AI provider. Restrict inventory to precisely
    # this test PID; actual DBus owner and frame identity checks still run.
    wayland_input.provider_pids = lambda provider: [fixture.pid]
    def inventory():
        try: return targets.discover_windows()
        except RuntimeError: return None
    windows = wait_for(inventory)
    assert len(windows) == 1 and windows[0].pid == fixture.pid
    from recharge_ai_task.target_delivery import deliver_targets
    result, = deliver_targets(windows, "Continue — ää\n第二行")
    assert result.success, result.detail
    assert select.select([fixture.stdout], [], [], 5)[0]
    assert fixture.stdout.readline().strip() == "sent"
    # Exercise the dashboard's actual widget tree on a native Wayland surface.
    from recharge_ai_task import target_ui
    target_ui.discover_targets = lambda **_: targets.Inventory()
    target_ui.TargetPicker.poll_runtime = lambda *_: False
    target_ui.TargetPicker.refresh_quota = lambda *_: None
    window = target_ui.TargetPicker(quit_on_close=False)
    window.show_all()
    def pump():
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        return window.get_mapped()
    wait_for(pump)
    window.resize(800, 600)
    for _ in range(10): pump(); time.sleep(.02)
    assert window.get_window().__gtype__.name == "GdkWaylandWindow"
    assert window.workspace_split.get_child1().get_allocated_width() > 0
    window.destroy()
    while Gtk.events_pending(): Gtk.main_iteration_do(False)
    with_bus.close()
    # A private StatusNotifier host proves the tray registers over D-Bus rather
    # than silently creating an invisible legacy Gtk.StatusIcon on Wayland.
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    interface = Gio.DBusNodeInfo.new_for_xml('''
<node><interface name="org.kde.StatusNotifierWatcher">
<method name="RegisterStatusNotifierItem"><arg type="s" direction="in"/></method>
<property name="IsStatusNotifierHostRegistered" type="b" access="read"/>
<property name="RegisteredStatusNotifierItems" type="as" access="read"/>
<property name="ProtocolVersion" type="i" access="read"/>
</interface></node>''').interfaces[0]
    registered = []
    def register(_connection, sender, _path, _interface, _method, params, invocation):
        registered.append((sender, params.unpack()[0]))
        invocation.return_value(None)
    def property_value(_connection, _sender, _path, _interface, name):
        return {"IsStatusNotifierHostRegistered": GLib.Variant("b", True),
                "RegisteredStatusNotifierItems": GLib.Variant("as", []),
                "ProtocolVersion": GLib.Variant("i", 0)}[name]
    registration = connection.register_object("/StatusNotifierWatcher", interface, register, property_value, None)
    owner = Gio.bus_own_name_on_connection(connection, "org.kde.StatusNotifierWatcher",
                                          Gio.BusNameOwnerFlags.NONE, None, None)
    notification_interface = Gio.DBusNodeInfo.new_for_xml('''
<node><interface name="org.freedesktop.Notifications">
<method name="CloseNotification"><arg type="u" direction="in"/></method>
</interface></node>''').interfaces[0]
    # pystray closes notifications synchronously while stopping its main loop.
    # Serve that desktop endpoint on a separate context to avoid a self-call.
    notification_context = GLib.MainContext.new()
    notification_loop = GLib.MainLoop.new(notification_context, False)
    notification_ready = threading.Event()
    def notifications():
        notification_context.push_thread_default()
        endpoint = Gio.DBusConnection.new_for_address_sync(os.environ["DBUS_SESSION_BUS_ADDRESS"],
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        token = endpoint.register_object("/org/freedesktop/Notifications", notification_interface,
            lambda _c, _s, _p, _i, _m, _a, invocation: invocation.return_value(None), None, None)
        notification_owner = Gio.bus_own_name_on_connection(endpoint, "org.freedesktop.Notifications",
            Gio.BusNameOwnerFlags.NONE, lambda *_: notification_ready.set(), None)
        notification_loop.run()
        Gio.bus_unown_name(notification_owner)
        endpoint.unregister_object(token)
        endpoint.close_sync(None)
        notification_context.pop_thread_default()
    notification_thread = threading.Thread(target=notifications, daemon=True)
    notification_thread.start()
    assert notification_ready.wait(3)
    for _ in range(5):
        while Gtk.events_pending(): Gtk.main_iteration_do(False)
        time.sleep(.02)
    from recharge_ai_task.tray import TrayApp
    app = TrayApp()
    def stop():
        app.exit_app(app._icon)
        return False
    GLib.timeout_add(1000, stop)
    app.run(show_gui=True)
    assert app._icon.__class__.__module__ == "pystray._appindicator"
    assert registered, "Wayland tray never registered with the StatusNotifier host"
    binary = os.environ.get("RECHARGE_AI_TASK_PACKAGED_BINARY")
    if binary:
        from recharge_ai_task import tray_control
        previous_config = os.environ.get("RECHARGE_AI_TASK_CONFIG_DIR")
        os.environ["RECHARGE_AI_TASK_CONFIG_DIR"] = str(runtime / "packaged-config")
        packaged_log = (runtime / "packaged.log").open("w+")
        process = subprocess.Popen([binary, "--tray"], stdout=packaged_log, stderr=packaged_log,
            start_new_session=True, env=dict(os.environ, GTK_MODULES="atk-bridge", AT_SPI_BUS_ADDRESS=with_bus.address))
        try:
            def ready():
                # Pump the private host while libappindicator registers.
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                try: return tray_control.request()
                except (OSError, RuntimeError): return None
            wait_for(ready)
            tray_control.request("open-gui")
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
                peer.connect(str(tray_control.control_path()))
                pid, _uid, _gid = struct.unpack("3i", peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            with_bus = ApplicationBus()
            def packaged_frame():
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                try: return wayland_input.frames(with_bus, pid)
                except RuntimeError: return None
            assert wait_for(packaged_frame)[0].name == "Recharge AI-task"
            def packaged_tray():
                while Gtk.events_pending(): Gtk.main_iteration_do(False)
                return len(registered) >= 2
            wait_for(packaged_tray)
            with_bus.close()
            print("packaged native Wayland checks passed", flush=True)
        finally:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=5)
            packaged_log.seek(0)
            print(packaged_log.read(), file=sys.stderr)
            packaged_log.close()
            if previous_config is None: os.environ.pop("RECHARGE_AI_TASK_CONFIG_DIR", None)
            else: os.environ["RECHARGE_AI_TASK_CONFIG_DIR"] = previous_config
    connection.unregister_object(registration)
    Gio.bus_unown_name(owner)
    notification_loop.quit()
    notification_thread.join(timeout=3)
    print("native Wayland checks passed", flush=True)
finally:
    if fixture is not None:
        fixture.terminate()
        fixture.wait(timeout=5)
    weston.terminate()
    weston.wait(timeout=5)
    log.seek(0)
    print(log.read(), file=sys.stderr)
    log.close()
