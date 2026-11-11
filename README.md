# Recharge AI-task

Continue selected AI tasks after their usage limits are reset. Recharge AI-task supports **OpenAI Codex**, **Claude Code** and **Meta (Facebook) Muse Code**, plus **Google Gemini CLI**, **Google Antigravity CLI** and **OpenCode** in wrapped interactive terminals, through a Linux dashboard, a system tray, and terminal commands. Version **1.0** · [MIT license](LICENSE).

![Recharge AI-task main screen](docs/assets/2026-11-09_Screenshot_Recharge-AI-task_Main-screen.png)

The Linux dashboard brings local chats, selected recipients, recovery actions, provider quota and activity logs into one window. Each recipient can have its own message, signal limits and recovery plan.

## Download and start

Get the files from [GitHub Releases](https://github.com/mikkovedru/recharge-ai-task/releases). Python is bundled; install and sign in to the AI provider you intend to use separately.

| Platform | Download | Start |
|---|---|---|
| Linux x86_64 (Debian with glibc 2.39+ / Ubuntu 24.04 / Mint 22 family) | Linux ZIP or raw `recharge-ai-task` | Extract if needed, allow execution, then open `recharge-ai-task` |
| Debian / Ubuntu / Mint x86_64 (glibc 2.39+) | `recharge-ai-task_1.0_amd64.deb` | Install with `sudo apt install ./recharge-ai-task_1.0_amd64.deb`, then open from the app menu |
| Windows x86_64 | Windows ZIP | Extract both executables together and open `recharge-ai-task.exe` for the tray |

For a portable Linux download:

```bash
chmod +x recharge-ai-task
./recharge-ai-task
```

Linux has **one executable** for the dashboard, tray and terminal commands. The portable app registers a per-user menu entry and file icon when opened; keep the executable at a permanent location. You can refresh integration with `./recharge-ai-task --install-desktop`. No installer script is needed. Closing the dashboard leaves the tray running; use **Exit** in the tray to quit. `./recharge-ai-task --tray` starts without opening the dashboard.

Windows currently provides a **tray and terminal interface**, without the Linux graphical dashboard. Keep `recharge-ai-task-cli.exe` beside the tray executable for terminal actions and configuration. Windows is included in the release plan; native verification is tracked in the [release guide](RELEASE.md).

### Remove the Debian package

Use Cinnamon’s **Uninstall** action or Synaptic to remove the installed package. You can also run `recharge-ai-task --uninstall` to open the Recharge removal dialog with its logo and GitHub link; it opens a terminal where apt requests your password and confirmation. The launcher also includes an **Uninstall Recharge AI-task…** action. Your personal settings and logs are retained. Captain’s downloaded `.deb` window offers reinstall only; its buttons are controlled by the system installer. Captain also changes the short description to title case (rendering `AI` as `Ai`) and does not display the package logo or GitHub Homepage link. The stored description preserves `AI` correctly. The Recharge removal dialog and supporting software managers show the logo and GitHub link; opening the `.deb` in Captain does not.

After updating from an older build, launch `/usr/bin/recharge-ai-task` once. It removes the older generated per-user launcher that could hide the package-owned menu entry and prevent Cinnamon from finding the package. Customized user launchers are preserved and reported for manual review.

## Choose recipients and start monitoring

1. Open your AI app and sign in. For Codex quota checks, install and sign in to [Codex CLI](https://github.com/openai/codex) with the corresponding account. Claude Code uses its subscription login. Muse Code requires a subscription and a working `muse usage --json` command (integration tested with 1.4.13).
2. Open Recharge AI-task. Select the chats to receive recovery signals and enable **Send message**, **Resume goal** (Codex only), or both in **Recipients & actions**.
3. Review each recipient's message, grace period and signal allowances, then start monitoring. Provider filters change visibility; hidden recipients retain their plans.
4. Recharge waits for exhausted quota to become usable, waits the grace period (60 seconds by default), and checks again before sending the selected actions. Monitor progress and failures in the provider status and activity log.

Local Claude Code and Muse Code sessions can be resumed by their exact session ID. An already active session is not taken over. Use a wrapped terminal for an interactive session that should keep running. Muse consumer app/browser chats are not supported recipients.

## Terminal commands

Run these beside the Linux executable. On Windows replace `./recharge-ai-task` with `.\recharge-ai-task-cli.exe`.

```bash
./recharge-ai-task --version
./recharge-ai-task quota
./recharge-ai-task targets --json
./recharge-ai-task watch
./recharge-ai-task run --goal
./recharge-ai-task run --provider claude
./recharge-ai-task run --provider gemini
./recharge-ai-task run --provider antigravity
./recharge-ai-task run --provider opencode
./recharge-ai-task run --provider muse
./recharge-ai-task configure
./recharge-ai-task --help
```

`run` wraps a provider CLI in a terminal and sends its continuation after quota recovery. Keep that terminal open. Put provider arguments after `--`, for example `./recharge-ai-task run --provider claude -- --resume SESSION_ID`. `watch` uses the saved desktop recipients. Every command has `--help`.

Google: install and sign in to [Gemini CLI](https://geminicli.com/docs/get-started/authentication/) (`gemini`) or [Antigravity CLI](https://antigravity.google/docs/getting-started?tab=cli) (`agy`), then run the matching `--provider` command above. Set custom executables with `--gemini PATH` / `--antigravity PATH`, `GEMINI_CLI_PATH` / `ANTIGRAVITY_CLI_PATH`, or save their paths and interactive arguments in Settings. Each has a provider tab; OpenCode stays last. Automatic continuation requires an explicit supported reset time in a stopped usage/quota-limit banner. Native retries, model fallback and choice dialogs stay in control, and typing cancels the pending continuation. These are wrapped-terminal integrations: shared dashboard quotas, saved desktop recipients, Antigravity app/IDE delivery and Codex Goal actions are unavailable. Use `/stats` in Gemini and `/usage` in Antigravity for their native usage views. See [Google integration design and limits](doc/architecture/2026-11-11_google-terminal-providers.md).

OpenCode: install and sign in to [OpenCode](https://opencode.ai/docs/cli/), then use `./recharge-ai-task run --provider opencode`. Set a custom executable with `--opencode PATH` or `OPENCODE_CLI_PATH`, or save it with `configure --provider opencode --opencode PATH`. Dashboard settings and the tray can also configure and launch OpenCode. Its provider tab explains terminal support and shows the launch command; it does not invent shared quota percentages or desktop recipients. Provider filter buttons wrap when needed, and OpenCode stays last. Arguments after `--` go to its interactive CLI. Automatic continuation requires a terminal usage/rate-limit message with an explicit “try again in” duration or “try again at” time, followed by the configured grace period. Native automatic retry messages suppress extra continuation prompts, and typing during the wait cancels the pending prompt. Limits without a supported reset time remain under manual control. OpenCode uses the model provider chosen in its own configuration; shared quota checks, dashboard chat recipients and Codex Goal commands are unavailable. Noninteractive `opencode run`, servers and remote attachment are outside this wrapper integration.

## Compatibility and limits

The GUI was tested on **Linux Mint 22.3 “Zena” Cinnamon**, the [latest stable Linux Mint release](https://linuxmint.com/download.php) as of 2026-11-10.

- **Linux:** release builds target compatible x86_64 Debian / Ubuntu / Mint systems with glibc 2.39 or later (Ubuntu 24.04 / Mint 22 baseline). Other distributions require testing.
- **X11 / XWayland:** window input needs `xdotool`. Prefer Codex chat-ID recipients when available.
- **Wayland:** the dashboard and chat messages work without X11. Window delivery requires accessible composer and Send controls in the target app. The tray needs AppIndicator/StatusNotifier support; GNOME may need an extension.
- **Codex Resume goal:** requires Codex under X11 or XWayland, accessibility and a clipboard manager. Native Wayland Goal controls are not supported. Use **Send message** for a native Wayland Codex window.
- Desktop integrations depend on provider versions and, for Codex chat routing, private desktop interfaces. Unsupported or ambiguous targets can fail. An uncertain send is not retried automatically. Prompt acceptance does not guarantee the task completed or eliminate later permission requests.
- This tool continues work after limits recover; it does not bypass quotas. Review recipient messages and permissions before enabling automatic actions.

Settings and logs are local, normally under `~/.recharge-ai-task/` (Windows: `%USERPROFILE%\.recharge-ai-task\`). `RECHARGE_AI_TASK_CONFIG_DIR` selects an isolated profile. Existing settings from the original project are imported on first launch without deleting the originals.

## More information

- [GitHub repository and source](https://github.com/mikkovedru/recharge-ai-task)
- [Report a bug or request a feature](https://github.com/mikkovedru/recharge-ai-task/issues)

- [Target discovery, delivery and compatibility](docs/target-selection.md)
- [Provider integration design](doc/architecture/2026-11-07_unified-provider-chats.md)
- [Builds, release formats and publishing](RELEASE.md)
- [Contributing and source setup](CONTRIBUTING.md)
- [Source distribution and license](OPEN_SOURCE.md)

Based on [Autumnpoem/codex-autocontinue](https://github.com/Autumnpoem/codex-autocontinue).

Recharge AI-task adds the multi-provider dashboard, recipient controls, quota monitoring, tray integration and verified delivery paths maintained here.
