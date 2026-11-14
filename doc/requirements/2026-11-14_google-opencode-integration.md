# Google and OpenCode integration requirements

This document distinguishes delivered functionality from remaining engineering requirements. See the [architecture and observation model](../architecture/2026-11-11_google-terminal-providers.md).

| ID | Capability | Status and acceptance criteria |
| --- | --- | --- |
| G1 | Live dashboard terminal observations | Implemented for Gemini, Antigravity and OpenCode. Show each live wrapped session independently, observed reset plus grace, retry/cancellation ownership and sent counts. Never label this account quota. Ignore dead or reused process identities and invalid records. |
| G2 | Shared Google quota adapter | Not implemented. Establish an authenticated, versioned quota source with model/account identity, reset timestamps, freshness and error semantics. Account linking must be explicit; do not infer that Gemini and Antigravity accounts or quotas are independent. No fabricated zero/available values on failure. |
| G3 | OpenCode quota mapping | Not implemented. Resolve the session's actual provider/model/account and use a supported quota source for that backend. OpenCode session cost/token counts alone do not establish remaining account allowance. |
| G4 | Direct OpenCode session delivery | Not implemented. Use the documented server/session API with an explicitly configured endpoint and stable session/project identity, authentication and capability/version checks. Discover/read status separately from sending; never auto-start a server or send to a guessed session. Respect busy/retry/permission states and do not resend after an ambiguous timeout. Add native authenticated-session tests before claiming IDE delivery. |
| G5 | Google app/IDE delivery | Not implemented. Establish a supported session/control interface with stable recipient identity and actual permission/focus behavior. Do not reuse Codex private interfaces or type into arbitrary windows. Verify both intended delivery and cancellation without changing unrelated chats. |

The [OpenCode V1 server reference](https://opencode.ai/v1/docs/server/) documents session and message APIs, server authentication and TUI access. That supports investigating G4; it does not establish compatibility with every installed version or provide account-wide quota. Inspect the actual configured server's OpenAPI document before implementing a client. Google Antigravity's [usage documentation](https://antigravity.google/docs/cli/commands/usage) describes its interactive model-group usage panel; G2 still requires an independently verified machine-readable adapter.

Retain native retry ownership and manual-input cancellation across future adapters. Record unverified provider versions, authentication paths and operating systems. A successful HTTP response or prompt submission is not evidence that the AI task completed.
