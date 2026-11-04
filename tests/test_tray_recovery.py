"""Docking return values and callback survival; native tests use Xephyr."""
import os
from types import SimpleNamespace

import pytest

if os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1":
    pytest.skip("Requires GTK/X11", allow_module_level=True)

from recharge_ai_task import tray_gtk


def test_dock_retries_ignored_requests_and_same_owner_socket_loss(monkeypatch):
    sent = []
    owner = SimpleNamespace(id=42, send_event=lambda event: sent.append(event))
    connection = SimpleNamespace(intern_atom=lambda _: 1, get_default_screen=lambda: 0,
        get_selection_owner=lambda _: owner, flush=lambda: None)
    embedded = [False]
    icon = SimpleNamespace(_xdisplay=connection, _owner=None, _last_dock=0,
        _plug=SimpleNamespace(get_embedded=lambda: embedded[0], get_id=lambda: 100))
    clock = [10]
    monkeypatch.setattr(tray_gtk.time, "monotonic", lambda: clock[0])
    # Keep this a routing check; Xlib's ClientMessage expects a real Window.
    monkeypatch.setattr(tray_gtk.protocol.event, "ClientMessage", lambda **kwargs: kwargs)
    dock = lambda: tray_gtk.CinnamonGtkIcon._dock(icon)
    dock(); assert len(sent) == 1
    clock[0] += 1; dock(); assert len(sent) == 1
    clock[0] += 1; dock(); assert len(sent) == 2
    embedded[0] = True
    clock[0] += 5; dock(); assert len(sent) == 2
    embedded[0] = False  # Same manager can replace only its socket.
    dock(); assert len(sent) == 3
    connection.get_selection_owner = lambda _: 0
    dock(); assert icon._owner is None
    connection.get_selection_owner = lambda _: owner
    owner.id = 43; dock(); assert len(sent) == 4


def test_transient_refresh_errors_do_not_remove_the_polling_callback(caplog):
    def unavailable():
        raise RuntimeError("Native window replaced")
    icon = SimpleNamespace(_refresh_once=unavailable, _refresh_error=None, _owner=42)
    assert tray_gtk.CinnamonGtkIcon._refresh(icon) is True
    assert tray_gtk.CinnamonGtkIcon._refresh(icon) is True
    assert icon._owner is None and len(caplog.records) == 1
    icon._refresh_once = lambda: True
    assert tray_gtk.CinnamonGtkIcon._refresh(icon) is True
    assert icon._refresh_error is None
