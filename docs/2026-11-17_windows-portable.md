# Windows portable package

Download `recharge-ai-task-1.0-windows-x86_64.zip` and `SHA256SUMS-windows.txt` from the same [GitHub Release](https://github.com/mikkovedru/recharge-ai-task/releases). Before a tagged release exists, open **Actions → Release → a successful run → Artifacts → windows-x86_64**. Extract that workflow artifact first to find the release ZIP and checksum file.

## Contents and startup

Extract the entire release ZIP into a permanent folder. Python and the application dependencies are bundled; install and sign in to your AI provider separately.

| File | Purpose |
| --- | --- |
| `recharge-ai-task.exe` | Windowed system tray application; open this to start Recharge. |
| `recharge-ai-task-cli.exe` | Console commands and interactive provider terminals; keep beside the tray EXE. |
| `README.md` | Provider setup, commands, settings location and compatibility limits. |
| `docs/target-selection.md` | Desktop target discovery and delivery limits. |
| `RELEASE.md` | Build, verification and publication instructions. |
| `OPEN_SOURCE.md`, `CONTRIBUTING.md`, `LICENSE` | Source, contribution and license information. |

Windows provides the tray and CLI. The GTK graphical dashboard is Linux-only. Use the tray menu to configure providers, launch a wrapped terminal or control monitoring. Enable login startup only after putting the extracted folder in its permanent location. Exit from the tray menu before replacing the executables during an update. Personal settings and logs stay in `%USERPROFILE%\.recharge-ai-task\`.

From PowerShell in the extracted directory:

```powershell
.\recharge-ai-task-cli.exe --version
.\recharge-ai-task-cli.exe --help
.\recharge-ai-task-cli.exe configure
.\recharge-ai-task-cli.exe quota
.\recharge-ai-task-cli.exe run --provider codex
.\recharge-ai-task-cli.exe run --provider claude
```

See [provider setup and monitoring](../README.md#choose-targets-and-start-monitoring) and [terminal commands](../README.md#terminal-commands) for other providers and options. The ZIP includes the linked usage documents for offline reading; deeper architecture links open the matching source version online.

## Verify the download

Keep the ZIP and checksum manifest together. Run this before extracting the release ZIP:

```powershell
foreach ($Line in Get-Content .\SHA256SUMS-windows.txt) {
    $Expected, $Name = $Line -split '  ', 2
    $Actual = (Get-FileHash -LiteralPath $Name -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($Actual -ne $Expected) { throw "Checksum mismatch: $Name" }
}
```

The executables are unsigned. Build-time CLI smoke checks and archive checks do not establish native tray, autostart, desktop delivery or real provider behavior. Those Windows 10/11 checks remain part of the [publication checklist](../RELEASE.md#verify-before-publishing).
