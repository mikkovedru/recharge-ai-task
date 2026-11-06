# Cinnamon crash during native Goal recovery

## Confirmed evidence

On 2026-11-05, the delivery database records one automatic Goal attempt starting
at 17:20:24 and becoming uncertain at 17:20:42. Cinnamon crashed at 17:20:34;
Nemo also crashed at 17:20:39. Times are Europe/Helsinki.

The Cinnamon journal reports a general protection fault, with this main-thread
stack: `g_type_check_instance_is_fundamentally_a`, `g_object_ref`,
`g_hash_table_foreach`, `libatk-bridge` offsets `0x18ad7` and `0x1c380`,
D-Bus dispatch, `libatspi`, and the Muffin main loop. This identifies an
accessibility-bridge crash, rather than establishing a graphics-driver failure.

Installed versions were Cinnamon `6.6.9+zena`, AT-SPI / ATK bridge
`2.52.0-1build1`, and GLib `2.80.0-6ubuntu3.10`. Disassembling the installed
bridge maps return address `0x18ad7` to its first `spi_cache_foreach` call with
a callback at `0xf400` that jumps to `g_object_ref`. This matches
[AT-SPI 2.52's Cache.GetItems implementation](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/atk-adaptor/adaptors/cache-adaptor.c#L218-L309).

The old helper called `pyatspi.Registry.getDesktop(0)` and filtered applications
by PID afterward. The matching
[libatspi discovery implementation](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/atspi/atspi-misc.c)
creates application references while enumerating the desktop and requests their
`Cache.GetItems` before the Python PID filter can exclude Cinnamon. Setting
`ATSPI_NO_CACHE` alone does not bypass that GetItems request in this version.
An upstream [cache lifetime fix](https://github.com/GNOME/at-spi2-core/commit/d442ee182ec8fa095c6bc5298a17663cfc70cf9a)
also describes possible dangling root pointers and difficult-to-reproduce crashes.
That is relevant background, not proof of the exact invalid object here.

## Application workaround

[Scoped accessibility](../../recharge_ai_task/scoped_accessibility.py) uses Gio
D-Bus calls to read the registry's application references and asks the bus daemon
for each connection's PID. Only the verified Codex process receives accessibility
object queries. The adapter never requests Cache.GetItems, initializes libatspi
desktop discovery, or follows an accessibility reference to another application.
The native helper still verifies X11 focus, the exact chat ID, the Goal identity,
and its unique native Resume button. The
[exact-chat navigation constraints](2026-11-04_exact-chat-goal-navigation.md)
still apply.

This removes the application's route into Cinnamon's failing cache enumeration.
It does not repair the installed system library or prove that every Cinnamon
restart has the same cause. No deliberate crash reproduction was attempted.

## Why a resumed Goal can produce a failure

The helper sets its attempted-click marker before invoking Resume goal. It then
checks for Pause goal, verifies the chat ID again through Copy deeplink, and
checks backend/desktop state. A failure in those later checks can leave the Goal
running while reporting an uncertain result. The generic menu-wait exception
previously appended “no Goal action sent” even after Resume had been invoked.
The helper now replaces that contradictory suffix with an explicit warning that
the Goal may already be running. Such attempts retain their allowance and are
not automatically replayed.

The recorded uncertain attempt and the user's observed restart are consistent
with this sequence. The journal does not record the exact Resume invocation time
or its acknowledgement. The 17:20:50 daemon metadata connection reset is a
separate discovery warning; it does not establish that activation failed or that
the daemon crashed.

## Validation and remaining work

Tests cover application-scoped discovery, refusal of foreign references, real
AT-SPI reads and an action against a synthetic GTK process on a private D-Bus
session, and post-click verification failures. The protocol test also checks that
libatspi discovery remains uninitialized. No live chat or Goal was changed.

Live Codex recovery after this change and long-running Cinnamon stability remain
unverified. If crashes continue, compare their main-thread stacks and investigate
the system AT-SPI package separately; do not assume every restart is this defect.


The [2026-11-07 missing-bus investigation](2026-11-07_missing-accessibility-bus.md)
documents a separate transport failure and isolated test-runtime requirements.
Its bounded reconnection preserves the scoped-cache workaround described here.
