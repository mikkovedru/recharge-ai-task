# AppImage release requirements

AppImage is an additional Linux x86_64 delivery format. It wraps the same PyInstaller executable as the raw/ZIP/Debian builds and retains the Ubuntu 24.04 / Mint 22, glibc 2.39 baseline. Packaging does not make a newer-glibc executable run on older distributions. GTK/tray/accessibility, host provider discovery, menu launch, autostart and native Goal helper relaunches need native verification separately from successful packaging. Windows and other architectures keep their existing release paths.

## Packaging and toolchain

Run the [Linux executable build](../../scripts/build_linux.sh), then [build_appimage.py](../../scripts/build_appimage.py). The packager assembles an AppDir containing the frozen executable, AppRun, desktop launcher, icon, AppStream metadata and license. The existing executable already bundles the GTK/Python libraries, so linuxdeploy would add another deployment layer; it is not required to embed update information. `appimagetool -u` performs that embedding and invokes its bundled `zsyncmake`. This is the supported approach described by the [AppImage update guide](https://docs.appimage.org/packaging-guide/optional/updates.html) and [appimagetool usage](https://github.com/AppImage/appimagetool/blob/main/README.md).

The official appimagetool and type-2 runtime downloads are SHA-256 pinned in [appimage-tools.json](../../packaging/linux/appimage-tools.json). A changed continuous-release download fails its checksum instead of silently changing the toolchain. Review upstream changes and update the pins deliberately. AppStream validation runs explicitly with `--no-net`; the tool's separate network-dependent validation is disabled. The pinned packager provides zstd SquashFS and zsyncmake. Run it in a temporary working directory because its zsync output is written relative to that directory. Tool extraction does not need FUSE. No system-wide tool installation is required.

```bash
PYTHON=.venv/bin/python bash scripts/build_linux.sh
.venv/bin/python scripts/build_appimage.py
cd dist/release
sha256sum -c SHA256SUMS-appimage.txt
./recharge-ai-task-1.0-x86_64.AppImage --appimage-updateinformation
./recharge-ai-task-1.0-x86_64.AppImage --appimage-extract-and-run --version
```

The packager also accepts `--tool` and `--runtime` paths for previously downloaded pinned files; checksums remain mandatory. The host build dependencies are the normal Linux build dependencies plus `appstream` and `desktop-file-utils`. A system with working FUSE can run the AppImage directly; extraction-and-run is the fallback when mounting is unavailable. A graphical session and the documented host tools/providers are still required for desktop operations.

## Update and publication contract

Embed exactly this update information:

```text
gh-releases-zsync|mikkovedru|recharge-ai-task|latest|recharge-ai-task-*-x86_64.AppImage.zsync
```

The [AppImage specification](https://github.com/AppImage/AppImageSpec/blob/master/draft.md#github-releases) defines the repository, channel and asset pattern. `latest` follows the latest public stable GitHub release, rather than permanently tracking one version tag. Each release must contain exactly one matching x86_64 pair:

- `recharge-ai-task-VERSION-x86_64.AppImage`
- `recharge-ai-task-VERSION-x86_64.AppImage.zsync`
- `SHA256SUMS-appimage.txt`

Upload the AppImage and zsync together. The zsync Filename and relative URL must identify the AppImage beside it, and its Length/SHA-1 must describe the final bytes. Rebuild the control file after any binary, metadata, signing or runtime change; then regenerate SHA-256 checksums. The packager verifies these properties before copying artifacts to the output directory. SHA-256 manifests identify artifact bytes; they are not a signature.

Publish from the source commit used to build the artifacts, with a matching version/tag. Do not attach new code to an old tag, mark a draft as a working update channel, or replace a stable release with a prerelease unexpectedly. The release workflow uploads both assets and the checksum file into its review draft. After source/tag publication and review, publish that draft and deliberately choose Latest. Verify GitHub's latest-release response, download both assets, check embedded metadata and checksums, then check an actual AppImageUpdate/Gear Lever update. A locally verified pair cannot establish a GitHub update while no public release exists.

Git pushes are a separate authorized action under this repository's standing policy. Local packaging does not push, create a tag or publish a release. The requested public upload requires a remote source/tag for the exact release code; absent that, retain the reviewed local artifacts and explicitly report the publication blocker.

## User installation and update management

Recommend [Gear Lever](https://gearlever.mijorus.it/docs/overview/) for graphical AppImage installation, menu integration and update management. Its [GitHub update settings](https://gearlever.mijorus.it/docs/github-updates/) use repository `mikkovedru/recharge-ai-task` and file pattern `recharge-ai-task-*-x86_64.AppImage`; these settings are also useful if a manager version needs manual source configuration. Embedded metadata enables the standard AppImageUpdate transport; do not claim every manager uses the same download algorithm or that an unreleased local build has an available online update.

[AM/AppMan](https://github.com/ivan-hc/AM) is the CLI alternative, with system and user-local installation modes. For an AppImage not in its catalog, the documented `am --launcher /path/to/file.AppImage` integrates a local file; `am -u --launcher` can try updating integrated images when `appimageupdatetool` is installed and delta updates are supported. See the [maintainer's launcher/update requirements](https://github.com/ivan-hc/AM#--launcher-integrate). Do not advertise a catalog installation command for Recharge until it has an accepted catalog entry.

Within an AppImage, `APPIMAGE` names the persistent outer file. Menu/autostart registrations and child GUI/CLI/Goal helper launches must use that file rather than `sys.executable` inside a temporary mount/extraction directory. The shared launch-path helper enforces that distinction. AppImage-manager installations own their menu entry; automatic portable launcher registration is skipped for an AppImage, while explicit `--install-desktop` remains available. Updaters replace the managed file; restart Recharge after an update so its running tray does not continue using the old code.

## AppImage managers and persistent launch paths

Recommend [Gear Lever](https://gearlever.mijorus.it/docs/overview/) for graphical installation and update management. Its [GitHub update setup](https://gearlever.mijorus.it/docs/github-updates/) can use repository `mikkovedru/recharge-ai-task` and asset pattern `recharge-ai-task-*-x86_64.AppImage`; embedded metadata also follows the standard AppImageUpdate transport. For CLI management use [AM/AppMan](https://github.com/ivan-hc/AM). For a locally downloaded file, `appman --launcher /path/to/recharge-ai-task-VERSION-x86_64.AppImage` integrates it; `appman -u --launcher` attempts delta updates when `appimageupdatetool` is installed. A catalog entry is a separate upstream contribution and is not assumed to exist. Follow AM’s maintained installation instructions to choose system or user mode.

The application uses the runtime-provided `APPIMAGE` path for CLI/desktop/Goal-helper relaunches and autostart, rather than registering the temporary mount executable. Automatic portable-menu registration is skipped under AppImage so Gear Lever/AM can own their launchers; explicit `--install-desktop` remains available and registers the persistent path. Linux autostart respects `XDG_CONFIG_HOME`. Native tests must still set the separate `RECHARGE_AI_TASK_CONFIG_DIR`; XDG isolation alone does not isolate Recharge settings.

On hosts with AppImageLauncher registered through `binfmt_misc`, an integration dialog can intercept a native startup check before Recharge opens. For a non-integrating verification run, set `APPIMAGELAUNCHER_DISABLE=1` on that one command, as documented by its [maintainer](https://github.com/TheAssassin/AppImageLauncher/discussions/679). Do not disable the system-wide registration or start/stop host manager services to run a test. This is distinct from a missing FUSE mount; the local packaged GUI check uses extraction-and-run plus the scoped launcher bypass.
