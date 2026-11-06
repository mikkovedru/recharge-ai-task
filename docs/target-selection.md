# Codex target discovery and delivery

<p align="center">
  <img src="assets/logo-lockup.png" width="200" alt="Recharge AI-task logo">
</p>

The selector distinguishes **desktop windows** (X11 window ID + process ID)
from **Codex chats** (stable thread ID + Codex profile). Titles are labels, not
identities: two chats can have the same name, and several chats can use the same
window. Selection is explicit, supports several recipients, and survives restart.

## Research

The official [App Server reference](https://learn.chatgpt.com/docs/app-server)
documents `thread/list`, pagination, `thread/read`, and existing Unix WebSocket
control sockets. [Deep links](https://learn.chatgpt.com/docs/reference/commands#deep-links)
use `codex://threads/<thread-id>` to open existing local chats.

On this Mint installation, Codex CLI is 0.160.0 and the managed local daemon is
0.161.0. Connecting to its existing control socket can list saved chats, but
`thread/loaded/list` returns no loaded chats even while the desktop is actively
running them. Its `notLoaded` status is therefore not used as the desktop's
availability signal. Starting a second app-server to resume these chats would
not address the existing desktop owner.

The installed desktop code also exposes a private, per-user routing socket at
`$CODEX_HOME/ipc/ipc.sock`. Inspection and read-only probes established its
four-byte little-endian JSON frame length, initialization handshake, versioned
`thread-owner-discovery` request, and `thread-follower-start-turn` request. Owner
discovery identifies the exact existing desktop client for a thread. This is
private implementation detail, not an officially supported integration API.
It is isolated in `codex_ipc.py`, checks ownership and acknowledgments, and fails
with an error on incompatible versions. Chat delivery never falls back to typing
in an arbitrary window or resuming the chat in another server.

## Discovery

- Linux X11: enumerate managed windows through EWMH and match application class,
  rather than titles that could belong to browsers. Show title, XID, PID and display.
- Discover running same-user Codex profiles from their `CODEX_HOME` and existing
  daemon control sockets. Read only that environment field, not credentials.
- Query all pages of user chat metadata from existing daemons. Fall back to a
  read-only SQLite connection with schema checks. Archived chats and internal
  subagents are excluded. Titles prefer the saved user-facing `name`.
- Probe desktop ownership separately; show saved versus open chats and owner IDs.
- Preserve selected rows if a window or chat temporarily disappears. Delivery
  revalidates availability and identity instead of silently replacing a recipient.

This inventories locally available Codex chats and desktop windows. It does not
query account-wide ChatGPT conversation history or enumerate disconnected remote
hosts. Linux Wayland cannot use X11 window delivery. The GTK picker is for Linux;
the CLI inventory/selection also supports Windows window discovery. Thread
routing currently requires the Linux desktop's Unix socket.

## User flow

Open **Open Recharge AI-task…** in the tray, or run `recharge-ai-task` or `recharge-ai-task-cli targets --gui`.
`recharge-ai-task --help` lists desktop options including `--tray`.
`recharge-ai-task-cli --help` lists terminal commands, including `gui` and `tray`. Releases
contain the CLI and a combined desktop executable, `recharge-ai-task`.
Linux keeps `recharge-ai-task-gui` and `recharge-ai-task-tray` as small
compatibility launchers.
Run `recharge-ai-task --tray` or `recharge-ai-task-cli tray` to start with only
the tray icon. This does not start monitoring or send any signals; if already
running, it leaves the dashboard visibility unchanged.
All GUI launch commands start the tray too. Further launches reuse the same tray
and present its existing window, preserving the current view. Closing the window
keeps the tray and watch running. Double-click the icon to hide the visible
dashboard to the tray, or restore it with the current view intact. GUI launch
commands and **Open Recharge AI-task…** always show the dashboard. Right-click for
the tray menu, including **Exit** to quit.
Search by title, ID, project, PID or deep link. Enable **Send message**, **Resume goal**, or both
for each recipient and edit the multiline message. Newlines are preserved
when saving and sending. These changes save automatically for quota-reset
delivery; editing them does not send a manual signal. Adding the first recipient
to an empty list starts Desktop watch after the selection is saved. Loading saved
recipients, adding further recipients and editing existing ones do not start a
stopped watch. **Send now to N recipients**
uses the current choices immediately, even when monitoring is off. The button
shows the recipient count and is disabled when none are selected. Manual sends
may resume paused goals; automatic recovery continues to respect intentional pauses.
Send message sends only the message. Resume goal resumes natively and starts
continuation without a prompt. Both activates the goal first, then sends the
message. Window rows support Send message only. **Open selected row** opens a chat
without sending.
The compact table shows Send message, Resume goal, Title, Last active, Task status,
Goal status and Project. **Last active** is Codex's last saved chat update, shown
in your local time and refreshed every 15 seconds. Chats sort newest first by
default; your chosen sort takes precedence after you change it. Windows and chats
without a timestamp show Unknown. Activity sorting uses the timestamp, including
millisecond precision when available.
Enable **Show technical columns** for paths, kind, availability, IDs, PID,
profile, deep link and desktop client. This preference survives reopening the
dashboard and does not restart monitoring. All fields remain searchable in
either view. Drag a header edge to resize a column; long text wraps onto additional
lines. Click any header to sort, then click again to reverse the order. PID sorts
numerically. **Project** starts the list, including when an older saved layout
is restored. You can still drag headers to change positions, including action
columns, and subsequent deliberate changes are remembered. Headers use at most
two lines, with full captions on hover; cell contents continue to wrap normally.
Drag the wide dividers between the chat list and editors, and between the
left workspace and recipients, to resize them. The log has no separate divider:
it starts directly below the send summary and uses all remaining space. The message and log occupy the left half below the chat list; Recipients & actions
starts directly beneath the logo and startup text and extends to the bottom of
the window. The recipient list takes spare height while the override editor keeps
its natural height; dragging their divider changes that balance. Smaller windows
retain scrolling when the editor cannot fit. This layout update resets old divider
positions once, while keeping saved window dimensions and message editor sizes.
Global limits sit to the right of the default message editor.
The shorter default editor remains resizable. The Send now button sits below the Default message label, aligned with the editor’s bottom. Recipient text is display-only; click an item or use
Up/Down to select it and highlight the same chat in the main list. Selecting a
chosen chat in the main list also highlights its recipient and loads its editor,
without moving keyboard focus. An unchosen chat has no recipient counterpart. A search that
hides that chat clears when the recipient is selected. Re-selecting a recipient
never sends signals. This panel shows titles and project/profile context rather
than chat IDs; use the main list’s technical columns or Copy link / ID for those.
Drag the bottom-right corner of the default or custom
message editor to change its width and height, or focus its grip and use Arrow
keys. Growing the default editor uses spare log space first and enlarges the lower
panel when needed; shrinking it gives that space back to the log. Editor sizes, window size, Settings dialog size and divider positions are remembered.
Column widths, order and sorting are saved automatically and survive refresh,
closing to the tray and restarting. These view changes do not send signals or
restart monitoring. Hovering a row also shows its full values.

Successful automatic saves do not add a status line. Write failures remain
visible and retry while the window is open. Changes made by another picker are
reported without overwriting them during refresh. The **Start/Stop Desktop watch** button
controls the tray's actual worker. The Monitoring box has a green border when
On, a red border when Off, Waiting or in error, and a yellow border during transitions.
The border uses the bright green/yellow/red palette of the earlier Desktop watch status. The status appears beside **Monitoring** as **On**, **Off** or
**Reloading** (with short labels for stopping, waiting and errors). The colored
border surrounds the whole Monitoring box; hover for details. It updates every
two seconds. A stopping worker must finish before another starts. If the tray is absent, Start launches it.
Closing the picker leaves the tray and active watch running.

The overview has a compact **Monitoring** group and a two-column **Quota checks & recovery** group above the list.
The quota heading and reset forecast share the top row. Both overview boxes and
the smaller logo share Monitoring's compact height. Overview text stays on one
line with the full value available on hover. The quota box retains its neutral
border: only **No send scheduled**, **Updating…** and **Checking…** are yellow,
**Desktop monitoring is off.** is red, and **Forecast** / **Next reset forecast** are green.
The left quota column reports the next check. The right shows the expected send
time, a live countdown and pending message/Goal counts. A forecast includes the
configured grace period and can move earlier when quota recovers early; a
confirmed send countdown starts from observed usable quota. Counts say “up to”
because live statuses and allowances can skip actions. Stopping watch clears
the send schedule. Counts respect the current remaining allowances. While
monitoring with no pending recovery, the right column shows a reset forecast
and selected counts rather than claiming a send is scheduled. Missing or stale
worker updates and allowance errors are displayed explicitly. Grace comes from
the running worker, so unapplied settings cannot alter its countdown.
Run-at-login controls and launch-origin details are in Settings.
**Recipients & actions** sits beside it with the actual recipient plans. Monitoring reports the tray worker, independently of each chat's task
status. Recipients counts the selected signal destinations. Next check uses the
worker's scheduled quota check or delivery retry, with a live countdown and the
reason for waiting. It does not promise that a task will resume at that time.
An unavailable tray, failed quota read, grace period, and pending delivery retry
have distinct explanations. Stopping monitoring removes its old countdown.

The list includes separate **Task status** and **Goal status** columns next to
its title. Status and target discovery refresh every 15 seconds without clearing
your choices; **Refresh** updates them immediately. Directly below the list,
the last refresh time spans its own line. Below it, **Refresh** appears on the
left, with **Copy link / ID** and **Open selected row** beside each other on the
right. Those button labels wrap onto multiple lines when space is limited. Their
height follows the displayed lines, so one-line captions keep a compact toolbar. Below the multiline
message, the recipient summary shares a row with **Send now to N recipients** at the far
right. Search also matches both status columns and the project name.

**Project** and **Project path** sit between **Goal status** and **Kind**. Project
names come from read-only, schema-checked Codex project metadata, combining
native SQLite memberships with desktop assignments retained during migration.
Native names take precedence over old cached names; explicit chat membership is
used even when the working path has moved. Older releases use the desktop state
file. Unassigned chats and window recipients have no project name. Unsupported
or unreadable metadata produces a discovery warning, while paths remain visible.
Folder names are not substituted for custom names.

Task status reports **Running**, **Waiting for approval**, **Waiting for input**,
**Idle**, **Error**, or **Not loaded**. For an open local chat, a temporary,
owner-pinned observer reads the desktop's current runtime snapshot and detaches.
It never resumes the chat or starts a turn. Desktop state takes precedence over
the metadata daemon, which can report an active desktop chat as not loaded.
The private snapshot adapter currently supports version 11 and fails visibly if
it becomes incompatible. Only status fields are retained; conversation contents
and goal objectives are discarded.

Goal status reports **Active**, **Paused**, **Blocked**, **Usage limited**,
**Budget limited**, **Complete**, or **No goal**. A read-only, schema-checked
`goals_*.sqlite` query supplies persisted status for saved chats and is read again
after live snapshots. This keeps an older desktop cache from hiding native goal
updates made through another connection. Cached completed goals are shown when
no newer persisted goal exists. A missing or unsupported source
is **Unavailable**, rather than an inferred idle task or absent goal. Window
recipients show **Unavailable** because they do not identify a fixed chat.
Disconnected saved selections remain listed with unavailable statuses.
The public runtime and goal states are documented in the
[Codex App Server reference](https://learn.chatgpt.com/docs/app-server).

Task and goal cells are colored. Their headings include information icons; hover
the cells or headings for a single legend of all supported states. **Running** (active) is green; **Waiting for approval** and
**Waiting for input** are yellow; **Error** is red. **Idle** and **Not loaded**
use normal text, and **Unavailable** is yellow. A task can need both approval
and input simultaneously. **Active** is also accepted as a green display label.

For goals, **Active** is green, **Paused** and **Usage limited** are yellow,
**Budget limited** and **Blocked** are red, **No goal** uses normal text, and
**Unavailable** is yellow. **Complete** uses normal text preceded by a green
checkmark. Persisted `usage_limited` and `budget_limited` are displayed as
**Usage limited** and **Budget limited**.

The multi-line status area scrolls and retains recent messages, each prefixed
with the local date and time (`YYYY-MM-DD HH:MM:SS`). Warnings are
yellow, errors red, and signal sending/results green. Saving, startup toggles
and watch start/restart messages use the normal theme text color. Mixed sends
show each recipient's result in its own color, with a red summary for failures
or yellow for skipped actions. Long logs are bounded and new messages do not
move the scroll position while you are reading older diagnostics.

Live quota shows usage, local reset dates, and a countdown for each limit.
The 5-hour and weekly lines are colored independently: normal theme text below
85% used, yellow from 85%, and red at 100% or above. Color stops after `used`;
the separator, reset date and countdown keep the theme's normal text color.
**Quota polling (seconds)** controls automatic quota reads in the dashboard,
Desktop watch and CLI recovery. The refresh label uses that same configured
interval. While Desktop watch is active, the dashboard reuses its quota snapshot
and check time instead of issuing an independent quota request; the overview
countdown comes from that worker's next check. Changing the setting reschedules
the dashboard timer and restarts the active watch with the new interval. Manual
checks can wake the worker sooner. Countdown text still updates every second. A failed refresh keeps the last known
values
with their age and the error. Quota requests time out if Codex stops responding.

In **Settings**, **Run the tray when I log in** controls the operating system's
startup registration. **(This tray started at login: Yes/No)** beside the checkbox
reports whether this session came from the startup entry.
The entry launches the tray, without automatically starting Desktop watch.
Startup entries include `--tray --autostart` so future launches can identify their
origin; enabled older entries are migrated when the updated tray starts.

**Settings…** opens a GTK editor for default mode, Codex CLI path and
arguments, reset grace, polling interval, and startup registration. Additional
information is a bulleted list; startup origin appears in round brackets beside
the login checkbox. Grace buttons step by 10 seconds; polling buttons
step by 5 seconds. Both fields also accept directly entered values.
**Color theme** offers **Dark**, **Light** and **Auto (OS)** with an immediate
preview. Save keeps the choice across launches; Cancel restores the saved
preference. Forced Light/Dark use GTK's bundled Adwaita variants so both work
even with a dark-only system theme. Auto releases those application overrides
and follows the operating system's GTK theme. The tray's
Settings menu opens this editor too. Prompt text and per-recipient signal choices remain visible
in the main window. Saved settings and recipients automatically restart an active watch after a
600 ms debounce. The previous worker finishes before its replacement starts;
quota-reset identities, accepted/uncertain recipients and pending retries survive
the restart. Prompt typing and checkbox changes coalesce into one update.
An empty selection or blank Prompt draft suspends the watch until settings become
valid. Stop cancels pending restarts. Editing existing recipients while Off does
not start a watch; adding the first recipient to an empty list does.
Configuration is saved atomically.

On Linux, the picker and tray communicate through a private Recharge AI-task control
socket in the configuration directory. Only same-user clients are accepted,
the socket is mode `0600`, and a second tray cannot replace an active socket.
The dashboard controls a watch started by the tray; a separately launched
`recharge-ai-task-cli watch` process is managed in its own terminal.

CLI examples:

```bash
recharge-ai-task-cli targets --json
recharge-ai-task-cli targets --select THREAD_ID_1 --select THREAD_ID_2
recharge-ai-task-cli targets --clear
recharge-ai-task-cli watch
```

Use the full `key` from JSON output when an ID is ambiguous across profiles.
No selection means no automatic signal. Legacy first-title-match watch behavior
has been replaced; users must choose recipients once.

## Delivery and retries

For a chat, discover its owner and route the versioned request directly to that
client. If a saved chat has no owner, open its canonical deep link and wait for an
owner before sending. No model, permission or workspace changes are requested.
Ordinary signals are text input; this path does not emulate the composer's
slash-command UI handlers. Native goal recovery is a separate operation:

Each saved recipient carries independent `send_prompt` and `send_goal` flags.
The GUI no longer has a global goal-recovery toggle. Legacy selections migrate
using the old `goal_mode` value, which remains a CLI option. New CLI `--select`
recipients default to Prompt only; `targets --json` reports saved action choices.

For Goal, the adapter reads the selected chat's goal through the existing same-user
Codex daemon. Reads share persisted state, but writing a goal through that daemon
does not update the desktop owner's cached goal or its continuation dispatcher.
The Linux adapter therefore opens the selected chat and uses its native **Resume
goal** button through accessibility. It verifies the desktop process, copies only
the selected sidebar chat's canonical deep link to check its exact ID, and restores
all clipboard formats through the desktop clipboard manager. A deep-link dispatch
acknowledgement does not mean navigation is complete. The
helper waits for the canonical selected ID, re-reads changing frames and sidebar
rows, and can reveal a collapsed project. Titles and project labels only narrow
candidates; canonical IDs are checked before opening any chat row. Decorated
accessibility labels do not replace that ID check. No objective,
budget or usage history is replaced.

Activation must change the native button to **Pause goal** and be confirmed in
both saved goal state and the owner's live snapshot. Goal-only never starts an
empty user turn or sends a prompt: Codex's native goal dispatcher handles the
continuation. An already active goal needs no further activation. Manual sends
may resume a paused goal during an existing prompt turn without starting a
competing turn. With both signals selected, the prompt follows verified Goal
activation; if Codex has already started a turn, the prompt steers that turn.

The native control currently targets the installed English Linux desktop UI and
requires X11, accessibility, `xdotool`, and a clipboard manager (present on Mint
Cinnamon). Source installations also need `gir1.2-atspi-2.0`; release builds bundle
the Python accessibility adapter and native typelib. Identity lookup uses pointer
and native menu actions only: it never sends Escape, which can cancel a Codex turn.
Missing or incompatible controls fail visibly;
there is no fallback to an empty turn. Native UI actions are serialized across
processes and time-limited. Unconfirmed activation or delivery is not retried
automatically, and prevents the independently selected prompt from sending.

Activation verification allows usage to advance during a running turn, but rejects
accounting resets and budget changes. Automatic recovery respects intentional
pauses in both saved state and the desktop cache. Goal actions skip missing,
blocked, budget-limited, complete or already-running goals during automatic
recovery. When Prompt is also selected, skipped Goal actions are reported and the
independent Prompt still sends. Window identities cannot identify an individual
goal, so their Goal checkbox is disabled.

This applies on every quota recovery, replacing the old once-per-watch first
message behavior. Starting a watch after quota has recovered also finds selected
usage-limited, errored or newly introduced resumable Goal states and recovers
only those, after the grace period. Other chats
receive no startup signal. Failed startup checks retry while the watch runs.

A window recipient means the currently displayed chat and focused input in that
window. Keep its composer focused before using window delivery; chat ID targets
avoid this focus dependency. Window delivery validates the XID/PID and foreground
window before typing and submitting. Closing a window or reusing an ID causes a
failure. Desktop settings and conversation drafts are not cleared.

The watcher polls all quota windows, including the weekly allowance. A manual
reset or newly usable credits can recover quota before the forecast reset time.
The grace period starts at the first check that observes availability; the old
forecast never delays an early recovery. Normal, exhausted and failed quota
reads all use the configured polling interval. Grace-period checks can occur
sooner to honor the grace deadline; there is no hidden percentage-based
acceleration or separate 60-second retry interval. Both windows must recover
unless the backend confirms usable additional credits. Explicit rate-limit and
spend-control blocks still postpone delivery. Unspent reset credits alone do not
make quota available, and the app never consumes a reset credit for you.

A passed reset timestamp alone does not trigger delivery. Failed quota reads
postpone desktop delivery. The CLI wrapper also polls while waiting; when its
quota API is unavailable, it retains the later terminal/API forecast as a fallback.
A second exhaustion/refill can reuse the same forecast ID; repeated current-window
exhaustion is confirmed before another recovery is armed, avoiding replay from
one stale snapshot.

The watcher tracks accepted recipients separately for each reset. Confirmed
failures retry every 30 seconds while quota is available; this pending delivery
survives the quota returning to normal. Confirmed successes are not resent within
that reset.
Native recovery rechecks the current goal on confirmed retries, so an already
activated goal is not activated again. A timeout or connection loss after native
activation or turn submission is **uncertain**, so it is not automatically
retried in the same reset; check that chat before retrying manually. Individual
results appear in logs and in the selector's scrollable message area. Automatic
and manual sends share a bounded delivery history in `delivery.sqlite`. The
dashboard reads new events every two seconds and reloads the most recent 200
on reopening, even when the tray is unavailable. Each event identifies the
recipient, Codex project name, message or Goal action, source and outcome.
Older history without stored project metadata is retained with “Project: not
available”; it is not guessed from a possibly duplicated chat title. Message events include
the actual default/custom text. Accepted Goal requests and verified activation
are distinct; failed, skipped and uncertain outcomes remain explicit. History
retains up to 1,000 events and is separate from allowance accounting.

## Validation

The Cinnamon tray double-click integration test uses native pointer injection.
It has missed injected toggles in batch and isolated runs. One diagnostic
received only one button press from an injected double-click. That check depends
on the active panel and pointer environment; the cause of the missing events
remains unconfirmed. Recovery and delivery-history
regressions use isolated settings and synthetic recipients.

Regression tests cover duplicate titles and profiles, pagination, read-only
metadata fallback, fragmented IPC frames, Unicode, pinned owner routing, partial
fan-out failure, stale windows, focus changes, malformed turn acknowledgments,
overlapping quota windows, stale snapshots, quota recovery, and reset retry
behavior. Native goal tests cover profile identity, preservation of budgets and
accounting, changed goals, startup recovery, retries, and uncertain activation.
An opt-in offline integration test uses two real installed Codex backends sharing
a temporary profile: native activation is visible to the original backend while
the control backend remains unloaded. Its model provider points only to a closed
local port; existing chats and external model services are never used. Live checks
exercise discovery and GTK selection/search/save using isolated configuration.
No test signal is sent to existing user chats.

## Recipient messages and continuation limits

**Recipients & actions** lists the chosen chats/windows, automatic and
manual action previews, used/remaining allowances and effective messages. Choose
an entry to edit its actions, message and limits. Hover over its preview for the
full custom message; the action preview’s tooltip explains current status checks. The preview
uses the latest refresh; the sender verifies live Goal state and allowances.

Allowances read **used N / limit**, using a larger **∞** for an unlimited
allowance. Default message previews are hidden. A custom message appears on the
same line as its message allowance, separated by **|** and labeled
**Custom message:**. Long text is ellipsized with the full multiline custom
message available on hover.

Each recipient has a single project-first title line and an obvious filled
selection highlight. The full title is available on hover. Rows with no eligible
automatic action have muted titles and previews, but remain
selectable and editable. Each unavailable action has a highlighted explanation;
reached limits are highlighted beside their counts. A row with an eligible
message and an inactive Goal keeps the message visibly available. Paused Goals
show the difference between automatic recovery and **Send now**, while an
already active Goal says that no activation is needed. Message-only recipients
are not made passive by task or Goal status labels.

Routine ready messages and checkmarks are hidden. Every recipient has an
information/details button, including message-only recipients. Warning icons
indicate actions needing attention; these icons are not delivery receipts.
Their contrasting background remains visible on selected rows.
Goal-only rows have no message-preview placeholder. Hover over an issue icon
for the full explanation, or focus it and press
Enter/Space to open the same details. Unreadable status or allowance data is
shown as unverified, not ready. Unconfirmed sends remain counted and have a
warning to check the chat before retrying or resetting counts. These previews
show eligibility when quota is usable; they do not promise a scheduled delivery.

Duplicate titles stay separate because preferences and counts use the chat ID
and Codex profile, or the window identity.

The **Global limits per recipient** controls beside the default message set
separate limits for **Send messages** and **Reactivate goals**. Each offers two buttons:
**∞** (unlimited) and its numeric limit. The larger infinity glyph matches the surrounding text height. The pressed button is the active mode;
click the number to select that mode and edit the value. These are defaults for each
recipient, rather than a shared pool. Each recipient can inherit a default,
choose its own limit, or explicitly choose ∞ (unlimited). The per-recipient controls
use **Off**, **Global default (value)**, **∞** and a numeric button.
**Reactivate goals** appears before **Send messages** in both groups.
Only the local controls below the list color their active button: red for Off
and green for other modes. Global buttons keep their normal theme styling.
**Off** replaces the separate action checkbox and retains its saved limit.
The local Global default button shows the current ∞/numeric value in
parentheses and follows future global changes. Turning both actions off removes
the recipient; reselect it in the main list to use it again.
Zero prevents that action.
**Use a custom message for this recipient** overrides the default, including
multiline text. With the checkbox off, the box previews the default message in
a passive theme-colored tint and remains read-only. Enabling the checkbox
restores the normal editor appearance. An empty custom message is an invalid draft; it never silently
falls back to the default. Overrides survive refresh, deselection and restarting.

Enable **Send only once**, beside the custom-message checkbox, to use the custom message for one accepted message send,
then return to the current default. A definite failure or skipped message leaves
it armed. An unconfirmed send is treated as used, so the custom text is not
repeated automatically. Count resets do not rearm it; editing or re-enabling Send
only once does. New edits are preserved if an earlier message finishes in the meantime.
See [one-use message handling](../doc/architecture/2026-11-06_one-use-custom-messages.md).

The colored icon in neutral round brackets beside **Use a custom message for this recipient** reports persistence
and application status: saved/applied, saved but waiting for the watch, unknown,
or failed. Green indicates saved/applied, yellow indicates pending or uncertain,
and red indicates failure. A red pause icon replaces the OK mark when Send
messages is Off or its effective allowance is zero. Hover for details. When monitoring is off, it reports that the message
is saved and available for Send now or a future watch start. This icon confirms
settings status, not delivery. Routine successful saves and watch restarts stay
out of the error log; failures to save, apply or restart are still reported.

The recipient counts sit directly below the default message and **Send now** in
the same bordered composition group. The immediate-send/paused-Goal explanation
is in Send now's hover help, including its Ctrl+Enter shortcut.

**Program log** has **Save log…** and **Clear log** buttons. Save exports the
currently displayed, timestamped text as UTF-8, preserving multiline messages.
Its file chooser suggests `YYYY-MM-DD_log_Recharge-AI-task.txt` using today's
local date and asks before replacing an existing file. Cancel leaves the log
unchanged, and write failures appear in the log. Clear empties this window's
view; it preserves stored delivery history and allowance counts. Already-read or
in-flight old history does not immediately repopulate the cleared view. New
events still appear, and reopening the dashboard loads recent stored history.

Counts cover both **Send now** and automatic Desktop watch recovery. They last
until explicitly reset, across quota resets, watch restarts and app restarts.
Confirmed messages and native Goal activations consume their respective
allowances. Already-active goals, protected or missing goals, and definitive
failures consume no Goal activation allowance. An unknown acknowledgement or
interrupted send reserves an allowance as **unconfirmed** to avoid duplicates.
A successful Goal action remains counted if its later message fails.

When both actions are selected, a reached Goal limit withholds the message too.
Untick Resume goal to send a message independently. A reached Message limit still
allows Goal-only activation. **Reset current recipient's counts** renews both allowances for the
chosen recipient; **Reset counts for all** renews all stored allowances.
Neither reset sends anything or replays an earlier quota recovery. Resets refuse
to run while a sender still has a delivery in progress. Check the chat before
resetting unconfirmed deliveries. Counts live in `delivery.sqlite` beside the
settings, so changing configuration does not erase them.

These limits apply to the selected desktop recipients. The separate interactive
PTY CLI wrapper continues to manage its own terminal session.

## Does status affect sending?

Checking an action saves a choice. **Send now** attempts it immediately;
**Desktop watch** waits for quota recovery and its grace period (or a selected
quota-stopped Goal at startup). A checked box is not a promise of delivery.

| Selected action | Behavior |
| --- | --- |
| Send message only | Attempts the effective message regardless of cached task/goal status, subject to its allowance. Codex may reject a busy chat or unavailable quota/routing. Window recipients also require verified focus. |
| Resume goal only | Requires a fixed chat ID and live Goal/task verification. Automatic recovery skips paused, blocked, budget-limited and completed goals and running/waiting tasks. Manual sending may resume a paused goal, including during an active task. A Goal already active needs no activation and consumes no Goal allowance. |
| Both | Verifies/activates Goal first, then sends the message. An active turn receives the message through steering after verified Goal handling. If Goal is intentionally skipped because it is protected, already running, or absent, the independent message choice still applies. Failed or unconfirmed Goal verification withholds the message. Limits apply as described above. |

When neither action is selected, nothing is sent. Status changes can invalidate
a preview before delivery; the result log reports accepted, skipped and failed
actions. The sender never removes a Goal's budget, changes its objective or sends
an empty user message to imitate native Goal continuation.


Task **Error** does not suppress chosen messages or resumable Goal actions. Explicit
Goal error states are also eligible for native activation, including startup
recovery once quota is available. Identity, budget and activation verification
still apply; intentional pauses and completed goals keep their usual handling.

Unrecognized nonempty task and Goal statuses are allowed by default. Only known
exclusions (such as intentional pauses during automatic recovery, blocked or
completed goals) suppress their actions. Missing/unreadable state is a verification
failure, and chat identity, send limits and native acknowledgement still apply.


## Status help and keyboard controls

Hover over ⓘ beside Task status or Goal status, or focus its button and press Enter/Space, for a
compact eligibility list. Each row shows **Automatic Goal** and **Send now Goal**
with green **✓ Continue** or red **✕ Skip** labels. Expand a status for its meaning.
Errors and new nonempty statuses are eligible by default; only explicit exclusions
are skipped. Missing/unreadable state remains a verification failure. Message-only
signals do not use Goal-status gates; quota, routing and configured allowances
still apply. Runtime status colors and continuation eligibility describe different
things: a task can be in Error while its continuation is allowed.

The list uses text and symbols alongside color and adapts to light/dark themes.
Use Up/Down or PageUp/PageDown to scroll; Enter on Close or Escape dismisses it.
Recipient lists and their selected overrides have visible grouping borders.

| Shortcut | Action |
| --- | --- |
| Ctrl+F | Focus chat search |
| Ctrl+R | Refresh chats and statuses |
| Ctrl+Shift+R | Check quota now and wake the active monitor |
| Ctrl+Enter | Send the selected actions now |
| Ctrl+, | Open Settings |

**Check quota now** updates the display and requests an immediate check from a
running monitor. It does not start an inactive watch or bypass grace or recipient
limits. The button indicates when a check is running. The recovery card shows
**Send in** during grace, separately from the next quota poll.

Settings highlights its default Save button: Enter saves and Escape cancels.
Left/Right moves between its action buttons when one is focused; arrow keys keep
their normal editing behavior in text fields. Enter in a main-window multiline
message editor continues to insert a newline. The logo is keyboard-focusable;
Enter/Space opens GitHub and Shift+F10 opens its copy-link menu. The copy item
shows the repository URL in round brackets.

Status-help hovering does not take editor focus or sort the column. The popup
stays open while the pointer moves into it. Expanding an explanation or scrolling
keeps it open until **Close** or **Escape**. Hover-only help closes shortly after
the pointer leaves both its icon and popup. See the
[GTK layout and popover notes](../doc/investigations/2026-11-04_gtk-table-and-popovers.md)
for the sizing and pointer-handling constraints.

Last active defaults to newest first; the
first timestamp-header click also chooses newest first. Old sort preferences are
migrated once, while column widths and order are preserved. Subsequent deliberate
sort choices are remembered. Message and/or Goal recipients always stay above
unselected chats, with a visible divider between the groups. Each group follows
the chosen column and sort direction.

## Recovery between quota checks

Recovery also detects a reset/refill between polls after a near-limit observation
(at least 95% used), even when no 100% snapshot was captured. Small percentage
corrections do not trigger sending. Repeated refills with the same reset ID need
two near-limit observations to avoid replaying a stale frame. Recovery checkpoints
retain pending sends and verified actions across tray restarts. A confirmed Goal
is not activated again when only its message needs retrying. See
[watch recovery and delivery history](../doc/architecture/2026-11-04_watch-recovery-and-history.md)
for the recovery rules and uncertainty handling.

A definite failure before pressing Resume goal stays a failed, retryable attempt
and releases its Goal allowance. An accepted activation whose state cannot be
verified remains uncertain, keeps its allowance reserved and is not automatically
replayed. An attempted UI operation alone is not evidence that a Goal was sent.
See [exact-chat navigation](../doc/investigations/2026-11-04_exact-chat-goal-navigation.md)
for the asynchronous navigation constraints.


## Cinnamon accessibility isolation

Native Goal discovery queries only the selected Codex process through the
accessibility bus. It avoids desktop-wide accessibility caches, which can crash
Cinnamon in the installed AT-SPI 2.52 bridge. If a native Resume invocation cannot
be verified afterward, the log says the Goal may already be running; that
uncertain attempt is not automatically repeated. See the
[Cinnamon crash investigation](../doc/investigations/2026-11-05_cinnamon-goal-accessibility.md)
for the observed stack, workaround and remaining validation limits.


## Missing desktop accessibility connection

Native Goal recovery preflights both the accessibility bus and the verified
Codex process's registration before touching the clipboard or opening a chat.
It refreshes a stale address once and may reconnect read-only discovery while
rechecking the same active Codex PID. It never repeats a Resume action after a
connection failure. If the desktop advertises a missing accessibility socket,
the error identifies that transport problem instead of claiming an exact-chat
identity failure. Session accessibility must be restored, or the session logged
out and back in, before native controls can work. A missing registry service is
reported separately from an available registry that has no Codex registration.
If the bus has restarted, an existing Codex process may still be disconnected:
check running chats, fully quit Codex, and reopen it before retrying. Reconnecting
this helper alone cannot restore the application's own accessibility connection.
If an ordinary restart leaves Codex unregistered, Recharge cannot read its native
Resume goal button. Restarting Recharge cannot enable accessibility inside Codex.
After running chats finish, fully Quit the desktop app; closing its window can
leave it running. On installations using the `chatgpt` launcher, a next-start
diagnostic is `chatgpt --force-renderer-accessibility`. The installed executable
may also be shown in the error. This workaround needs live registration verification
after restart; it is not an acknowledgement that Goal activation succeeded.
The dashboard never restarts Codex or shared desktop services automatically. See the
[missing-bus investigation](../doc/investigations/2026-11-07_missing-accessibility-bus.md).
