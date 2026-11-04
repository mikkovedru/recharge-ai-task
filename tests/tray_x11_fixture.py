"""Separate native tray manager/client for isolated Xephyr regression tests."""
import json
import os
import sys
import time


def manager(size):
    from Xlib import X, display, protocol
    connection = display.Display()
    root = connection.screen().root
    owner = root.create_window(0, 0, 1, 1, 0, X.CopyFromParent)
    owner.set_selection_owner(connection.intern_atom('_NET_SYSTEM_TRAY_S0'), X.CurrentTime)
    connection.sync()
    print(json.dumps({'ready': True}), flush=True)
    hosts = []
    while True:
        event = connection.next_event()
        if event.type == X.ConfigureRequest:
            event.window.configure(x=0, y=0, width=size, height=size, border_width=0)
            reply = protocol.event.ConfigureNotify(event=event.window, window=event.window,
                x=0, y=0, width=size, height=size, border_width=0,
                above_sibling=X.NONE, override=False)
            event.window.send_event(reply, event_mask=X.StructureNotifyMask)
            connection.flush()
            continue
        if event.type == X.MapRequest:
            event.window.map();connection.flush();continue
        if event.type != X.ClientMessage or event.client_type != connection.intern_atom('_NET_SYSTEM_TRAY_OPCODE'):
            continue
        xid = int(event.data[1][2])
        plug = connection.create_resource_object('window', xid)
        host = root.create_window(0, 0, size, size, 0, X.CopyFromParent, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
        hosts.append(host)
        plug.change_save_set(X.SetModeInsert)
        plug.reparent(host, 0, 0)
        plug.configure(width=size, height=size)
        host.map(); plug.map()
        message = protocol.event.ClientMessage(window=plug,
            client_type=connection.intern_atom('_XEMBED'), data=(32, [0, 0, 0, host.id, 0]))
        plug.send_event(message)
        connection.flush()


def client():
    from types import SimpleNamespace
    from recharge_ai_task import tray, target_ui
    from recharge_ai_task.tray_gtk import CinnamonGtkIcon
    from recharge_ai_task.config import AppConfig
    from recharge_ai_task.targets import Inventory, Target
    from gi.repository import GLib
    from pystray._util import gtk
    # No real desktop state, quota, notifications, login edits or chat delivery.
    tray.is_autostart_enabled = lambda: False
    tray.icon_class = lambda _: CinnamonGtkIcon
    tray.discover_codex = target_ui.discover_codex = lambda _: 'fixture'
    target_ui.discover_targets = lambda: Inventory([])
    target_ui.fetch_quota = lambda _: (_ for _ in ()).throw(RuntimeError('offline fixture'))
    gtk.notify_dbus.Notifier = lambda: SimpleNamespace(hide=lambda: None)
    def watch(config, stop):
        stop.wait(300)
        return 0
    tray.run_desktop_watch = watch
    AppConfig(desktop_targets=[Target('thread', 'fixture', 'Fixture', send_prompt=True, send_goal=False).to_dict()]).save()
    app = tray.TrayApp()
    # Keep the dashboard away from the fake panel so native GetImage can read
    # visible pixels; obscured X11 windows need not retain readable backing.
    open_targets = app.open_targets
    def open_away(*args, **kwargs):
        open_targets(*args, **kwargs)
        def position():
            if app._picker is not None: app._picker.move(80, 80)
            return False
        GLib.timeout_add(100, position)
    app.open_targets = open_away
    def query(_fd, _condition):
        command = sys.stdin.readline().strip()
        if not command:
            app.exit_app(app._icon)
            return False
        try:
            icon = app._icon
            if command == 'break':
                # Simulate an old timeout already removed by GLib and a lost plug.
                if icon._size_timer is not None:
                    source = GLib.MainContext.default().find_source_by_id(icon._size_timer)
                    if source is not None: GLib.source_remove(icon._size_timer)
                if icon._plug is not None: icon._plug.destroy()
            elif command == 'start-watch': app.start_desktop()
            elif command == 'stop':
                app.exit_app(icon)
            plug = icon._plug
            info = {'pid': os.getpid(), 'embedded': bool(plug and plug.get_embedded()),
                'watch': app._is_running(), 'watch_thread': id(app._watch_thread),
                'rendered': icon._rendered_size, 'menu': id(icon._menu_handle),
                'timer': bool(icon._size_timer and GLib.MainContext.default().find_source_by_id(icon._size_timer))}
            if plug is not None:
                window = icon._xdisplay.create_resource_object('window', plug.get_id())
                geometry = window.get_geometry()
                info.update(xid=plug.get_id(), width=geometry.width, height=geometry.height,
                            scale=icon._area.get_scale_factor(), area=[icon._area.get_allocated_width(),icon._area.get_allocated_height()], mapped=icon._area.get_mapped(), visible=plug.get_visible(), parent=window.query_tree().parent.id)
                if info['embedded'] and geometry.width >= 16:
                    from PIL import Image
                    raw = window.get_image(0, 0, geometry.width, geometry.height, 2, 0xffffffff)
                    image = Image.frombytes('RGB', (geometry.width, geometry.height), raw.data, 'raw', 'BGRX')
                    pixels = list(image.getdata())
                    # Every edge must be painted, and blue logo/status must exist.
                    info['corners'] = [image.getpixel(p) for p in ((0,0),(geometry.width-1,0),(0,geometry.height-1),(geometry.width-1,geometry.height-1))]
                    info['blue'] = sum(b > 150 and r < 100 for r,g,b in pixels)
                    info['white'] = sum(min(rgb) > 220 for rgb in pixels)
            print(json.dumps(info), flush=True)
        except Exception as exc:
            print(json.dumps({'error': repr(exc)}), flush=True)
        return True
    GLib.io_add_watch(sys.stdin, GLib.IO_IN | GLib.IO_HUP, query)
    app.run()


if __name__ == '__main__':
    if sys.argv[1] == 'manager': manager(int(sys.argv[2]))
    else: client()
