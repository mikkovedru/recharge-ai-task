# Google Gemini and Antigravity terminal integration

Recharge has independent `gemini` and `antigravity` providers. Gemini runs the `gemini` executable; Antigravity runs `agy`, the interactive CLI, rather than the IDE launcher. Each has its own executable path and argument list. OpenCode remains last in provider ordering. The implementation is in [google_ai.py](../../recharge_ai_task/google_ai.py), with PTY execution in [wrapper.py](../../recharge_ai_task/wrapper.py).

## Why keep two Google providers?

Both tools are from Google and overlap in their workflows. Google's [Gemini CLI migration guide](https://antigravity.google/docs/cli/gcli-migration/) describes Antigravity's compatibility with existing Gemini CLI rules and its conversion of extensions, skills and MCP configuration. Compatibility does not make the installations interchangeable: `gemini` and `agy` have separate startup commands, configuration layouts and usage views. Recharge retains separate provider identities so selecting one launches the executable and arguments the user configured for that tool. Combining them solely by company would make that selection ambiguous and could apply settings to the wrong process. This distinction concerns integrations, not a claim that their Google account quotas are independent.

## Supported behavior and capability boundaries

Run `recharge-ai-task run --provider gemini` or `recharge-ai-task run --provider antigravity`. Install the provider separately and complete its own sign-in and workspace-trust setup. Explicit paths use `--gemini PATH` and `--antigravity PATH`; environment overrides are `GEMINI_CLI_PATH` and `ANTIGRAVITY_CLI_PATH`. Antigravity's documented CLI locations include `~/.local/bin/agy` and `%LOCALAPPDATA%/agy/bin`; npm-installed Gemini can use the Windows npm command directory.

The wrapper observes explicit terminal usage/quota-limit messages and supported reset durations or local reset times, adds the configured grace period, then sends the saved continuation message. A bare 429, network error, unknown reset format or quota percentage does not establish a continuation deadline. Native retries, model switching and choice dialogs suppress Recharge's pending prompt; manual input cancels it. Headless/print, ACP and remote-agent modes cannot receive the local continuation prompt and are rejected. Permissions and model choice remain with the provider.

The provider tabs identify wrapped-terminal support and show the launch command. They do not display invented quota percentages, zero delivery counts or a fake provider plan. This integration does not consume a Google machine-readable quota endpoint, discover saved Google chats as dashboard targets, or operate the Antigravity app/IDE composer. Codex Goal recovery is not sent to Google tools, even if Goal mode remains enabled in an older configuration.

Antigravity's own `/usage` panel refreshes model-group quotas. Gemini provides its own `/stats` view and different authentication paths. Those interactive views are not used as a background shared-quota API. This is an implementation boundary, not a claim that Google has no internal quota endpoints.

## Verification and limits

Regression checks use real POSIX PTY child processes to verify continuation after an explicit reset and suppression during native retry. Parser checks cover chunked banners, long compact durations, decimal seconds, stable deadlines across redraws, ambiguity, native fallback/choice prompts and rejected headless modes. GTK checks cover tab order, configuration persistence and narrow-window interaction. The supported message forms are intentionally conservative; a changed provider TUI can require parser updates.

Live signed-in Gemini/Antigravity quota exhaustion and native Windows PTY operation have not been established by fixture tests. New provider releases may redraw prompts differently or introduce additional choice screens. Do not broaden message matching without reproducing the terminal interaction and protecting native retry ownership. A successful prompt submission does not establish task completion.

## Primary references

- [Google Gemini CLI authentication](https://geminicli.com/docs/get-started/authentication/) describes Google sign-in, API-key and Vertex authentication paths.
- [Gemini quota-error classification](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/utils/googleQuotaErrors.ts) distinguishes terminal quota exhaustion from retryable quota errors.
- [Gemini quota/fallback UI](https://github.com/google-gemini/gemini-cli/blob/main/packages/cli/src/ui/components/ProQuotaDialog.tsx) includes native retry, model-switch and Stop choices; sending a continuation into that menu would be incorrect.
- [Antigravity setup](https://antigravity.google/docs/getting-started?tab=cli) identifies the `agy` CLI and its installation locations.
- [Antigravity CLI reference](https://antigravity.google/docs/cli/reference/) distinguishes interactive startup from print, ACP and remote modes.
- [Antigravity usage panel](https://antigravity.google/docs/cli/commands/usage) explains its interactive model-group quota view.

## Live wrapped-terminal observations — 2026-11-14

The provider tabs now show observations from live Recharge-wrapped sessions: running, waiting for a detected reset plus grace, native-retry ownership, manual cancellation and sent continuations. Each wrapper writes an atomic, private record scoped to its Recharge profile and process creation identity. Multiple terminals remain separate; the dashboard ignores dead/reused PIDs, malformed records and symlinks. Normal exit removes the record. No prompts, API keys or terminal transcripts are stored. Observation failures must not interrupt continuation.

These records describe the last observed terminal event, not fresh account-wide quota or successful task completion. They also cannot see terminals launched outside Recharge. This closes part of the dashboard visibility gap without inventing quota percentages. Remaining quota adapters and direct session delivery have explicit acceptance requirements in the [integration requirements](../requirements/2026-11-14_google-opencode-integration.md).
