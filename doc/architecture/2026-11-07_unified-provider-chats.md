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
