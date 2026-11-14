"""Query only the verified application's AT-SPI objects, without global caches.

libatspi desktop discovery primes every application's Cache.GetItems, including
Cinnamon's shell. Use the accessibility bus directly so unrelated applications
receive no accessibility calls. See the Cinnamon investigation in doc/.
"""
from __future__ import annotations

import time
import os
import shlex
from pathlib import Path
from urllib.parse import unquote

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib

ACCESSIBLE = "org.a11y.atspi.Accessible"
ROOT = "/org/a11y/atspi/accessible/root"
DBUS = "org.freedesktop.DBus"
PROPERTIES = "org.freedesktop.DBus.Properties"


class AccessibilityUnavailable(RuntimeError):
    """Unavailable native accessibility, rather than an unverified chat identity."""


class AccessibilityTimeout(RuntimeError):
    """A slow request, without evidence that the connection is unavailable."""


def request_timeout(exc, interface, method, path, timeout_ms):
    return AccessibilityTimeout(
        f"Desktop accessibility request timed out after {timeout_ms / 1000:g}s: "
        f"{interface}.{method} ({path}). A timeout does not mean accessibility "
        f"is disabled. {exc}; no Goal action sent")


def timeout_error(exc):
    return exc.matches(Gio.io_error_quark(), Gio.IOErrorEnum.TIMED_OUT) or any(
        exc.matches(Gio.dbus_error_quark(), code) for code in (Gio.DBusError.NO_REPLY, Gio.DBusError.TIMED_OUT))


def accessibility_launch_hint(pid):
    """Suggest a next-start diagnostic without launching or stopping the app."""
    try:
        executable = os.readlink(Path('/proc') / str(pid) / 'exe')
    except OSError:
        return ''
    if Path(executable).name.lower() not in ('chatgpt', 'codex'):
        return ''
    return ('Next launch to try: ' + shlex.quote(executable) +
            ' --force-renderer-accessibility. This workaround still needs verification after restart. ')


def connection_error(exc, address=""):
    missing = ""
    for candidate in address.split(";"):
        if candidate.startswith("unix:"):
            fields = dict(part.split("=", 1) for part in candidate[5:].split(",") if "=" in part)
            if "path" in fields:
                path = unquote(fields["path"])
                if not Path(path).exists():
                    missing = f" Advertised socket is missing: {path}."
    return AccessibilityUnavailable("Desktop accessibility connection is unavailable." + missing +
        " Restore desktop accessibility (or log out and back in), then retry. " +
        str(exc) + "; no Goal action sent")


def transport_error(exc):
    return any(exc.matches(Gio.io_error_quark(), code) for code in (
        Gio.IOErrorEnum.CLOSED, Gio.IOErrorEnum.BROKEN_PIPE, Gio.IOErrorEnum.CONNECTION_REFUSED,
        Gio.IOErrorEnum.NOT_FOUND)) or exc.matches(Gio.dbus_error_quark(), Gio.DBusError.DISCONNECTED)


class ApplicationBus:
    timeout_ms = 1500

    def __init__(self, *, timeout_ms=1500):
        self.timeout_ms = timeout_ms
        self.owner = None
        self.root = ROOT
        self.connection = None
        self.address = ""
        # A restarted broker can briefly advertise its old socket. Re-read the
        # address once; never restart desktop services or touch global caches.
        for attempt in range(2):
            try:
                session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
                self.address = session.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress",
                    None, GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, self.timeout_ms, None).unpack()[0]
                self.connection = Gio.DBusConnection.new_for_address_sync(self.address,
                    Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
                    None, None)
                return
            except GLib.Error as exc:
                if timeout_error(exc):
                    raise request_timeout(exc, "org.a11y.Bus", "GetAddress", "/org/a11y/bus", self.timeout_ms) from exc
                if attempt:
                    raise connection_error(exc, self.address) from exc
                time.sleep(.1)

    def close(self):
        if self.connection is not None and not self.connection.is_closed():
            try:
                self.connection.close_sync(None)
            except GLib.Error:
                pass

    def call(self, destination, path, interface, method, signature=None, args=()):
        try:
            return self.connection.call_sync(destination, path, interface, method,
                GLib.Variant(signature, args) if signature else None, None,
                Gio.DBusCallFlags.NONE, self.timeout_ms, None).unpack()
        except GLib.Error as exc:
            if timeout_error(exc):
                # Keep a slow but connected transport. Never repeat this call:
                # an action can have arrived even though its reply was late.
                raise request_timeout(exc, interface, method, path, self.timeout_ms) from exc
            if not transport_error(exc):
                raise
            self.close()
            # Never replay a DoAction: it may have arrived before disconnection.
            raise connection_error(exc, self.address) from exc

    def application(self, pid):
        if self.owner is not None:
            try:
                owner_pid = self.call(DBUS, "/org/freedesktop/DBus", DBUS,
                                      "GetConnectionUnixProcessID", "(s)", (self.owner,))[0]
            except GLib.Error as exc:
                if not exc.matches(Gio.dbus_error_quark(), Gio.DBusError.NAME_HAS_NO_OWNER):
                    raise
                self.owner = None
            else:
                if owner_pid != pid:
                    raise RuntimeError("The verified Codex accessibility process changed; no Goal action sent")
                return Accessible(self, self.owner, self.root)
        try:
            references = self.call("org.a11y.atspi.Registry", ROOT, ACCESSIBLE, "GetChildren")[0]
        except GLib.Error as exc:
            if not any(exc.matches(Gio.dbus_error_quark(), code) for code in (
                    Gio.DBusError.SERVICE_UNKNOWN, Gio.DBusError.NAME_HAS_NO_OWNER,
                    Gio.DBusError.SPAWN_SERVICE_NOT_FOUND, Gio.DBusError.SPAWN_EXEC_FAILED,
                    Gio.DBusError.SPAWN_CHILD_EXITED)):
                raise
            raise AccessibilityUnavailable(
                "The desktop accessibility registry is unavailable. Restore desktop accessibility "
                "(or log out and back in), then reopen Codex and retry; no Goal action sent") from exc
        matches = []
        for destination, path in references:
            try:
                owner_pid = self.call(DBUS, "/org/freedesktop/DBus", DBUS,
                                      "GetConnectionUnixProcessID", "(s)", (destination,))[0]
            except GLib.Error:
                continue  # An application exited since the registry snapshot.
            if owner_pid == pid:
                matches.append((destination, path))
        if not matches:
            raise AccessibilityUnavailable(
                "Codex is not registered on the current desktop accessibility bus. "
                "Recharge cannot read the native Resume goal button. Restarting Recharge cannot "
                "enable this connection inside Codex. After checking running chats, fully quit and "
                "reopen Codex with native accessibility enabled. " + accessibility_launch_hint(pid) +
                "Closing its window alone may leave the application running; "
                "no Goal action sent")
        if len(matches) != 1:
            raise RuntimeError("More than one accessibility application belongs to the verified Codex process; no Goal action sent")
        self.owner, self.root = matches[0]
        return Accessible(self, self.owner, self.root)


class Accessible:
    def __init__(self, bus, owner, path):
        if owner != bus.owner:
            raise RuntimeError("Accessibility reference left the verified Codex process")
        self.bus, self.owner, self.path = bus, owner, path

    def call(self, interface, method, signature=None, args=()):
        return self.bus.call(self.owner, self.path, interface, method, signature, args)

    def _property(self, name):
        return self.call(PROPERTIES, "Get", "(ss)", (ACCESSIBLE, name))[0]

    @property
    def name(self):
        return self._property("Name")

    @property
    def parent(self):
        return Accessible(self.bus, *self._property("Parent"))

    def __iter__(self):
        return iter(Accessible(self.bus, owner, path) for owner, path in self.call(ACCESSIBLE, "GetChildren")[0]
                    if owner and path != "/org/a11y/atspi/null")

    def getRoleName(self):
        return Atspi.role_get_name(self.call(ACCESSIBLE, "GetRole")[0])

    def find_roles(self, roles):
        """Let the verified app find controls without fetching its whole tree."""
        values = [int(Atspi.Role.__enum_values__[value]) for value in Atspi.Role.__enum_values__
                  if Atspi.role_get_name(value) in roles]
        if len(values) != len(set(roles)):
            return None
        bits = [0] * 4
        for value in values:
            bits[value // 32] |= 1 << (value % 32)
        bits = [value if value < 2**31 else value - 2**32 for value in bits]
        all_items, any_item = int(Atspi.CollectionMatchType.ALL), int(Atspi.CollectionMatchType.ANY)
        rule = ([0, 0], all_items, {}, all_items, bits, any_item, [], all_items, False)
        try:
            references = self.call("org.a11y.atspi.Collection", "GetMatches",
                "((aiia{ss}iaiiasib)uib)", (rule, int(Atspi.CollectionSortOrder.CANONICAL), 0, True))[0]
        except GLib.Error as exc:
            if any(exc.matches(Gio.dbus_error_quark(), code) for code in
                   (Gio.DBusError.UNKNOWN_METHOD, Gio.DBusError.UNKNOWN_INTERFACE, Gio.DBusError.NOT_SUPPORTED)):
                return None
            raise
        return [Accessible(self.bus, owner, path) for owner, path in references
                if owner and path != "/org/a11y/atspi/null"]

    def getAttributes(self):
        return [f"{key}:{value}" for key, value in self.call(ACCESSIBLE, "GetAttributes")[0].items()]

    def getState(self):
        return States(self.call(ACCESSIBLE, "GetState")[0])

    def queryAction(self):
        return self

    def doAction(self, index):
        return self.call("org.a11y.atspi.Action", "DoAction", "(i)", (index,))[0]

    def queryComponent(self):
        return self

    def get_interfaces(self):
        return self.call(ACCESSIBLE, "GetInterfaces")[0]

    def get_text(self):
        return self.call("org.a11y.atspi.Text", "GetText", "(ii)", (0, -1))[0]

    def set_text(self, text):
        return self.call("org.a11y.atspi.EditableText", "SetTextContents", "(s)", (text,))[0]

    def getExtents(self, coordinates):
        from types import SimpleNamespace
        values = self.call("org.a11y.atspi.Component", "GetExtents", "(u)", (int(coordinates),))[0]
        return SimpleNamespace(**dict(zip(("x", "y", "width", "height"), values)))

    def scrollTo(self, location):
        return self.call("org.a11y.atspi.Component", "ScrollTo", "(u)", (int(location),))[0]


class States:
    def __init__(self, words):
        self.words = words

    def contains(self, state):
        bit = int(state)
        return bit // 32 < len(self.words) and bool(self.words[bit // 32] & (1 << (bit % 32)))
