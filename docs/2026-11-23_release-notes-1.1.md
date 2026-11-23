# Recharge AI-task 1.1

<p align="center">
  <img src="assets/logo-lockup.png" width="240" alt="Recharge AI-task logo">
</p>

This release improves the Linux dashboard and prepares a standalone Flatpak download alongside the existing Linux and Windows packages.

- Idle dashboard refreshes reuse unchanged target rows and health indicators. Earlier layout feedback loops and overly frequent quota retries have been fixed.
- Fixed limits accept typed numbers. Enter saves, and Escape restores the previous value and mode.
- Targets with both actions disabled show a red **Off** badge.
- **Message status** shows what the provider's current turn state means for sending a message. **Goal status** retains its own recovery rules.
- The standalone x86_64 Flatpak launches Recharge as your user on the host so it can reach existing provider tools, chat data and the desktop session.

| Platform | File |
| --- | --- |
| Linux x86_64 portable | `recharge-ai-task-1.1-linux-x86_64.zip` or `recharge-ai-task` |
| Debian, Ubuntu or Mint x86_64 | `recharge-ai-task_1.1_amd64.deb` |
| Linux x86_64 AppImage | `recharge-ai-task-1.1-x86_64.AppImage` and its matching `.zsync` |
| Linux x86_64 Flatpak | `recharge-ai-task-1.1-x86_64.flatpak` |
| Windows x86_64 | `recharge-ai-task-1.1-windows-x86_64.zip` |

See the [README](../README.md) for launch and installation instructions, the [release guide](../RELEASE.md) for checksums and platform checks, and the [CPU investigation](../doc/investigations/2026-11-22_dashboard-idle-cpu.md) for the dashboard measurements.
