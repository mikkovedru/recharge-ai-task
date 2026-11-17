"""Address native windows through scoped AT-SPI, without global input injection.

Only same-user provider executables are queried. Window identities include the
accessibility bus ID, unique connection owner and object path, so a restart can
never silently redirect a saved target. Codex chat-ID delivery still uses IPC.
"""
from contextlib import closing
import os
from pathlib import Path
import time

from .codex_ipc import DeliveryUncertain


def provider_pids(provider):
    names = {"claude", "claude-desktop"} if provider == "claude" else {"codex", "chatgpt"}
    found = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            executable = Path(os.readlink(process / "exe")).name.lower().removesuffix(" (deleted)")
            if executable in names:
                found.append(int(process.name))
        except OSError:
            continue
    return found


def window_target(bus, frame, pid, provider):
    from .targets import Target
    from .scoped_accessibility import DBUS
    bus_id = bus.call(DBUS, "/org/freedesktop/DBus", DBUS, "GetId")[0]
    return Target("window", bus.owner + frame.path, frame.name,
                  instance=f"atspi:{bus_id}:{pid}", pid=pid, provider=provider,
                  status="Current chat in this window (accessibility)")


def frames(bus, pid):
    from gi.repository import Atspi
    return [frame for frame in bus.application(pid)
            if frame.getRoleName() == "frame" and frame.getState().contains(Atspi.StateType.SHOWING)]


def discover_windows(provider):
    pids = provider_pids(provider)
    if not pids:
        return []
    from .scoped_accessibility import ApplicationBus, AccessibilityUnavailable
    windows, errors = [], []
    for pid in pids:
        with closing(ApplicationBus()) as bus:
            try:
                windows.extend(window_target(bus, frame, pid, provider) for frame in frames(bus, pid))
            except AccessibilityUnavailable as exc:
                errors.append(str(exc))
    if not windows and errors:
        raise RuntimeError("Wayland window discovery needs native accessibility enabled in the AI app. "
                           "Codex chat-ID and saved CLI session delivery remain available. " + errors[0])
    return windows


def nodes(frame):
    # Bound traversal even if a broken application exposes a cycle or huge tree.
    pending = [(frame, 0)]
    visited = set()
    while pending:
        node, depth = pending.pop()
        identity = (node.owner, node.path)
        if identity in visited:
            continue
        visited.add(identity)
        if len(visited) > 5000 or depth > 45:
            raise RuntimeError("The selected window's accessibility tree is too large")
        yield node
        pending.extend((child, depth + 1) for child in node)


def send_window(target, text):
    from .scoped_accessibility import ApplicationBus
    from gi.repository import Atspi
    if target.pid not in provider_pids(target.provider):
        raise RuntimeError("Selected AI process closed or changed; refresh targets")
    with closing(ApplicationBus()) as bus:
        selected = [frame for frame in frames(bus, target.pid)
                    if window_target(bus, frame, target.pid, target.provider).key == target.key]
        if len(selected) != 1:
            raise RuntimeError("Selected window closed or its ID changed; refresh targets")
        frame = selected[0]

        def showing(node):
            return node.getState().contains(Atspi.StateType.SHOWING)

        # Search boxes and single-line fields must never become composers.
        composers = [node for node in nodes(frame) if showing(node)
                     and node.getState().contains(Atspi.StateType.EDITABLE)
                     and node.getState().contains(Atspi.StateType.ENABLED)
                     and node.getState().contains(Atspi.StateType.MULTI_LINE)
                     and "org.a11y.atspi.EditableText" in node.get_interfaces()]
        if len(composers) != 1:
            raise RuntimeError("Wayland delivery needs one accessible multiline composer in the selected window")
        composer = composers[0]
        if composer.get_text():
            raise RuntimeError("The selected composer contains a draft; no message sent")

        def send_buttons():
            return [node for node in nodes(frame) if showing(node)
                    and node.getRoleName() == "push button"
                    and node.name.strip().casefold() in {"send", "send message", "send prompt", "submit"}
                    and "org.a11y.atspi.Action" in node.get_interfaces()]

        # An empty composer normally disables Send. Verify the control exists
        # before editing, then wait for that same control to become enabled.
        buttons = send_buttons()
        if len(buttons) != 1:
            raise RuntimeError("Wayland delivery needs one accessible Send button; no message entered")
        selected_button = buttons[0]
        # Once editing starts, any failure is uncertain: do not append twice.
        try:
            if not composer.set_text(text) or composer.get_text() != text:
                raise RuntimeError("The AI app did not confirm the message text")
            deadline = time.monotonic() + 3
            while True:
                buttons = send_buttons()
                if (len(buttons) == 1 and buttons[0].path == selected_button.path
                        and buttons[0].getState().contains(Atspi.StateType.ENABLED)):
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError("The AI app has no unique enabled accessible Send button")
                time.sleep(.05)
            if composer.get_text() != text:
                raise RuntimeError("The composer changed before sending")
            if not buttons[0].queryAction().doAction(0):
                raise RuntimeError("The AI app did not acknowledge Send")
        except Exception as exc:
            raise DeliveryUncertain("Wayland window input may have been entered; check its composer before retrying. " + str(exc)) from exc
