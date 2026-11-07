"""Session selection and native accessibility delivery; no user chat mutations."""
import os
import select
from pathlib import Path
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from recharge_ai_task import display_session, targets, wayland_input


@pytest.mark.parametrize("session,socket,expected", [
    ("wayland", "wayland-0", True), ("wayland", "", True),
    ("", "wayland-1", True), ("x11", "wayland-1", False), ("x11", "", False), ("", "", False)])
def test_session_detection(monkeypatch, session, socket, expected):
    monkeypatch.setattr(display_session.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", session)
    monkeypatch.setenv("WAYLAND_DISPLAY", socket)
    assert display_session.is_wayland() is expected


def test_wayland_tray_does_not_choose_cinnamon_xembed(monkeypatch):
    from recharge_ai_task import tray_backend
    monkeypatch.setattr(display_session.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "X-Cinnamon")
    monkeypatch.delenv("PYSTRAY_BACKEND", raising=False)
    tray_backend.prepare_backend()
    assert os.environ["PYSTRAY_BACKEND"] == "appindicator"
    default = object()
    assert tray_backend.icon_class(default) is default


def test_native_discovery_needs_no_display(monkeypatch):
    monkeypatch.setattr(display_session.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("DISPLAY", raising=False)
    expected = [targets.Target("window", ":1.2/frame", "Fixture", instance="atspi:bus:42", pid=42)]
    monkeypatch.setattr(wayland_input, "discover_windows", lambda provider: expected)
    assert targets.discover_windows() == expected


def test_wayland_legacy_typing_never_uses_xdotool(monkeypatch):
    from recharge_ai_task import desktop_input
    monkeypatch.setattr(display_session.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setattr(desktop_input.subprocess, "run", lambda *_a, **_k: pytest.fail("Global input"))
    assert not desktop_input._send_linux("hello", ("Codex",), 1, .1)


@pytest.mark.parametrize("accessibility_error", [False, True])
def test_xwayland_window_keeps_its_existing_input_path(monkeypatch, accessibility_error):
    monkeypatch.setattr(display_session.sys, "platform", "linux")
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":fixture")
    compatibility = targets.Target("window", "42", "XWayland", instance=":fixture:123", pid=123)
    native = targets.Target("window", ":1.2/frame", "Native", instance="atspi:bus:123", pid=123)
    def accessible(_provider):
        if accessibility_error: raise RuntimeError("Accessibility disabled")
        return [native]
    monkeypatch.setattr(wayland_input, "discover_windows", accessible)
    original = targets.discover_windows
    monkeypatch.setattr(targets, "discover_windows", lambda provider="codex", **kw:
                        [compatibility] if kw.get("x11") else original(provider))
    assert targets.discover_windows() == [compatibility]


def test_goal_without_xwayland_fails_before_spawning(monkeypatch):
    if sys.platform != "linux":
        pytest.skip("Linux Goal helper")
    from recharge_ai_task import desktop_goal
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.setattr(desktop_goal.subprocess, "Popen", lambda *_a, **_k: pytest.fail("Helper spawned"))
    with pytest.raises(RuntimeError, match="XWayland"):
        desktop_goal.activate(None, None, None)


def test_xwayland_goal_backend_is_isolated_to_the_helper(monkeypatch):
    if sys.platform != "linux":
        pytest.skip("Linux Goal helper")
    from contextlib import nullcontext
    import struct
    from recharge_ai_task import desktop_goal
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.setenv("DISPLAY", ":fixture")
    monkeypatch.setenv("GDK_BACKEND", "wayland")
    monkeypatch.setattr(desktop_goal, "ui_lock", nullcontext)
    calls = []
    def launch(command, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(communicate=lambda *_a, **_k: ('{"success":true}', ""), returncode=0)
    monkeypatch.setattr(desktop_goal.subprocess, "Popen", launch)
    desktop = SimpleNamespace(socket=SimpleNamespace(getsockopt=lambda *_:
                              struct.pack("3i", 42, os.getuid(), os.getgid())))
    desktop_goal.activate(targets.Target("thread", "fixture", "Fixture"), {}, desktop)
    assert calls[0]["env"]["GDK_BACKEND"] == "x11"
    assert os.environ["GDK_BACKEND"] == "wayland"


@pytest.fixture
def accessibility(monkeypatch):
    pytest.importorskip("gi")
    from recharge_ai_task import scoped_accessibility as api
    from gi.repository import Atspi
    class Node:
        owner = ":1.42"
        def __init__(self, path, *, name="", role="text", states=(), interfaces=(), children=()):
            self.path, self.name, self.role = path, name, role
            self.states, self.interfaces, self.children = set(states), interfaces, children
            self.text, self.edits, self.clicks = "", [], []
        def __iter__(self): return iter(self.children)
        def getState(self): return SimpleNamespace(contains=lambda state: state in self.states)
        def getRoleName(self): return self.role
        def get_interfaces(self): return self.interfaces
        def get_text(self): return self.text
        def set_text(self, text):
            self.edits.append(text)
            self.text = text
            return True
        def queryAction(self): return self
        def doAction(self, index):
            self.clicks.append(index)
            return True
    visible = Atspi.StateType.SHOWING
    composer = Node("/composer", states=(visible, Atspi.StateType.ENABLED, Atspi.StateType.EDITABLE, Atspi.StateType.MULTI_LINE),
                    interfaces=("org.a11y.atspi.EditableText",))
    button = Node("/send", name="Send", role="push button", states=(visible, Atspi.StateType.ENABLED),
                  interfaces=("org.a11y.atspi.Action",))
    frame = Node("/frame", name="Fixture", role="frame", states=(visible,), children=(composer, button))
    class Bus:
        owner = ":1.42"
        def close(self): pass
        def call(self, *_a): return ("test-bus",)
        def application(self, pid):
            assert pid == 42
            return [frame]
    bus = Bus()
    monkeypatch.setattr(api, "ApplicationBus", lambda: bus)
    monkeypatch.setattr(wayland_input, "provider_pids", lambda _provider: [42])
    target = wayland_input.window_target(bus, frame, 42, "codex")
    return SimpleNamespace(composer=composer, button=button, frame=frame, bus=bus, target=target)


def test_scoped_multiline_unicode_delivery(accessibility):
    a = accessibility
    assert wayland_input.discover_windows("codex") == [a.target]
    wayland_input.send_window(a.target, "Continue — ää\n第二行")
    assert a.composer.edits == ["Continue — ää\n第二行"]
    assert a.button.clicks == [0]


@pytest.mark.parametrize("changed", ["draft", "disabled", "single-line", "ambiguous", "stale-bus", "stale-window", "missing-send"])
def test_native_delivery_refuses_unsafe_composer(accessibility, changed):
    from dataclasses import replace
    a = accessibility
    from gi.repository import Atspi
    if changed == "draft": a.composer.text = "Unsent draft"
    if changed == "disabled": a.composer.states.remove(Atspi.StateType.ENABLED)
    if changed == "missing-send": a.button.name = "Another action"
    if changed == "single-line": a.composer.states.remove(Atspi.StateType.MULTI_LINE)
    if changed == "ambiguous":
        import copy
        other = copy.copy(a.composer)
        other.path = "/other"
        a.frame.children = (a.composer, other, a.button)
    if changed == "stale-bus": a.target = replace(a.target, instance="atspi:old-bus:42")
    if changed == "stale-window": a.target = replace(a.target, id=":1.99/frame")
    with pytest.raises(RuntimeError): wayland_input.send_window(a.target, "Continue")
    assert a.composer.edits == a.button.clicks == []


def test_failure_after_edit_is_uncertain_and_never_retried(accessibility, monkeypatch):
    a = accessibility
    monkeypatch.setattr(a.button, "doAction", lambda _: (_ for _ in ()).throw(RuntimeError("disconnected")))
    from recharge_ai_task.target_delivery import deliver_targets
    result, = deliver_targets([a.target], "Continue")
    assert not result.success and result.uncertain and not result.retryable
    assert a.composer.edits == ["Continue"]


def test_native_wayland_session(tmp_path):
    weston = os.environ.get("WESTON_BINARY") or shutil.which("weston")
    xvfb = os.environ.get("XVFB_BINARY") or shutil.which("Xvfb")
    if os.environ.get("RECHARGE_AI_TASK_WAYLAND_TESTS") != "1" or not weston or not xvfb:
        pytest.skip("Set RECHARGE_AI_TASK_WAYLAND_TESTS=1; needs Weston, Xvfb, GTK and dbus-run-session")
    runtime = tmp_path / "runtime"
    runtime.mkdir(mode=0o700)
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), XDG_SESSION_TYPE="wayland",
               GDK_BACKEND="wayland", WAYLAND_DISPLAY="recharge-test", WESTON_BINARY=weston,
               HOME=str(tmp_path), GIO_USE_VFS="local", PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    for name in ("DISPLAY", "PYSTRAY_BACKEND", "NO_AT_BRIDGE", "AT_SPI_BUS_ADDRESS"):
        env.pop(name, None)
    # Xvfb supplies the compositor's private input seat. All application clients
    # receive only a Wayland socket: no DISPLAY, XWayland or global X11 input.
    server = subprocess.Popen([xvfb, "-displayfd", "1", "-screen", "0", "1440x1000x24",
                               "-nolisten", "tcp", "-ac"], stdout=subprocess.PIPE, text=True)
    try:
        assert select.select([server.stdout], [], [], 5)[0]
        display_number = server.stdout.readline().strip()
        assert display_number.isdigit()
        env["WESTON_TEST_X11_DISPLAY"] = ":" + display_number
        result = subprocess.run(["dbus-run-session", "--", sys.executable,
                                 str(Path(__file__).with_name("wayland_session_fixture.py"))],
                                env=env, capture_output=True, text=True, timeout=50)
    finally:
        server.terminate()
        server.wait(timeout=5)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "native Wayland checks passed" in result.stdout
