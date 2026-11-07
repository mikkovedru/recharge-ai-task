# Missing desktop accessibility socket during Goal recovery

## Confirmed failure

A 2026-11-07 automatic Goal attempt failed before activation with
`g-io-error-quark: Could not connect: No such file or directory` while opening
the exact selected chat. A read-only probe reproduced the error independently
of chat navigation: `org.a11y.Bus.GetAddress` returned
`unix:path=/run/user/1000/at-spi/bus_0`, but that socket did not exist. The session
D-Bus socket existed, and the accessibility launcher, broker and registry were
still running. X11 had no alternative `AT_SPI_BUS` address.

The failure was connection to the desktop accessibility bus, rather than a
canonical chat-ID mismatch. Earlier daemon metadata connection resets and desktop
routing timeouts are separate discovery warnings; they do not identify the
cause of the missing accessibility socket. The affected saved recipient had
both actions disabled when inspected, so diagnosis did not re-enable or resume it.

## Recovery behavior

The scoped adapter re-reads the advertised address once when connection fails.
Read-only frame discovery can reconnect once, rechecking focus and the same
Codex PID. Cached owners that have exited are re-discovered by PID. A failed
accessibility action is never replayed: disconnection after Resume was invoked
remains uncertain, and the Goal may already be running.

A persistently missing socket produces a transport-specific error before
clipboard inspection or opening a chat. It does not spend the navigation timeout
reporting an exact-chat failure. The application does not restart shared desktop
services or change accessibility preferences automatically. A missing live
socket still requires session repair, or logout/login; applications may need to
reconnect afterward. Rebuilding this application alone cannot recreate a socket
owned by another service.

The [Cinnamon cache workaround](2026-11-05_cinnamon-goal-accessibility.md) remains
in force: only the registry and bus daemon are queried for discovery, followed by
objects of the verified Codex PID. No desktop-wide Cache.GetItems enumeration,
composer input, Escape cleanup, or direct Goal-state mutation was introduced.

## Test isolation

AT-SPI 2.52 derives its socket name from XDG_RUNTIME_DIR and DISPLAY, rather than
from the session-bus identity. See the
[upstream launcher implementation](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/bus/at-spi-bus-launcher.c#L494-L550).
Thus a private `dbus-run-session` alone does not isolate the filesystem socket.
The synthetic protocol regression now supplies its own runtime directory before
starting that session. It also suppresses the launcher's X11 bus-address
publication while retaining X11 for the fixture. The test asserts the display's
original AT_SPI_BUS property stays unchanged. This prevents it from sharing the
live desktop's socket namespace or replacing its address even when run on the
same X display.

The former inherited runtime directory is a confirmed isolation gap. Which
historical process removed the live bus_0 socket has not been established;
its absence must not be attributed to a specific test without further evidence.

## Validation boundaries

Synthetic regressions cover stale advertised addresses, persistent missing
sockets, cached-owner replacement, reconnect focus/PID guards and post-action
uncertainty without action replay. The real protocol regression uses an isolated
runtime directory, private D-Bus session and synthetic GTK application. No live Goal was activated during diagnosis or verification.

After explicit user authorization, the verified same-user accessibility launcher
was terminated and reactivated through D-Bus. The socket was recreated with a
new bus GUID, and a private connection succeeded. The existing Codex process was
not registered on the replacement bus, so scoped native controls still require
Codex to reconnect, typically by reopening it. Codex and Cinnamon were not
restarted. A separate read-only query found the reported Goal already active,
with the correct chat ID. This current state does not prove that the originally
reported attempt activated it. Reopening Codex while that Goal is running may
interrupt it; no further Resume action is needed while it remains active.

## Reachable bus without a Codex registration

A subsequent 2026-11-07 read-only probe reproduced the later failure reported at
13:27:48. The advertised socket existed and accepted a private connection, but
the registry returned zero applications. Querying connection PIDs on that bus
found only the registry and the probe, while Codex processes remained running.
This confirms missing application registration on the replacement bus, rather
than another missing socket or a wrong selected chat ID. The probe did not query
unrelated application accessibility objects, change preferences, or send actions.

The helper previously treated zero PID matches as a generic navigation error,
retried for the full navigation timeout, and duplicated the “no Goal action sent”
suffix. Registration is now checked before clipboard or navigation effects.
Missing registration reports that Codex must fully quit and reopen after running
chats are checked; an unavailable registry service has separate repair guidance.
Ambiguous registrations still fail closed. Exact-chat identity and native button
verification remain mandatory after registration succeeds.

No supported, safe way to reconnect the existing Codex process was verified.
The helper cannot address a Codex accessibility endpoint on a bus to which Codex
is not connected. Restarting the helper cannot supply that endpoint; changing
global accessibility settings or restarting Codex could disrupt running work.
The application therefore leaves that session repair to the user. Regression
tests cover both missing services and absent or ambiguous registrations, with
zero clipboard, navigation or Goal actions before successful preflight. Live
Goal continuation remains unverified until Codex reconnects to the current bus.

## When an ordinary restart does not restore native controls

A later read-only check on 2026-11-07 found Linux accessibility enabled and matching
session/X11 bus addresses, but no registered Codex process. Thus reopening Recharge
alone cannot repair the missing application interface, and the evidence no longer
justifies assuming that every absent registration follows a bus restart.

The installed desktop launcher is `chatgpt` and delegates to
`/usr/lib/chatgpt/ChatGPT`. The installed binary contains the
`force-renderer-accessibility` switch. After running chats finish, a next-start
diagnostic is to fully quit the desktop app and launch:

```bash
chatgpt --force-renderer-accessibility
```

Closing a window may leave the application running, causing a subsequent launch
to reuse it. This launch workaround has not yet been verified against the live
Codex registration or Goal button; no desktop app or global accessibility service
was restarted automatically. If registration is confirmed after this launch,
retaining the flag in the desktop launcher can make that startup choice persistent.
The [official Linux app documentation](https://learn.chatgpt.com/docs/linux/linux-app)
confirms the `chatgpt` launcher. Neither that page nor the
[OpenAI troubleshooting page](https://learn.chatgpt.com/docs/reference/troubleshooting)
checked for this investigation established a supported repair for this exact
Linux AT-SPI condition. The flag suggestion comes from inspecting the installed
binary, not from a documented OpenAI repair procedure.

The [daemon metadata reset investigation](2026-11-07_codex-daemon-metadata-reset.md)
documents a separate, confirmed protocol-selection bug that does not require
restarting Codex or deleting sockets.


## Registration confirmed after the accessibility-enabled relaunch

Following the user's full relaunch with the flag, a 2026-11-07 read-only probe
confirmed that the current desktop IPC process was registered on the
accessibility bus. Its command line contained `--force-renderer-accessibility`.
The earlier registration blocker was therefore cleared in that session.
The next failure concerned foreground ownership and absent ACTIVE frame state,
not a missing accessibility connection. See the
[exact-chat navigation findings](2026-11-04_exact-chat-goal-navigation.md#foreground-acquisition-and-missing-active-frame-state).
This confirms successful registration in this run; it does not establish why
earlier launches lacked it or prove a live Goal was resumed.


## Slow requests are distinct from unavailable accessibility

The user's 19:38:47 failure was `G_IO_ERROR_TIMED_OUT` (24) after navigation
reached the selected chat. The adapter used a fixed 1,500 ms deadline for every
request and treated a timeout or D-Bus NO_REPLY as a broken transport: it closed
the connection and suggested session repair. That diagnosis was too broad. The
historical log did not include the method or object path, so its exact slow
request cannot be recovered.

Native Goal calls now use 30,000 ms (20 times longer), while other users of the
scoped adapter retain their existing default. Control polling budgets increase
from 3 to 15 seconds, navigation from 10 to 60 seconds, and activation
confirmation from 5 to 30 seconds. The isolated helper has 240 seconds overall,
plus up to 45 seconds for cleanup after termination, rather than 45 and 12.
These are bounded waits; an in-flight request can outlast a polling phase's
budget. Longer waits do not make absent controls available.

A new timeout error names the interface, method, object path and request limit,
and explicitly avoids claiming accessibility is disabled. A slow connection is
kept open. A timed-out request is not replayed, especially DoAction or editing
calls. Native navigation propagates that error immediately; an invocation of
Resume whose acknowledgement times out stays uncertain and cannot be repeated
automatically. Closed/missing transports retain their separate repair guidance.

A private D-Bus fixture with 2.2-second replies demonstrates the old deadline
failing and the 30-second deadline succeeding on the same still-open connection.
Its timed-out action counter stays at one. Tests also cover the helper/cleanup
budgets, controls appearing after the former three-second wait, timeout details,
focus guards and post-Resume uncertainty.

A live Goal-only test then used the selected recipient's saved allowances and
normal delivery path. It succeeded: native and desktop Goal state became active,
the desktop task was active, and objective/creation identity/token budget were
unchanged. No prompt was sent. This verifies actual activation and an active
turn in that session; it does not establish that every historical failure had
the same cause or guarantee an indefinitely healthy accessibility service.

## Accessibility existed in the original working implementation

The native control implementation introduced on 2026-10-10 in `b3a86c2` already
used pyatspi. Access to the native Resume button has always required exposed
accessibility controls. The explicit launch flag is one way to force exposure,
not an inherent requirement when the application activates accessibility itself.
Chromium documents its
[on-demand activation and force flag](https://chromium.googlesource.com/chromium/src.git/+/HEAD/docs/accessibility/overview.md#command-line-options).
That explains how the feature can work without a flag; it does not reconstruct
the previous Codex process's activation state.

The later scoped adapter avoids global caches because the old libatspi discovery
path could trigger a confirmed Cinnamon crash. This changes discovery/cache
behavior, rather than introducing accessibility as a new dependency. Do not
claim the old library simply had a longer normal deadline: upstream AT-SPI 2.52
[documents an 800 ms normal timeout and 15-second startup allowance](https://github.com/GNOME/at-spi2-core/blob/AT_SPI2_CORE_2_52_0/atspi/atspi-misc.c#L1783-L1804).
The exact historical contribution of startup allowance, cache availability and
application behavior remains unknown. Restoring unsafe global cache enumeration
is not needed for the verified activation above.
