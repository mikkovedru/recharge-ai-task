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
