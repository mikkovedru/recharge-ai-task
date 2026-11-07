# Unified provider discovery and recovery

## Identity and discovery

`providers.discover_all_targets` detects executable paths, local data profiles
and supported native app windows, then isolates discovery failures per provider.
Detection and metadata reads never start a model. A missing executable can leave
saved histories visible; a send reports the missing dependency.

Codex keys retain their existing three-part identity. Other targets prepend the
provider to kind, profile and native ID. GTK rows retain that full key separately
from presentation columns, so equal titles or IDs cannot overwrite recipients.
Provider labels also identify saved recipients. The persisted
`chat_provider_filter` only controls visibility; `provider` remains
the default for new terminal launches. Neither changes watch identity.

Claude Code 2.1.301 stores main sessions in `projects/*/UUID.jsonl`. Muse Code
1.4.13 stores main sessions in `sessions/YYYY/MM/DD/UUID/session.jsonl`. The
catalog reads bounded head/tail samples and caches by inode, size and mtime;
it ignores partial JSON records, nested subagents and escaping symlinks. Project
paths come from native metadata instead of guessed directory decoding. These
internal log formats can change; unknown metadata is skipped instead of inventing
chat identity. Large tool-output records can obscure sampled metadata; missing
project metadata keeps a session out of the inventory.

## Native continuation

Local sessions use native exact-session resume commands in their original project
and provider profile. The sender validates the transcript identity immediately
before launch. Same-user process checks block identified active sessions and
unidentified interactive processes in the same project. An advisory session lock
also prevents concurrent Recharge processes from launching the same recipient;
on Linux the child inherits that lock until it exits.

A native Muse session-stream `turn.input.user` or `run.lifecycle.started` event
must match both session ID and submitted prompt. Claude requires a new matching
user turn in its transcript, or a successful result with the same session ID.
Initialization alone never confirms delivery. A timeout or unreadable output
after launch is uncertain, consumes the normal uncertain allowance and disables
automatic retry. Output logs are private files in Recharge's `session-runs/`.
Native permissions remain unchanged. This confirms prompt acceptance, not task
completion or resolution of later native approval/input requests.

The installed Muse echo provider was used to verify persistence, discovery and
continuation of the same UUID without a model request. Claude continuation uses
isolated protocol fixtures; paid live turns are not part of regression checks.

## Independent provider watches

An All-provider watch partitions recipients and creates one worker per selected
provider. Each retains its own quota observations, reset cycles, grace period,
delivered actions and failures. The parent publishes per-provider quota snapshots
plus aggregate scheduling counts; child checkpoints copy mutable accounting
into independent snapshots and are serialized under a parent lock. Manual quota checks wake every worker; stopping or reloading joins the old
workers before replacement. A failed login or provider startup does not stop the
other workers. Existing single-provider state remains readable.

Only the locally configured account/profile is queried for each provider's quota.
Automatic recovery refuses saved Code recipients from another profile, so an old
selection cannot send against the wrong account's observed allowance.
Consumer cloud histories are not enumerated: Claude desktop uses supported native
window recipients, and Muse consumer app/browser chats have no continuation
bridge. An existing Muse terminal cannot be controlled by starting a separate
MSP server. These limits are described in the [user guide](../../README.md#anthropic-claude).

Native contracts: [Claude session management](https://code.claude.com/docs/en/sessions),
[Muse audit logs](https://dev.meta.ai/docs/cookbook/audit-agent-sessions), and
[Muse session streams](https://meta-models.github.io/muse-code-sdk/next/guides/msp-concepts/sessions-and-turns/).


## Provider-specific dashboard presentation

The list button groups filter their own views without mutating recipients.
Question/exclamation icons in parentheses represent warnings and errors only;
healthy tabs have no status icon. The pressed button represents the independent
visibility choice. Recipient filter captions include total category counts.
All starts with Provider before Project; individual provider views hide Provider. Recipient rows
carry their own provider badge and disclose overflowing custom messages with
icon-only view controls. Expansion does not alter message text or delivery state.

`provider_monitor` scopes worker observations and usage-ledger statistics by
provider before formatting any schedule. The All tab labels its earliest schedule
and combined maximum counts explicitly. Separate tabs retain each provider's plan,
usage windows, observation timestamp and failure. A failed refresh may retain old
quota values, marked as last known, without asserting current availability.
Missing data never becomes a zero or another provider's forecast. These views
perform no quota fetch or delivery; existing workers and standalone refreshes
supply observations. Recipient ledger snapshots supply statistics without adding
per-frame database reads. Monitoring tab headers own their tooltip, so the text,
icon and parentheses inherit the same explanation. Page changes clear GTK's
automatic label selection while leaving text available for deliberate copying.
Polling leaves unchanged tooltip text, notice icons and colors intact so refreshes
do not repeatedly replace the hovered tab's presentation.

Inventory warnings retain their provider at discovery. Quota and discovery notices
are rendered in that provider's tab and replaced by current state, avoiding repeated
shared-log messages. Delivery history adds an additive provider column with an
empty default for legacy records; unknown historical attribution is explicit.
Program-wide messages and provider-specific outcomes remain distinguishable in
both the displayed log and exports. Concurrent quota workers also label their
file/stderr status with their provider.

Installation identity is separate from local-history availability. Main filter
buttons are insensitive when no executable or supported running app is detected;
local histories can remain in All. Warning/error adornments are real themed
question/exclamation Gtk images after the caption in neutral round brackets.
