# Recharge AI-task

<p align="center">
  <img src="docs/assets/logo-lockup.png" width="360" alt="Recharge AI-task logo">
</p>

[![MIT License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Ubuntu%20x86__64-lightgrey.svg)](#release-builds-x86_64-only)

> Auto-continue Codex, Anthropic Claude and Meta Muse Code after quota resets — CLI PTY wrapper and supported desktop watch, MIT.

The primary command, `recharge-ai-task`, opens the desktop app. Use
`recharge-ai-task-cli` for terminal operation. The current project version is **1.0**.

### Usage at a glance

**CLI setup**

```bash
recharge-ai-task-cli configure          # choose mode (cli/desktop) and defaults
```

**For the Linux GUI, run `recharge-ai-task` and use Settings directly.**

**Then pick your workflow:**

| Scenario | What to run | Notes |
|-----------------|------------------------|--------------|
| **CLI + Goal mode** | `recharge-ai-task-cli --goal` | Wraps `codex` in terminal; first resume sends `/goal resume` |
| **CLI + normal** | `recharge-ai-task-cli` | Auto-sends `Continue` after reset |
| **CLI + task args** | `recharge-ai-task-cli --goal -- exec "your task"` | Pass args to codex after `--` |
| **Linux graphical dashboard** | `recharge-ai-task` | Select recipients, view quota, change settings, start/stop Desktop watch |
| **ChatGPT Codex desktop app** | `recharge-ai-task-cli watch` | Open Codex and save recipients in the GUI first |
| **Claude Code CLI** | `recharge-ai-task-cli run --provider claude` | Uses the Claude terminal limit/reset message and configured continuation text |
| **Claude desktop app** | `recharge-ai-task-cli watch --provider claude` | Select Claude windows in Settings and save recipients first; see [Claude setup](#anthropic-claude) |
| **Meta Muse Code** | `recharge-ai-task-cli run --provider muse` | Checks both subscription allowances with `muse usage --json`; see [Muse setup](#meta-muse-code) |
| **Start directly in tray** | `recharge-ai-task --tray` or `recharge-ai-task-cli tray` | Starts without opening the dashboard or starting monitoring |
| **Check quota only** | `recharge-ai-task-cli quota` | Shows short/long window usage |
| **No Python (Release zip)** | Run `recharge-ai-task.exe` (Win) or `recharge-ai-task` (Linux) | Two binaries: CLI and combined desktop app. Keep them together for CLI integration; Codex CLI must be installed and signed in |

**Prerequisites:** Install [Codex CLI](https://github.com/openai/codex) and sign in with ChatGPT, or follow [Claude setup](#anthropic-claude). Linux desktop mode also needs `sudo apt install xdotool` (X11). Native Goal signals use Codex's Resume goal control and require accessibility plus a clipboard manager (included in Mint Cinnamon). Source installs also need `gir1.2-atspi-2.0`.

→ [Full guide](#english)

---

<a id="english"></a>

## Overview

Auto-continue **Codex**, **Claude Code** and **Meta Muse Code** after usage limits reset. Codex and Claude also support selected desktop recipients.

When quota is exhausted, Recharge AI-task waits for recovery and the grace period, then continues selected tasks. Codex recipients have independent Prompt and Goal signals; Codex CLI Goal mode enters `/goal resume` on its first recovery. Claude recipients use the configured continuation message. See [Claude setup](#anthropic-claude) for authentication and native continuation behavior.

### Features

- **Two modes**
  - `cli` — PTY wrapper around `codex`, `claude` or `muse` in the terminal
  - `desktop` — watches the selected provider's quota and signals its saved recipients
- **Reset detection** — Codex terminal parsing plus `codex app-server`; Claude terminal reset messages or subscription usage for desktop; Muse Code's limit banner and official subscription-allowance command
- **Cross-platform** — Windows and Ubuntu (x86_64); `pip install` for developers
- **Optional tray app** — system tray on Windows & Linux (start/stop, quota, autostart)
- **MIT licensed** — open source, release-ready

### How Codex recovery works

```
┌─────────────────────────────────────────────────────────────┐
│                       Recharge AI-task                      │
├──────────────────────────┬──────────────────────────────────┤
│      CLI mode (PTY)      │       Desktop mode (watch)        │
│  spawn codex in PTY      │  poll quota API every N seconds   │
│  parse terminal output   │  on 100% → sleep until reset      │
│  + quota API fallback    │  → type into desktop window       │
│  → write to PTY          │                                   │
└──────────────────────────┴──────────────────────────────────┘
                              │
                              ▼
                    codex app-server (quota API)
                    ChatGPT account / Codex CLI auth
```

**Why PTY for CLI?** Usage limits appear in the Codex CLI session. A PTY can read output and write input like a real terminal — no IDE plugin required.

**Why dual-channel parsing?** Terminal messages may change format. Live quota checks detect early resets and usable added credits; the default **60s grace** starts when recovery is observed. If the CLI quota API is unavailable, the later terminal/API reset forecast remains its fallback.

**Desktop delivery:** Desktop mode reads the quota API and addresses explicitly selected recipients. Linux chat targets use the running desktop’s private routing socket; window targets use keyboard input in the selected window. See [target discovery and delivery](docs/target-selection.md) for compatibility and focus requirements.

### Quick start

#### 1. Install

**Windows (full — CLI + tray):**

```powershell
pip install "recharge-ai-task[all]"
recharge-ai-task-cli configure
```

**Ubuntu / Debian (tray + desktop):**

```bash
sudo apt install xdotool    # required for desktop mode on X11
pip install "recharge-ai-task[tray]"
recharge-ai-task-cli configure
```

**CLI only (no tray):**

```bash
pip install recharge-ai-task
recharge-ai-task-cli configure --mode cli
```

#### 2. First-time setup (mode and defaults)

```bash
recharge-ai-task-cli configure
# non-interactive example:
recharge-ai-task-cli configure --mode desktop --goal
```

On first run in an interactive terminal, the setup wizard starts automatically if no config exists.

Config file: `~/.recharge-ai-task/config.json`

| Setting | Description |
|---------|-------------|
| `mode` | `cli` or `desktop` |
| `goal_mode` | CLI: first `/goal resume`; migration default for old Desktop selections |
| `grace_seconds` | Extra wait after reset (default `60`) |
| `continue_prompt` | Text to send (default `Continue`) |
| `desktop_targets` | Saved chat/window recipient identities |
| `poll_seconds` | Shared quota polling interval for the dashboard, Desktop watch and CLI recovery |
| `autostart` | Startup preference; the GUI also checks the OS registration |

#### 3. Run

```bash
# CLI mode (default when mode=cli)
recharge-ai-task-cli --goal
recharge-ai-task-cli --goal -- exec "your long task"

# Linux GUI: choose and save recipients, then start Desktop watch
recharge-ai-task
# Terminal watcher using the saved recipients
recharge-ai-task-cli watch

# Check quota
recharge-ai-task-cli quota

# Start only the system tray (Windows / Linux)
recharge-ai-task --tray
# Equivalent command through the CLI:
recharge-ai-task-cli tray
```

### Desktop app support

The **ChatGPT Codex desktop app** is supported via `desktop` mode:

1. Choose and save one or several chat/window recipients in the Linux GUI (or with `targets --select`).
2. Poll `codex app-server` quota API using the CLI account.
3. Wait for every exhausted window to recover, retain the grace period, and check fresh quota.
4. Signal each saved recipient once; retry confirmed failures independently.

Linux chat delivery uses exact IDs and the desktop router. X11 window delivery
requires `xdotool` and a focused composer. The GTK dashboard is available on
Linux. Windows uses CLI selection and window input. Legacy title-pattern
matching has been replaced by explicit recipients.

### Distribution options

| Method | Best for | How |
|--------|----------|-----|
| **Tray app** | Non-technical users | Download [GitHub Release](https://github.com/mikkovedru/recharge-ai-task/releases) zip, run `recharge-ai-task` |
| **Pre-built binary** | Users without Python | CLI plus one combined GUI/tray executable; no separate GUI runtime |
| **pip install** | Developers | `pip install "recharge-ai-task[all]"` |

> End users need their selected provider's CLI installed and signed in. This tool handles auto-continue after quota resets.

#### Tray menu

| Item | Action |
|------|--------|
| Start Codex (Goal) | New console, `--goal` mode |
| Start Codex (Normal) | Auto-send `Continue` after reset |
| Start Desktop Watch | Desktop app mode |
| Stop | End running process |
| Show Quota | Notification with usage |
| Settings… | Re-run configure wizard |
| Run at startup | Toggle autostart |
| Exit | Stop and quit tray |

The tray keeps the blue 5h recharge logo in both states. Its bottom strip is
**yellow** when idle and **green** when running; the tooltip also reports the state.

#### Autostart

| Platform | Mechanism |
|----------|-----------|
| Windows | `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\recharge-ai-task-tray.bat` |
| Linux | `~/.config/autostart/recharge-ai-task-tray.desktop` |

Toggle via tray menu **Run at startup**.

### Release builds (x86_64 only)

Official binaries target **x86_64** on Windows and Ubuntu only (no ARM builds in official releases).

Build scripts keep generated PyInstaller specifications and intermediate files
under `build/`. Finished executables are written to `dist/`.

**Windows:**

```powershell
pip install "recharge-ai-task[all,dev]"
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
# → dist/recharge-ai-task-cli.exe, dist/recharge-ai-task.exe
```

**Ubuntu:**

```bash
pip install "recharge-ai-task[tray,dev]"
bash scripts/build_linux.sh
# → dist/recharge-ai-task-cli, dist/recharge-ai-task
```

The desktop executable runs independently for the GUI and tray. Keep the CLI
beside it to use CLI actions from the tray and to open the desktop from the CLI.
Linux includes small compatibility scripts named `recharge-ai-task-gui` and
`recharge-ai-task-tray`; Windows includes matching `.cmd` launchers. Neither
contains another bundled runtime.

**GitHub Release** (suggested attachments):

- `recharge-ai-task-windows-x86_64.zip`
- `recharge-ai-task-linux-x86_64.tar.gz`

**PyPI** (optional):

```bash
pip install build twine
python -m build
twine upload dist/recharge_ai_task-*.tar.gz dist/recharge_ai_task-*.whl
```

### Resource usage

| State | RAM | CPU |
|-------|-----|-----|
| Tray idle | ~30–50 MB | ~0% |
| CLI wrapper | +~5 MB over Codex | ~0% when waiting |
| Desktop watch | ~20–40 MB | ~0% (scheduled sleep) |
| Codex running | Codex itself dominates | task-dependent |
| Limit triggered | One quota API call (~1–2s) | brief spike |

You can leave the tray running in the background — it is lightweight. Codex itself is what consumes resources.

### CLI options

| Flag | Description | Default |
|------|-------------|---------|
| `--grace SECONDS` | Wait after reset | `60` |
| `--continue TEXT` | Auto-send text | `Continue` |
| `--goal` | First send `/goal resume` | off |
| `--codex PATH` | Codex executable | auto-detect |
| `--provider codex/claude/muse` | Select the AI provider | saved setting, initially `codex` |
| `--claude PATH` | Claude Code executable | auto-detect |
| `--muse PATH` | Muse Code executable | auto-detect |

The CLI, tray and dashboard use English. Language selectors and language
environment variables are no longer supported. Existing language preferences
are ignored, and the previous shipped continue prompt becomes `Continue`.
Custom prompts (including non-English text) and recipient choices are preserved.

### FAQ

**Does it support the new ChatGPT Codex desktop app?**  
Yes — use `desktop` mode or tray **Start Desktop Watch**. It uses the same quota API as CLI, not Electron hooks.

**Does it work with Cursor / VS Code?**  
It wraps **Codex CLI**, **Claude Code CLI** or **Muse Code** in a terminal. IDE extensions are out of scope; run `recharge-ai-task-cli` in a terminal instead.

**What happens at quota reset?**  
Detect availability through live checks, including manual early resets and usable additional credits, then wait the configured grace period (60 seconds by default) and send the selected actions. A forecast timestamp does not delay an observed early recovery.

**Can I run it 24/7?**  
Yes. Idle tray/watch uses negligible CPU; only Codex tasks consume meaningful resources.

### Project layout

```
recharge-ai-task/
├── recharge_ai_task/       # Main package
│   ├── cli.py          # Entry point
│   ├── configure.py    # Mode and defaults wizard
│   ├── wrapper.py      # CLI PTY mode
│   ├── watch.py        # Desktop watch mode
│   ├── tray.py         # System tray
│   ├── quota.py        # codex app-server API
│   ├── parser.py       # Limit message parser
│   ├── i18n.py         # Shared English messages
│   └── locales/        # English message catalog
├── scripts/            # build_*.ps1 / build_*.sh, fake_codex.py
├── tests/              # Automated regression tests
├── LICENSE             # MIT
├── RELEASE.md          # Release checklist
└── CONTRIBUTING.md
```

### Development

```bash
git clone https://github.com/mikkovedru/recharge-ai-task.git recharge-ai-task
cd recharge-ai-task
pip install -e ".[all,dev]"
pytest tests/ -v
```

Tests cover Codex, Claude and Muse limit parsing, PTY continuation, desktop recovery,
provider isolation, quota failures, recipient accounting and GTK controls.

See also: [CONTRIBUTING.md](CONTRIBUTING.md) · [RELEASE.md](RELEASE.md) · [OPEN_SOURCE.md](OPEN_SOURCE.md)

### Requirements

- Python 3.10+
- The selected provider's CLI installed and signed in: [Codex CLI](https://github.com/openai/codex) with ChatGPT, [Claude Code](https://code.claude.com/docs/en/setup) with Claude, or [Muse Code](https://dev.meta.ai/docs/muse-code) with a Meta subscription
- Windows CLI mode: `pywinpty` (included in `[windows]` extra)
- Linux desktop mode: `xdotool` on X11

### Limitations

- Official release binaries: **x86_64 only** (Windows + Ubuntu)
- Desktop mode on Linux: **X11 only** (Wayland → use CLI mode)
- Codex desktop quota requires local Codex CLI auth (`codex app-server` must work)
- Claude desktop quota requires a local Claude Code subscription login and its private usage endpoint
- Terminal limit message formats may change; Codex has a quota API fallback, while Claude CLI uses the printed reset
- Muse continuation supports wrapped terminal sessions; consumer Muse app/browser chats have no continuation bridge in this integration

### Logs

When a limit is hit (CLI mode), stderr shows:

```text
[recharge-ai-task-cli] limit detected ('4 hours 12 minutes'), source=quota API, will send 'Continue' at 2026-07-13 04:01:00
[recharge-ai-task-cli] auto-continue sent
```

Log files: `~/.recharge-ai-task/tray.log`, `~/.recharge-ai-task/wrapper.log`

### GitHub repository

| Field | Value |
|-------|-------|
| **Repository** | [Recharge AI-task source](https://github.com/mikkovedru/recharge-ai-task) |
| **GUI / package name** | `recharge-ai-task` (also the pip install name) |
| **CLI command** | `recharge-ai-task-cli` |
| **Description** | Auto-continue Codex, Claude and Meta Muse Code after quota resets — Windows & Ubuntu x86_64, MIT |
| **License** | MIT |
| **Topics** | `codex`, `openai`, `chatgpt`, `automation`, `quota`, `rate-limit`, `cli`, `python`, `windows`, `linux`, `tray-app` |

Repository: [Recharge AI-task source](https://github.com/mikkovedru/recharge-ai-task)

### License

MIT — see [LICENSE](LICENSE).

---

## Project identity and upgrades

The application is **Recharge AI-task**. Its package and desktop command use
`recharge-ai-task`; terminal commands use `recharge-ai-task-cli`. The Python
package is `recharge_ai_task`.
Run `recharge-ai-task` for the dashboard. Resize columns by dragging their edges,
click headers to sort, and drag headers to reorder them. Long text wraps; column
widths, positions and sorting are remembered between launches. The visible
**Last active** column shows each chat's last update in Codex in local time.
Chats sort newest first by default; you can choose and save another sort.
The resizable **Recipients & actions** panel shows each selected item's
automatic/manual plan, effective message and used/remaining allowances. Set global Message and Goal
activation limits beside the default message, then override either limit or the
message for individual recipients. Counts persist until explicitly reset and
cover manual sends and automatic recovery. Unconfirmed sends keep their allowance.
See [recipient policies and allowances](docs/target-selection.md#recipient-messages-and-continuation-limits)
for action ordering, skipped actions and counter reset behavior.

Settings now live in `~/.recharge-ai-task/config.json`. On the first default
launch, existing settings from the previous name are copied byte for byte;
existing new settings are never overwritten and the original remains a backup.
Explicit `RECHARGE_AI_TASK_CONFIG_DIR` paths stay isolated. The previous
configuration-directory environment variable is accepted during upgrades,
with the new variable taking precedence. Language preferences are ignored.
Startup registration uses
`recharge-ai-task-tray.desktop` on Linux or `recharge-ai-task-tray.bat` on Windows;
enabling or disabling startup also retires its previous registration.

The GitHub repository is
[Recharge AI-task](https://github.com/mikkovedru/recharge-ai-task).
Use `origin` for this repository and `upstream` for
[Autumnpoem's original project](https://github.com/Autumnpoem/codex-autocontinue).
Development and releases use `master` as the only primary branch. There is no
local or `origin/main` branch. The local `upstream-sync` branch tracks the
original project’s `upstream/main`; update it before integrating upstream work.
See [CONTRIBUTING.md](CONTRIBUTING.md) for the remote and branch setup.

## Linux Mint Cinnamon

The tray uses the blue 5h recharge logo on an opaque white background with a dark border and a yellow (idle) or green (running) status strip. When Cinnamon's native XApp status applet is active, it uses XApp; with legacy or collapsible trays it uses an opaque XEmbed drawing surface at the actual allocated size, avoiding GTK StatusIcon caches and clipping. Image paths bypass symbolic icon recoloring; status is also shown by the tooltip and bottom color strip. Double-click toggles the dashboard; right-click opens the menu. The icon reconnects if Cinnamon or its tray socket is replaced. Cinnamon still controls the panel's icon size and whether its XApp status applet is visible.

```bash
sudo apt install python3-venv python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-xapp-1.0 gir1.2-atspi-2.0 xdotool
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[tray,dev]"
PYTHON=.venv/bin/python bash scripts/build_linux.sh
./dist/recharge-ai-task --tray
```

Alternatively, run from source with `bash scripts/run_tray.sh`. The launcher works from any directory. Use `RECHARGE_AI_TASK_CONFIG_DIR` for isolated settings during checks; live quota tests require `RECHARGE_AI_TASK_LIVE_TESTS=1`. `PYSTRAY_BACKEND` can explicitly override the Cinnamon backend selection.


## Combined dashboard and tray

`recharge-ai-task` contains the dashboard and tray in one executable.
On Linux, the frozen desktop app installs persistent menu and file-manager icons
for both executables on normal launch. To install or refresh these without opening
the app, run `recharge-ai-task --install-desktop`, or `./install-desktop.sh` beside
the unpacked release. Nemo uses per-file GIO metadata for raw executable icons;
that metadata is local to your user and does not travel inside the release archive.
Re-run the installer after moving the release directory. It also handles matching
command symlinks in `~/.local/bin`. GUI launchers open the dashboard; the CLI
launcher runs in a terminal. See [Linux desktop integration](docs/branding.md#linux-file-manager-and-menu-icons).

On Linux, normal launch opens the dashboard and starts its tray icon. To start
with only the icon, run either command:

```bash
recharge-ai-task --tray
recharge-ai-task-cli tray
```

Starting the tray does not start quota monitoring or send any signals.
If the app is already running, the tray command leaves the dashboard's current
visibility unchanged. Both launch forms repair the existing process's tray surface
and refresh timer without restarting monitoring or CLI jobs. `recharge-ai-task`
opens or restores its dashboard. Tray artwork fills the panel's physical pixel
allocation, including scaled displays.
Closing the dashboard keeps the tray and any active monitoring running.
The old `recharge-ai-task-gui` and `recharge-ai-task-tray` commands remain
compatibility launchers. CLI scripts must now use `recharge-ai-task-cli`;
`recharge-ai-task` opens the graphical app. `python -m recharge_ai_task` also
opens the graphical app; `python -m recharge_ai_task.cli` starts the CLI.
On Windows, the combined desktop executable starts in the tray by default;
the GTK dashboard remains Linux-only.

## Choose Codex signal recipients

The tray menu now has **Open Recharge AI-task…**. Select one or several chats or
windows; checkbox and prompt changes save automatically for quota-reset signals.
The picker shows titles,
thread/window IDs, process IDs, profiles, deep links, projects and live desktop
owners. Chat targets address a stable ID; window targets use the chat and focused
input currently shown in that window.

```bash
./dist/recharge-ai-task
./dist/recharge-ai-task-cli targets --gui
./dist/recharge-ai-task-cli targets --json
./dist/recharge-ai-task-cli targets --select THREAD_ID_1 --select THREAD_ID_2
```

After installing the Python package, use `recharge-ai-task`.
For a release archive, there are two binaries: CLI and combined desktop app.
`recharge-ai-task --help` lists desktop options including `--tray`;
`recharge-ai-task-cli --help` lists terminal commands. GUI launch commands also start the tray, or reuse the
running tray and bring its dashboard forward. Closing the window keeps the tray
and its watch available. Double-click the tray icon to hide the open dashboard
to the tray or restore it, preserving the current view. Right-click for the tray menu. Use **Exit** in that menu to quit the application.

The GUI saves checkbox and multiline prompt edits automatically, and shows
task and goal status refreshed every 15 seconds,
live quota usage and reset countdowns,
and the actual Desktop watch state. Startup registration and launch origin are
available in Settings. Settings also offers **Dark**, **Light** and **Auto (OS)**
color themes, with live preview and a saved preference.
Use **Start/Stop Desktop watch** and **Settings…** directly from this window.
Each row has independent **Send message** and **Resume goal** checkboxes.
Choices and message text save automatically for future quota recovery; editing
them does not send a manual signal. Adding the first recipient to an empty list
starts Desktop watch after saving; loading saved recipients or editing existing
ones does not start a stopped watch. **Send now to N recipients** applies those
choices immediately, even with monitoring off. Its label shows the recipient
count, and the button is disabled when no recipients are selected:

- **Send message** sends only the configured message.
- **Resume goal** verifies native activation and continues the goal without a user prompt.
- **Both** verifies Goal activation first, then sends the prompt to continue work.
- **Neither** excludes the recipient. Window recipients support Send message only.

Goal activation preserves the existing objective, budget and usage history.
Manual sends may resume paused goals even while a prompt turn is running,
without adding a competing empty turn; automatic quota recovery respects intentional
pauses and skips blocked, completed, budget-limited or already-running goals.
An independently selected Prompt still sends when the Goal action is skipped;
a failed or unconfirmed Goal action prevents the subsequent prompt. Results for
each recipient appear in the window. Starting watch after quota has recovered
also recovers selected usage-limited goals, after the grace period.
Settings contains the **Run the tray when I log in** checkbox and startup
details. The short **On**, **Off** or **Reloading** status sits beside
**Monitoring**. Its whole box has a bright green border when On, red when Off,
Waiting or in error, and yellow during transitions. The compact quota box and
logo match its height; the quota box keeps a neutral border with selected status
text colors. **Refresh** sits directly
below the list; **Copy link / ID** and **Open selected row** are on its right.
The recipient summary sits directly below the multiline message in the same
group; **Send now to N recipients** is beside the message, below its label. **Project** shows the name assigned in Codex;
**Project path** retains the chat's working path. Both precede **Kind**.
Old selections migrate to Prompt, or Prompt + Goal when old goal recovery was enabled.
Settings' **Quota polling (seconds)** controls all regular quota reads and retry
checks. An active dashboard reuses the watch's quota snapshot and schedule. There
is no independent 60-second refresh or hidden adaptive polling interval.
The recipient counts share a group with the default message and Send now;
immediate-send details are in the button's hover help. **Program log** includes
**Save log…** (with a dated text-file name) and **Clear log**. Clearing the view
preserves stored delivery history and allowances.
Saved changes automatically restart an active watch after a short debounce.
The previous worker finishes first, and quota-reset delivery accounting is
preserved. Empty selections or blank Prompt drafts suspend it until valid;
explicitly stopping the watch cancels pending restarts.

Choose targets before starting desktop watch. Local saved chats are included;
account-wide ChatGPT history and disconnected remote hosts are not enumerated.
See [the research, design and delivery notes](docs/target-selection.md) for protocol
compatibility, focus requirements and per-target retry behavior.


The status ⓘ buttons show a compact green/red continuation list for automatic
and manual actions, including the default allowance for new statuses.
**Check quota now** (**Ctrl+Shift+R**) wakes active monitoring so early resets
and added usable credits are checked immediately. **Ctrl+F** searches, **Ctrl+R**
refreshes chats and **Ctrl+Enter** sends. Focus a status ⓘ button and press
Enter/Space for its details.
See [status help and keyboard controls](docs/target-selection.md#status-help-and-keyboard-controls).

## Anthropic Claude

Select **Settings → AI provider → Anthropic Claude**, then save. The dashboard
shows Claude windows and Claude subscription quota. Codex remains the default
for existing installations. Each provider retains its recipients, overrides,
allowances and recovery checkpoints when you switch; one provider is monitored
at a time. Settings has separate executable paths and terminal arguments for
Codex and Claude. The tray's normal terminal action starts the selected provider;
its Codex Goal action is disabled for Claude.

### Claude Code terminal

Install [Claude Code](https://code.claude.com/docs/en/setup), sign in, and run:

```bash
recharge-ai-task-cli run --provider claude
recharge-ai-task-cli run --provider claude -- --continue
recharge-ai-task-cli run --provider claude -- --resume SESSION_ID
recharge-ai-task-cli run --provider claude --claude /path/to/claude --grace 60
# Save the provider for future CLI and tray launches:
recharge-ai-task-cli configure --provider claude --mode cli
```

Arguments after `--` go to Claude. Discovery uses `--claude`, `CLAUDE_CLI_PATH`,
PATH and the standard native-install location. The wrapper reads Claude's
terminal limit messages, including clock times, dated weekly resets and named
timezones. After the indicated reset plus grace, it submits the configured
message (default `Continue`). It never sends Codex's `/goal resume` to Claude,
even if Goal mode was previously enabled. Terminal recovery does not require
access to a quota API and cannot detect an early refill before the printed reset.
Unknown reset formats leave the terminal under manual control.
Typing in the terminal cancels Recharge's pending continuation for that limit.

Recent Claude Code versions have their own
[automatic continuation](https://code.claude.com/docs/en/interactive-mode#wait-for-a-usage-limit-to-reset).
When Claude reports native automatic continuation or its cancellation, the
wrapper leaves that wait to Claude and does not queue another prompt. To use
Recharge's continuation message and grace instead, turn off **Continue
automatically at usage limit** in Claude's `/config`. Leave the terminal open.
Interactive sessions are supported; `claude -p` exits after its response and
cannot be resumed through that terminated PTY.

### Claude desktop

1. Run `claude auth login` using the **same subscription account** as Claude desktop.
2. Open Claude desktop. In Recharge Settings, select Anthropic Claude and save.
3. Select **Send message** for the desired window recipients. Keep the intended
   chat open with its empty message composer focused. Adding the first recipient
   starts Desktop watch; use Start/Stop Desktop watch to control it thereafter.
4. Recharge observes exhaustion, waits for fresh usage to show recovery across
   every reported window, retains the configured grace, then sends the message.

The same workflow is available through the CLI:

```bash
recharge-ai-task-cli targets --provider claude --json
recharge-ai-task-cli targets --provider claude --select WINDOW_ID
recharge-ai-task-cli quota --provider claude
recharge-ai-task-cli watch --provider claude
```

Window discovery checks application identity, not page titles in browsers.
Delivery rechecks the provider, window ID, process and foreground window.
Recipients address the **current chat in a window**, not a saved Claude chat ID;
changing that window's chat changes where its next signal goes. OS input cannot
verify that Claude accepted a turn. Check the composer before retrying an
unconfirmed send. Per-recipient messages, limits and one-use overrides use the
same accounting as Codex. Native Codex Goal recovery is unavailable for Claude;
use Send message. Disable Claude's own automatic continuation for any desktop
session managed by Recharge to avoid independent continuations. Linux requires
X11 and `xdotool`; Windows uses foreground window input. Wayland and macOS are
not supported by this desktop delivery implementation.

Desktop quota uses the private read-only usage endpoint used by Claude Code's
`/usage`, authenticated from `~/.claude/.credentials.json` (or
`CLAUDE_CONFIG_DIR/.credentials.json`). It sends the existing access token only
to `https://api.anthropic.com/api/oauth/usage`, refuses redirects, never copies
it into Recharge settings/logs, and does not refresh or write Claude credentials.
API-key billing, setup-token-only logins and desktop-only logins do not supply
the required subscription profile access. Open Claude Code or sign in again when
its token expires. Missing, malformed, expired or failed usage reads remain
unavailable and never trigger a desktop recovery. HTTP 429 means the usage read
was throttled; it does not prove that model quota is exhausted.

The endpoint is undocumented and may change. See Anthropic's issue tracker for
[profile-scope requirements](https://github.com/anthropics/claude-code/issues/81015)
and [usage endpoint throttling](https://github.com/anthropics/claude-code/issues/30930).
Recharge checks all returned five-hour and weekly windows, including model
windows, conservatively waiting for every exhausted window. Enabling extra usage
alone does not prove that funds are usable, so it does not bypass those checks.
The configured quota polling interval applies to Claude too; increase it if
reads are throttled. No model requests are made to check quota.

## Meta Muse Code

Install [Muse Code](https://dev.meta.ai/docs/muse-code) **1.4.13 or later**, then
sign in with `muse login` using a Muse Code subscription. Meta added the
no-model-turn allowance command in
[1.4.13](https://dev.meta.ai/docs/muse-code/changelog). Confirm it works first:

```bash
muse usage --json
recharge-ai-task-cli quota --provider muse
recharge-ai-task-cli run --provider muse
recharge-ai-task-cli run --provider muse -- resume --last
recharge-ai-task-cli run --provider muse --muse /path/to/muse --grace 60
# Save Muse as the default for the terminal, dashboard and tray:
recharge-ai-task-cli configure --provider muse --mode cli
```

Discovery uses `--muse`, `MUSE_CLI_PATH`, PATH and the standard native-install
location. Arguments after `--` go to Muse; its executable path and saved arguments
are independent of Codex and Claude. Switching providers preserves their saved
recipients and policies. Muse uses the configured continuation message (default
`Continue`); a previously enabled Codex Goal setting does not inject `/goal resume`.
Muse's own goals remain available through its native `/goal` commands.

When Muse prints its native **Usage limit reached** banner, Recharge polls
`muse usage --json` at the configured **Quota polling (seconds)** interval.
It requires fresh availability in **both the session and weekly allowances**,
then waits the configured grace and rechecks before submitting the message.
An early refill is observed through those live checks. A failed check or renewed
exhaustion restarts the grace. Typing in the terminal cancels Recharge's pending
continuation for that limit. Leave the terminal open; a headless `muse exec` run
that exits cannot receive a message through its terminated PTY.

The schema-v1 allowance uses `usedPercent` and millisecond `resetsAtMs`, with
`asOfMs` identifying the observation. Recharge rejects missing, malformed,
unsupported or older-than-two-minute observations, and timestamps more than
30 seconds in the future. A missing window never becomes a fabricated zero.
Terminal recovery also requires an observation made after the detected limit;
an earlier cached "available" allowance cannot trigger continuation.
`allowance: null` with `reason: api_key` means API-key billing, not available
subscription quota. A login failure or missing allowance keeps recovery waiting;
run `muse login` and `muse usage --json` to diagnose it. Recharge does not read
Meta credentials, make a model probe, or call a private Meta HTTP endpoint.
Allowance subprocesses disable launcher auto-updates so polling cannot start an
update on every check; the wrapped interactive Muse command retains its normal
launcher behavior.

### Muse in the dashboard and tray

Choose **Settings → AI provider → Meta Muse Code**. The dashboard shows the
subscription session and weekly allowance and offers **Start Muse Code CLI**.
The tray has **Start Muse Code** too. These open a terminal using the same wrapper
and saved Muse arguments. Settings keeps its mode at CLI for this provider.
The dashboard's quota display refreshes on the configured interval; recovery in
the running terminal performs its own checks when it encounters a limit.

Consumer **Muse app/browser chats are not continuation recipients** in this
integration. They are a separate product from Muse Code and must not inherit its
subscription quota or Codex/Claude routing. `targets --provider muse` explains
this limit instead of guessing a window or browser identity; `watch --provider
muse` directs you to the wrapped terminal. Native Codex Goal recovery and desktop
recipient policies do not apply to Muse terminal sessions.

This boundary was checked against Muse Code 1.4.13 and the official
[MSP transport documentation](https://meta-models.github.io/muse-code-sdk/next/guides/msp-wire/framing-and-caps/):
normal interactive sessions host their runtime in-process; a new `muse serve`
stdio process does not control an already-open terminal session. The installed
socket host requires a separate client-credential handshake, and the local
peer-message CLI reported `external_agent_ingress_closed`. Recharge neither
impersonates that client nor sends peer messages as a substitute for user input.
A supported app/browser continuation interface would be needed for that workflow.
