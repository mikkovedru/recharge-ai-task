# Codex metadata resets on the daemon management socket

## Confirmed cause

On 2026-11-07, Codex app-server 0.167.0 exposed two same-user Unix sockets under `/tmp/codex-daemon-<uid>/`:

- An `app-server daemon` supervisor owns the management listener.
- Its `app-server --listen unix:// --managed-daemon` child owns the metadata WebSocket listener.

Recharge attempted the app-server WebSocket handshake on every socket in that directory. A read-only probe reproduced `ConnectionResetError: [Errno 104]` on management while initialization and `thread/list` succeeded on the worker, returning 26 records. Both listeners were alive. This is a protocol mismatch, not evidence that the worker crashed or that the user's chats were lost.

The indiscriminate enumeration dates to commit `4cd90b5` (2026-10-08). The latest Goal accessibility diagnostics did not introduce it. Restarting Recharge cannot change the socket roles; restarting Codex normally recreates the same topology. Deleting live sockets or restarting their services is unnecessary for this bug.

## Discovery repair

After connecting, Recharge reads Linux `SO_PEERCRED` and verifies the peer UID. Only a `codex` executable whose command contains the adjacent `app-server daemon` subcommands is treated as management. That connection closes before sending WebSocket or metadata bytes. The decision uses the current peer, with no cached PID, socket hash, release path or fixed filename.

Unknown/inaccessible process identities continue through ordinary metadata validation. Genuine worker failures remain visible and identify the endpoint; saved chat metadata remains available. If management exists but no worker metadata connection succeeds, the dashboard reports that explicitly.

Regression coverage includes role discrimination, deleted executable paths, unknown and foreign peers, a real Unix connection receiving no handshake on the management path, healthy-worker discovery, visible worker failures and saved metadata fallback. Live read-only verification confirmed worker metadata and management discrimination without sending a prompt or Goal action.

## Separate native Goal prerequisite

The metadata warning and native Goal activation use different connections. The [accessibility investigation](2026-11-07_missing-accessibility-bus.md) records why native Resume still requires Codex's own accessibility registration. Repairing metadata discovery does not create that registration or establish a successful Goal activation.
