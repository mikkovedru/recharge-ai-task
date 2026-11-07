# Exact-chat navigation before native Goal activation

The Error task / Usage limited Goal combination is eligible for automatic
recovery. The reported “Could not open the exact selected chat ID” error is a
navigation/identity failure before any native Resume goal action.

`xdg-open codex://threads/<id>` confirms dispatch, not completed navigation. An
active Codex window can still show its previous chat. A single immediate ID read
followed by a snapshot of exact-title sidebar rows is insufficient: loading can
replace those accessible rows, collapsed projects can hide them, and badges can
change their accessible names.

The helper now waits for canonical ID confirmation, re-queries the active frame
and sidebar, and may expand the uniquely named expandable project when no chat
candidate is visible. A title or project name is only a search hint. Each
candidate's native Copy deeplink identity is still verified before opening its
row. The helper rechecks the visible ID and unchanged Goal identity before using
a unique native Resume goal button. It does not type a continuation prompt or
use Escape to close menus, because Escape could stop an active turn.

In the live 2026-11-04 read-only check, both sidebar representations of the webcam
chat copied the canonical ID `01a1a687-2d5a-78c0-ac64-60cf07a1444f`. The registered
protocol handler remained `chatgpt.desktop`; there was no evidence of a changed
URI scheme. Updated navigation reached and verified that ID, then restored the
previous chat and clipboard. The Goal was active before and after; no Resume
goal action or prompt was sent. The exact transient sidebar state at the original
16:09 failure cannot be reconstructed from the historical log.

Synthetic regressions cover delayed selection, stale accessibility frames,
collapsed projects, decorated and duplicate titles, and mismatched canonical IDs.
The profile, process, clipboard and Goal identity guards remain necessary even
when navigation becomes more tolerant of asynchronous UI updates.


The [2026-11-05 Cinnamon investigation](2026-11-05_cinnamon-goal-accessibility.md)
updates the accessibility discovery mechanism and post-click failure wording.
The exact-chat navigation and identity constraints described here still apply.


## Foreground acquisition and missing active-frame state

After the accessibility-enabled relaunch on 2026-11-07, the desktop process
registered successfully. A live probe of the installed `chatgpt` package
`26.1103.32239` found three accessible frames. All reported SHOWING and VISIBLE;
none reported ACTIVE, even while X11 confirmed that the same verified process
owned the foreground window. The existing ACTIVE-only frame selection failed
for ten seconds. One frame's bounds exactly matched the active X11 client's
screen position and dimensions; the other two did not.

The helper now falls back to a unique SHOWING frame with those exact bounds
when no frame reports ACTIVE. The PID is still verified against the desktop IPC
peer, and X11 focus is rechecked after geometry matching. Missing or ambiguous
matches fail without any Goal action. There is no global accessibility scan.

There was a separate foreground acquisition gap: `show_chat` dispatched the
chat URI and assumed the application would gain focus. It never explicitly
activated the verified window. This dates to the original native-controls
implementation, `b3a86c2` on 2026-10-10, and remained through the 2026-10-27
navigation retries and 2026-11-07 accessibility diagnostics. History does not
show a recent removal of explicit focus activation. The exact foreground owner
at the user's 16:59:47 failure and the date ACTIVE stopped being exposed cannot
be established from that log.

After accessibility preflight, the helper acquires the verified process's one
normal X11 window before dispatching the URI. If several windows are eligible,
the user must bring the intended one forward. Once acquired, focus loss aborts
immediately; the helper does not keep retrying and regain focus later. A final
focus check runs immediately before Resume. Canonical chat ID, unchanged Goal
identity and the unique native button remain mandatory.

With these changes, a live navigation-only check reached and verified the exact
reported webcam chat and restored the clipboard. It did not invoke Resume or
send a prompt. Regression checks cover missing ACTIVE, exact/ambiguous bounds,
PID-based activation, post-identity focus loss and real focus transfer between
two blank GTK fixture applications. Actual live Goal activation remains untested.


## Pointer-dependent Copy submenu

A later 2026-11-07 report again failed during exact-chat navigation with the
generic native-control timeout. Moving the pointer away during the old Copy
submenu hover reproduced that error against the reported chat. Activating the
verified submenu trigger through AT-SPI instead returned the exact canonical
chat ID without moving the pointer. This is a confirmed failure mechanism; the
historical log does not prove where the pointer was during the user's attempt.

Identity verification now uses an already exposed Chat actions button directly,
with row hover retained only when necessary to reveal that button. It requires
Copy to expose `haspopup:menu` before invoking its native action; an ordinary
copy-content action is never used as a substitute. Menus, missing/rejected
submenu actions and canonical clipboard reads report their own stage rather
than the same generic timeout. The clipboard is restored and no keyboard
cleanup is sent. Native Goal actions remain guarded separately.

Live inspection also saw the registered frame initially expose no web content,
then populate its full sidebar on later reads. Registration alone therefore
cannot prove that web controls are ready. The exact cause and duration of that
transient state were not established. Chromium's
[accessibility overview](https://chromium.googlesource.com/chromium/src.git/+/HEAD/docs/accessibility/overview.md#command-line-options)
notes that the flag without an explicit mode starts complete but permits runtime
mode changes. This is relevant context, not proof of this transient's cause.

The corrected complete recovery path was checked against the real chat up to the
Resume action, intercepting that action before execution. Clipboard restoration
ran, and the backend Goal status was unchanged. This covers native button,
canonical chat and backend Goal verification; it does not verify actual live
activation or post-activation continuation.
