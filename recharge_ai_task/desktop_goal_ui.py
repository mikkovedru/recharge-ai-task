"""Native Codex Goal controls on Linux; never type into a chat composer."""
from __future__ import annotations

from contextlib import closing
import ctypes
import json
import subprocess
import signal
import sys
import time
import uuid
from urllib.parse import quote, urlparse, unquote

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gdk, Gtk
from .scoped_accessibility import ApplicationBus, AccessibilityUnavailable
from Xlib import display


class ClipboardSnapshot:
    """Preserve all clipboard formats, including HTML/images, through Mint's manager."""
    def __init__(self):
        self.clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        with closing(display.Display()) as connection:
            if not connection.get_selection_owner(connection.intern_atom("CLIPBOARD_MANAGER")):
                raise RuntimeError("Native Goal controls need a running clipboard manager to preserve your clipboard")
        available, targets = self.clipboard.wait_for_targets()
        self.data = []
        for target in targets if available else []:
            if target.name() in {"TARGETS", "MULTIPLE", "TIMESTAMP", "SAVE_TARGETS"}:
                continue
            value = self.clipboard.wait_for_contents(target)
            if value is None or value.get_length() < 0:
                raise RuntimeError("Could not preserve the clipboard; no Goal action sent")
            self.data.append((target.name(), value.get_data_type().name(), value.get_format(), bytes(value.get_data())))
        if sum(len(row[3]) for row in self.data) > 16*1024*1024:
            raise RuntimeError("Clipboard exceeds the preservation limit; no Goal action sent")

    def restore(self):
        if not self.data:
            self.clipboard.set_text("", -1)
            self.clipboard.store()
            return
        # PyGObject does not expose gtk_clipboard_set_with_data's callback API.
        # Keep callback objects and backing bytes alive until store() completes.
        gtk = ctypes.CDLL("libgtk-3.so.0")
        gdk = ctypes.CDLL("libgdk-3.so.0")
        class Entry(ctypes.Structure):
            _fields_ = [("target", ctypes.c_char_p), ("flags", ctypes.c_uint), ("info", ctypes.c_uint)]
        callback_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p)
        clear_type = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
        gdk.gdk_atom_intern.argtypes = [ctypes.c_char_p, ctypes.c_int]
        gdk.gdk_atom_intern.restype = ctypes.c_void_p
        gtk.gtk_selection_data_set.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        def provide(_clipboard, selection, info, _data):
            _target, kind, bits, value = self.data[info]
            gtk.gtk_selection_data_set(selection, gdk.gdk_atom_intern(kind.encode(), 0), bits, value, len(value))
        self._provide = callback_type(provide)
        self._clear = clear_type(lambda *_: None)
        self._entries = (Entry * len(self.data))(*(Entry(row[0].encode(), 0, i) for i, row in enumerate(self.data)))
        gtk.gtk_clipboard_set_with_data.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry), ctypes.c_uint, callback_type, clear_type, ctypes.c_void_p]
        gtk.gtk_clipboard_set_with_data.restype = ctypes.c_int
        if not gtk.gtk_clipboard_set_with_data(hash(self.clipboard), self._entries, len(self.data), self._provide, self._clear, None):
            raise RuntimeError("Could not restore clipboard contents")
        gtk.gtk_clipboard_set_can_store.argtypes = [ctypes.c_void_p, ctypes.POINTER(Entry), ctypes.c_int]
        gtk.gtk_clipboard_set_can_store(hash(self.clipboard), self._entries, len(self.data))
        self.clipboard.store()


def nodes(node, depth=0):
    if depth > 45:
        return
    yield node
    for child in node:
        if child is not None:
            yield from nodes(child, depth+1)


def active_window(pid):
    with closing(display.Display()) as connection:
        value = connection.screen().root.get_full_property(connection.intern_atom("_NET_ACTIVE_WINDOW"), 0)
        if value is None or not value.value[0]:
            raise RuntimeError("Codex is not the active window; no Goal action sent")
        xid = int(value.value[0])
        window = connection.create_resource_object("window", xid)
        owner = window.get_full_property(connection.intern_atom("_NET_WM_PID"), 0)
        if owner is None or int(owner.value[0]) != pid:
            raise RuntimeError("Another application has focus; no Goal action sent")
        return xid


_application_bus = None


def accessibility_bus():
    global _application_bus
    if _application_bus is None:
        _application_bus = ApplicationBus()
    return _application_bus


def preflight_accessibility(pid):
    """Retry read-only registration once, before clipboard or focus effects."""
    global _application_bus
    for attempt in range(2):
        try:
            return accessibility_bus().application(pid)
        except AccessibilityUnavailable:
            if _application_bus is not None:
                _application_bus.close()
            _application_bus = None
            if attempt:
                raise
            time.sleep(.1)


def visible_frame(pid):
    global _application_bus
    for attempt in range(2):
        active_window(pid)
        try:
            app = accessibility_bus().application(pid)
            frames = [frame for frame in app if frame.getState().contains(Atspi.StateType.ACTIVE)]
            if len(frames) != 1:
                raise RuntimeError("Could not identify the active Codex window; no Goal action sent")
            return frames[0]
        except AccessibilityUnavailable:
            if _application_bus is not None:
                _application_bus.close()
            _application_bus = None
            if attempt:
                raise
            time.sleep(.1)


def wait_for(check, timeout=3):
    deadline = time.monotonic()+timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(.05)
    raise RuntimeError("Codex's native control was not available; no Goal action sent")


def sidebar_rows(frame):
    return [node for node in nodes(frame) if node.getRoleName() == "push button"
            and any("sidebar-item" in value for value in node.getAttributes())]


def current_chat_id(pid):
    frame = visible_frame(pid)
    selected = [row for row in sidebar_rows(frame) if "current:page" in row.getAttributes()]
    if len(selected) != 1:
        raise RuntimeError("Could not identify the selected Codex sidebar chat; no Goal action sent")
    return row_chat_id(pid, selected[0])


def row_chat_id(pid, row):
    frame = visible_frame(pid)
    active_window(pid)
    component = row.queryComponent()
    if not row.getState().contains(Atspi.StateType.SHOWING):
        if not component.scrollTo(Atspi.ScrollType.ANYWHERE):
            raise RuntimeError("Could not scroll the selected chat into view; no Goal action sent")
        wait_for(lambda: row.getState().contains(Atspi.StateType.SHOWING))
    bounds = component.getExtents(Atspi.CoordType.SCREEN)
    if bounds.width <= 0 or bounds.height <= 0:
        raise RuntimeError("The selected Codex chat is not visible in its sidebar")
    subprocess.run(["xdotool", "mousemove", str(bounds.x+bounds.width-12), str(bounds.y+bounds.height//2)], check=True, timeout=5)
    def named(parent, role, name):
        matches = [node for node in nodes(parent) if node.getRoleName() == role and node.name == name
                   and node.getState().contains(Atspi.StateType.SHOWING)]
        return matches[0] if len(matches) == 1 else None
    action = None
    try:
        action = wait_for(lambda: named(row.parent, "push button", "Chat actions"))
        active_window(pid)
        if not action.queryAction().doAction(0):
            raise RuntimeError("Could not open the selected chat's actions")
        menu = wait_for(lambda: named(frame, "menu", "Chat actions"))
        copy = named(menu, "menu item", "Copy")
        if copy is None or "haspopup:menu" not in copy.getAttributes():
            raise RuntimeError("Codex does not expose its native Copy submenu")
        # Hover a verified submenu; never activate Copy or Copy as Markdown.
        bounds = copy.queryComponent().getExtents(Atspi.CoordType.SCREEN)
        active_window(pid)
        subprocess.run(["xdotool", "mousemove", str(bounds.x+bounds.width//2), str(bounds.y+bounds.height//2)], check=True, timeout=5)
        submenu = wait_for(lambda: named(frame, "menu", "Copy"))
        link = named(submenu, "menu item", "Copy deeplink")
        if link is None:
            raise RuntimeError("Codex does not expose its Copy deeplink action")
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text("recharge-ai-task-verification:" + str(uuid.uuid4()), -1)
        active_window(pid)
        if not link.queryAction().doAction(0):
            raise RuntimeError("Codex did not copy its chat identity")
        def identity():
            parsed = urlparse(clipboard.wait_for_text() or "")
            return unquote(parsed.path.lstrip("/")) if parsed.scheme == "codex" and parsed.netloc == "threads" else None
        return wait_for(identity)
    finally:
        try:
            active_window(pid)
            # Copy deeplink normally closes both menus. Escape in the main
            # window cancels a turn and can pause a just-resumed goal. Never
            # send keyboard cleanup; toggle the expanded native trigger only.
            if (action is not None and action.getState().contains(Atspi.StateType.EXPANDED)
                    and (named(frame, "menu", "Chat actions") or named(frame, "menu", "Copy"))):
                action.queryAction().doAction(0)
        except RuntimeError:
            pass  # Leave a menu alone if another application gained focus.



def _title_candidate(row, title):
    # Accessible row names may include badges, while a child retains the title.
    expected = " ".join(title.split()).casefold()
    if not expected:
        return False
    for node in nodes(row):
        name = " ".join((node.name or "").split()).casefold()
        if name == expected or node is row and name.startswith(expected + " "):
            return True
    return False


def _expand_project(frame, target, pid):
    if not target.project_name:
        return False
    projects = [row for row in sidebar_rows(frame) if row.name == target.project_name
                and row.getState().contains(Atspi.StateType.EXPANDABLE)]
    if len(projects) != 1 or projects[0].getState().contains(Atspi.StateType.EXPANDED):
        return False
    active_window(pid)
    if not projects[0].queryAction().doAction(0):
        raise RuntimeError("Could not expand the selected chat's project")
    return True


def show_chat(target, pid):
    """Wait for canonical-ID navigation, retaining exact-ID sidebar fallback."""
    preflight_accessibility(pid)  # Verify registration before opening a chat.
    link = "codex://threads/" + quote(target.id, safe="")
    subprocess.run(["xdg-open", link], check=True, capture_output=True, timeout=8)
    # xdg-open acknowledges dispatch, not completed navigation. Re-read the
    # active frame and sidebar after loading/project expansion on every pass.
    deadline = time.monotonic() + 10
    last_error = "the selected chat has not appeared in the desktop"
    while time.monotonic() < deadline:
        try:
            frame = visible_frame(pid)
            try:
                if current_chat_id(pid) == target.id:
                    return visible_frame(pid)
            except (InterruptedError, AccessibilityUnavailable):
                raise
            except Exception as exc:
                last_error = str(exc)
            candidates = [row for row in sidebar_rows(frame) if _title_candidate(row, target.title)]
            if not candidates and _expand_project(frame, target, pid):
                time.sleep(.1)
                continue
            for row in candidates:
                if time.monotonic() >= deadline:
                    break
                try:
                    identity = row_chat_id(pid, row)
                except (InterruptedError, AccessibilityUnavailable):
                    raise
                except Exception as exc:
                    last_error = str(exc)
                    continue
                if identity != target.id:
                    last_error = "same-title sidebar candidates have different chat IDs"
                    continue
                active_window(pid)
                if not row.queryAction().doAction(0):
                    raise RuntimeError("Could not open the verified Codex chat; no Goal action sent")
                # The row click is asynchronous too. A fresh pass verifies the
                # canonical selection; its label alone never authorizes a Goal.
                time.sleep(.1)
                break
        except (InterruptedError, AccessibilityUnavailable):
            raise
        except Exception as exc:
            last_error = str(exc)
        time.sleep(.05)
    detail = last_error.replace("; no Goal action sent", "")
    raise RuntimeError(f"Could not open the exact selected chat ID {target.id}: {detail}; no Goal action sent")


def resume_goal(target, expected, pid):
    from .goal_control import NativeGoals
    from .recovery_rules import goal_allowed
    if not goal_allowed(expected.get("status"), manual=True):
        raise RuntimeError("This Goal state cannot be resumed")
    # A reachable bus does not imply Codex rejoined it after a bus restart.
    # Check the verified process before clipboard or navigation side effects.
    preflight_accessibility(pid)
    snapshot = ClipboardSnapshot()
    clicked = False
    try:
        frame = show_chat(target, pid)
        with NativeGoals(target.instance) as goals:
            current = goals.get(target.id)
            if current is None or any(current.get(k) != expected.get(k) for k in ("threadId", "createdAt", "objective", "status", "tokenBudget")):
                raise RuntimeError("Goal changed before native activation; no Goal action sent")
        buttons = [node for node in nodes(frame) if node.getRoleName() == "push button"
                   and node.name == "Resume goal" and node.getState().contains(Atspi.StateType.SHOWING)
                   and node.getState().contains(Atspi.StateType.ENABLED)]
        if len(buttons) != 1:
            raise RuntimeError("The selected chat has no unique native Resume goal button; no Goal action sent")
        if current_chat_id(pid) != target.id:
            raise RuntimeError("The visible Codex chat changed; no Goal action sent")
        clicked = True
        if not buttons[0].queryAction().doAction(0):
            raise RuntimeError("Codex did not acknowledge its native Goal control")
        deadline = time.monotonic()+5
        while time.monotonic() < deadline:
            frame = visible_frame(pid)
            if any(node.getRoleName() == "push button" and node.name == "Pause goal"
                   and node.getState().contains(Atspi.StateType.SHOWING) for node in nodes(frame)):
                if current_chat_id(pid) != target.id:
                    raise RuntimeError("Chat changed after native Goal activation")
                return
            time.sleep(.1)
        raise RuntimeError("Codex's Goal button did not become active")
    except Exception as exc:
        if clicked:
            detail = str(exc).replace("; no Goal action sent", "")
            exc = RuntimeError(f"Resume goal was invoked, but verification failed: {detail}. The goal may already be running; no prompt was sent")
        exc.goal_clicked = clicked
        raise exc
    finally:
        try:
            snapshot.restore()
        except Exception as exc:
            exc.goal_clicked = clicked
            raise


def main():
    from .targets import Target
    def interrupted(*_):
        raise InterruptedError("Native Goal control interrupted; check this chat")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        payload = json.loads(sys.stdin.read(65536))
        resume_goal(Target.from_dict(payload["target"]), payload["goal"], payload["pid"])
        result = {"success": True}
    except Exception as exc:
        result = {"success": False, "detail": str(exc), "uncertain": getattr(exc, "goal_clicked", False)}
    print(json.dumps(result), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
