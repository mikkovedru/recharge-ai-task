# Project artwork

<p align="center">
  <img src="assets/logo-lockup.png" width="320" alt="Recharge AI-task logo">
</p>

Use the text-free blue **5h recharge** symbol for application and tray icons. Use the logo with the project name in documentation and the dashboard. The checked-in assets are resized copies of the approved artwork; documentation and program code use these assets rather than the original input files.

| Location | Purpose | Size |
|----------|---------|------|
| `docs/assets/logo-lockup.png` | Documentation logo with project name | 512 × 512 |
| `recharge_ai_task/assets/logo-lockup.png` | Dashboard logo source | 512 × 512 |
| `recharge_ai_task/assets/logo-symbol.png` | Tray source artwork | 512 × 512 |
| `recharge_ai_task/assets/icon-*.png` | Window and desktop icons | 16, 24, 32, 48, 64, 128, 256 px |
| `recharge_ai_task/assets/recharge-ai-task.ico` | Windows executable icon | 16–256 px in one ICO |

`branding.py` supplies the shared tray, window and desktop artwork. The tray adds an opaque background, dark outer edge and colored status strip. These stay visible on light and dark panels without relying on theme colors. The tooltip also states the status. Desktop startup entries use a persistent copy of the icon, so the icon survives a one-file executable exiting.

To regenerate the assets with Pillow installed:

```bash
python scripts/prepare_branding.py --symbol /path/to/symbol.png --lockup /path/to/logo-with-name.png
```

Python packages and frozen executables include runtime assets automatically. The Windows build uses the ICO for the CLI and combined desktop executable shell icons.

The dashboard scales the logo to the Settings button width, preserves its aspect ratio and uses device-scaled pixels for HiDPI displays. The logo does not force the Monitoring card to grow.

Hover over the dashboard logo to see the installed program version. Click it to open the GitHub repository, or right-click and choose **Copy GitHub repository link**.

## Linux file-manager and menu icons

Portable Linux ELF files do not provide the shell icon resource used by Windows executables. Nemo obtains a custom icon from GIO's `metadata::custom-icon` attribute. The desktop app copies its approved 256-pixel artwork to the user's persistent data directory and assigns that file URI to the executable and matching command symlinks. The default location is `~/.local/share/recharge-ai-task/icon.png`; `XDG_DATA_HOME` is respected. The app also creates its dashboard menu entry under `~/.local/share/applications/`. It does not replace the file type's generic icon for unrelated executables.

Portable frozen desktop launches refresh this integration when no installed package supplies the menu entry. Isolated profiles configured with `RECHARGE_AI_TASK_CONFIG_DIR` skip automatic installation. Source installs can opt in with `recharge-ai-task --install-desktop`. Release archives need no separate installer script. Run it again after moving the release. Icons on raw files depend on Nemo/GVfs metadata support; branded desktop launchers also work where that metadata is unavailable. Installation reports partial failures instead of silently claiming that file icons were assigned.

Debian packages install the icon and `/usr/share/applications/recharge-ai-task.desktop` as package-owned files, with GitHub and Uninstall actions. Frozen builds prefer that launcher whenever the package is present, instead of creating an unowned per-user override. On launch they retire an exact older generated shadow, including one pointing to a portable build, but preserve customized entries. This keeps Cinnamon’s package lookup working. AppStream metadata supplies the same display name, descriptions, logo and GitHub links to supporting software managers; Captain’s own package window does not display those icon/link fields.

See [tray reconnection](../doc/investigations/2026-11-04_cinnamon-tray-reconnection.md) for the separate native panel lifecycle issue.
