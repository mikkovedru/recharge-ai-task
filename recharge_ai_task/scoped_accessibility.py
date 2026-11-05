"""Query only the verified application's AT-SPI objects, without global caches.

libatspi desktop discovery primes every application's Cache.GetItems, including
Cinnamon's shell. Use the accessibility bus directly so unrelated applications
receive no accessibility calls. See the Cinnamon investigation in doc/.
"""
from __future__ import annotations

import gi
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, Gio, GLib

ACCESSIBLE = "org.a11y.atspi.Accessible"
ROOT = "/org/a11y/atspi/accessible/root"
DBUS = "org.freedesktop.DBus"
PROPERTIES = "org.freedesktop.DBus.Properties"


class ApplicationBus:
    def __init__(self):
        session = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        self.address = session.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.a11y.Bus", "GetAddress",
                                    None, GLib.VariantType.new("(s)"), Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]
        self.connection = Gio.DBusConnection.new_for_address_sync(self.address,
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, None)
        self.owner = None
        self.root = ROOT

    def call(self, destination, path, interface, method, signature=None, args=()):
        return self.connection.call_sync(destination, path, interface, method,
            GLib.Variant(signature, args) if signature else None, None,
            Gio.DBusCallFlags.NONE, 1500, None).unpack()

    def application(self, pid):
        if self.owner is not None:
            owner_pid = self.call(DBUS, "/org/freedesktop/DBus", DBUS,
                                  "GetConnectionUnixProcessID", "(s)", (self.owner,))[0]
            if owner_pid != pid:
                raise RuntimeError("The verified Codex accessibility process changed; no Goal action sent")
            return Accessible(self, self.owner, self.root)
        references = self.call("org.a11y.atspi.Registry", ROOT, ACCESSIBLE, "GetChildren")[0]
        matches = []
        for destination, path in references:
            try:
                owner_pid = self.call(DBUS, "/org/freedesktop/DBus", DBUS,
                                      "GetConnectionUnixProcessID", "(s)", (destination,))[0]
            except GLib.Error:
                continue  # An application exited since the registry snapshot.
            if owner_pid == pid:
                matches.append((destination, path))
        if len(matches) != 1:
            raise RuntimeError("Codex accessibility is unavailable; no Goal action sent")
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
