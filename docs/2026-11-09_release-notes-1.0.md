# Recharge AI-task 1.0

<p align="center">
  <img src="assets/logo-lockup.png" width="240" alt="Recharge AI-task logo">
</p>

First public release of [Recharge AI-task](https://github.com/mikkovedru/recharge-ai-task), licensed under the [MIT license](../LICENSE).

Continue selected AI tasks (by resuming goals and sending custom messages) after their quota usage limits are reset. Recharge AI-task supports **OpenAI Codex**, **Claude Code**, **Meta (Facebook) Muse Code**, **Google Gemini CLI**, **Google Antigravity CLI** and **OpenCode** in wrapped interactive terminals. Linux (dashboard, a system tray, and CLI terminal commands) and Windows (tray, CLI). User-friendly. Portable, `.deb`, `.AppImage` (incl `.zsync` delta files for updates).

## Included

- One Linux `recharge-ai-task` executable for the dashboard, tray and terminal commands; closing the dashboard keeps the tray available. The graphical dashboard requires Linux GTK.
- Windows tray application `recharge-ai-task.exe` and terminal companion `recharge-ai-task-cli.exe`, kept together in one portable ZIP with offline usage documentation, Windows startup/checksum instructions and the license.
- Terminal wrappers that observe usage-limit messages and quota recovery, plus monitoring for selected desktop targets and saved local Code sessions.
- Start/stop controls, quota information, optional login startup, private local settings and activity logs.
- Bundled Python runtime, English message catalog and Recharge artwork. No Python installation is needed for release downloads.
- Choose a `.deb` installation package with Linux desktop menu integration or a portable ZIP/raw executable or updateable AppImage.

## Downloads

| Platform | File |
|---|---|
| Linux x86_64 portable | `recharge-ai-task-1.0-linux-x86_64.zip` or raw `recharge-ai-task` |
| Debian / Ubuntu / Mint amd64 | `recharge-ai-task_1.0_amd64.deb` |
| Linux x86_64 AppImage | `recharge-ai-task-1.0-x86_64.AppImage` and matching `.AppImage.zsync` |
| Windows x86_64 | `recharge-ai-task-1.0-windows-x86_64.zip` |
| Checksums | `SHA256SUMS-linux.txt`, `SHA256SUMS-windows.txt` and `SHA256SUMS-appimage.txt` |

The Linux build targets compatible Debian / Ubuntu / Mint systems with glibc 2.39 or later (Ubuntu 24.04 / Mint 22 baseline).

The GUI was tested on Linux Mint 22.3 “Zena” Cinnamon, the [latest stable Linux Mint release](https://linuxmint.com/download.php) as of 2026-11-10. Debian and Ubuntu compatibility uses the stated baseline; their native GUI sessions have not been separately tested.

Windows builds automatically alongside Linux in the Release workflow. Before publication, downloads are available under the successful workflow run’s `windows-x86_64` artifact; version tags attach the ZIP and checksum manifest to the same draft release as Linux. Native tray and end-to-end provider operation still need confirmation on Windows. See the [Windows portable guide](2026-11-17_windows-portable.md).

## Start

1. Download the package for your platform. Extract ZIP downloads; on Linux allow the portable executable to run with `chmod +x recharge-ai-task`, or install the `.deb` through your package installer. For AppImage, allow execution and open the `.AppImage` file; keep its matching `.zsync` available for updates. See [AppImage installation and updates](../README.md#appimage-installation-and-updates).
2. Open `recharge-ai-task` on Linux or `recharge-ai-task.exe` on Windows. Use `recharge-ai-task-cli.exe` for Windows terminal commands.
3. Install and sign in to the provider tools you will use. Codex quota checks require the corresponding signed-in Codex CLI account; Claude Code and Muse Code use their subscription logins. Muse Code must support `muse usage --json`.
4. On Linux, choose targets and actions, then start monitoring. For a wrapped terminal, use `recharge-ai-task run` with the desired provider options.

Linux supports X11 and Wayland. X11/XWayland window input needs `xdotool`; native Codex Goal recovery also needs accessibility and a clipboard manager. Native Wayland Goal controls are not supported, and Wayland trays require AppIndicator/StatusNotifier support. Desktop routing depends on provider compatibility; an uncertain send is not retried automatically.

Read the [README](../README.md), [release guide](../RELEASE.md) and [known compatibility limits](../README.md#compatibility-and-limits). Report problems in [GitHub Issues](https://github.com/mikkovedru/recharge-ai-task/issues).
