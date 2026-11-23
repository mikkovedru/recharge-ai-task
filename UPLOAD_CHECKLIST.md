# Upload checklist

<p align="center">
  <img src="docs/assets/logo-lockup.png" width="200" alt="Recharge AI-task logo">
</p>

Repository: [Recharge AI-task](https://github.com/mikkovedru/recharge-ai-task)

## Source files

Commit project source, English documentation, tests, build scripts and workflows. Include the resized artwork in `recharge_ai_task/assets/` and `docs/assets/`. The English message catalog is `recharge_ai_task/locales/en.json`. See [OPEN_SOURCE.md](OPEN_SOURCE.md) for the source layout and [docs/branding.md](docs/branding.md) for artwork sizes.

## Keep local files out of Git

| Path | Purpose |
|------|---------|
| `dist/` | Built executables and packages; upload release archives as attachments |
| `build/` | PyInstaller intermediate files |
| `*.egg-info/` | Local Python package metadata |
| `.pytest_cache/`, `.venv/` | Test cache and development environment |
| Generated root-level `*.spec` files | Temporary PyInstaller build specifications |
| Original input artwork | Use converted project assets instead |
| `~/.recharge-ai-task/` | Private user settings |

Keep `AGENTS.md` local as instructed by the repository owner. Review `git status` and the staged diff before committing to avoid including private settings or unrelated local files.

## Git remotes and publishing

`origin` is the Recharge AI-task repository. `upstream` is the original Autumnpoem repository. `master` is the only primary branch; do not publish a duplicate `main` branch. The local `upstream-sync` branch tracks `upstream/main` for incoming changes from the original repository. For a checkout that already has both remotes:

```bash
git remote set-url origin https://github.com/mikkovedru/recharge-ai-task.git
git remote set-url upstream https://github.com/Autumnpoem/codex-autocontinue.git
git config remote.pushDefault origin
```

Push only when you intend to publish the reviewed commits:

```bash
git push -u origin master
```

## Release attachments

Use only the explicit outputs from `dist/release/`, including platform ZIPs, the raw Linux executable, `.deb`, the `.AppImage`/`.AppImage.zsync` pair, `SHA256SUMS-appimage.txt`, the standalone `.flatpak` and its checksum, and per-platform SHA-256 manifests. Publish the AppImage and its matching zsync together; verify their checksums and embedded update information, and deliberately select Latest after reviewing the draft. See the [AppImage publication contract](doc/requirements/2026-11-17_appimage-release.md). Linux ships one executable. Windows ships the tray executable with `recharge-ai-task-cli.exe`; obsolete GUI/tray aliases and the desktop installer script are excluded. Follow [RELEASE.md](RELEASE.md) for native validation, version checks, a draft release and manual publication.
