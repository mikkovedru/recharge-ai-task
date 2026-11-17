# Release and build guide

Current version: **1.0**, tag **v1.0**. Source metadata and the logo tooltip use 1.0; Windows file/product resources use 1.0 (numeric resource: 1.0.0.0). `python scripts/check_version.py --tag v1.0` checks source, installed metadata and tag. Do not reuse a published tag for different code. Existing local v1.1.0/v1.1.1 tags are retained; this release intentionally uses the requested 1.0 version. When publishing, explicitly select whether 1.0 should be marked Latest rather than assuming version ordering will choose it.

## Release formats

| Format | 1.0 decision | Considerations |
|---|---|---|
| Linux ZIP | Ship | One executable, offline usage/build documentation and license; file managers may require restoring the executable permission |
| Raw Linux `recharge-ai-task` | Ship | Same executable, convenient for updates; `chmod +x` after download |
| `.deb` (amd64) | Ship; owner tested installation/use | Debian / Ubuntu / Mint with glibc 2.39+; Ubuntu 24.04 / Mint 22 baseline; installs binary, menu entry, icon and license |
| Windows ZIP | Ship; owner approved proceeding | Tray EXE plus console CLI EXE, offline usage/build documentation and license; no Linux GTK dashboard |
| AppImage (x86_64) | Build with update metadata and paired zsync | Same glibc 2.39 baseline; publish both files and verify GTK/tray/accessibility and host CLI discovery |
| Flatpak | Excluded by owner | Host processes, provider files/sockets and accessibility need deliberate permissions and host execution adapters; a sandbox wrapper alone would break features |
| `.tar.gz`, RPM, ARM, macOS, Windows installer | Omit for 1.0 | ZIP covers portable downloads; additional targets need their own builds and validation |
| SHA-256 manifests | Ship | Detect corrupt/incorrect downloads; not a code signature |

The Linux executable handles dashboard, tray and terminal commands itself. Windows keeps `recharge-ai-task.exe` (windowed tray) and `recharge-ai-task-cli.exe` (console). The tray launches its console companion for interactive actions. PyInstaller's windowed build has no standard streams; a single Windows EXE would need a tested console attachment/hiding design. See [PyInstaller's standard-stream limitations](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html#sys-stdin-sys-stdout-and-sys-stderr-in-noconsole-windowed-applications-windows-only).

AppImage must be built against a compatible oldest target system; see its [build guidance](https://docs.appimage.org/reference/best-practices.html). Flatpak restricts host access; see its [sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html). AppImage packaging and update requirements are now specified in the [AppImage release contract](doc/requirements/2026-11-17_appimage-release.md). Flatpak remains excluded.

For AppImage, publish the `.AppImage`, `.AppImage.zsync` and `SHA256SUMS-appimage.txt` together; [embedded update information, tool pins, manager recommendations and publication checks](doc/requirements/2026-11-17_appimage-release.md) are mandatory parts of that release.

## Where Windows downloads are created

Every push to `master`, version-tag push and manual **Release** workflow run builds Linux and Windows together after CI passes. Open **Actions → Release → a successful run → Artifacts** for `linux-x86_64` and `windows-x86_64`. The latter contains `recharge-ai-task-1.0-windows-x86_64.zip` and `SHA256SUMS-windows.txt`. Workflow downloads wrap these files in an outer artifact ZIP; extract that first. Branch builds upload artifacts only; version tags also create a draft release containing both platforms. Published downloads appear on [GitHub Releases](https://github.com/mikkovedru/recharge-ai-task/releases) after the draft is reviewed and published.

On 2026-11-17, GitHub's release list and Release workflow history were both empty. The local checkout already had a Windows job, but local Linux builds do not run that job or produce Windows EXEs. This explains the missing remote downloads without establishing any Windows build failure. Creating native Windows executables requires a Windows runner; running the packager on Linux with placeholder EXEs cannot verify a Windows build.

The portable ZIP includes both Windows executables (the main EXE is the tray), README, this release guide, source/contribution/license information, target-selection help and the [Windows portable guide](docs/2026-11-17_windows-portable.md). Shipped Markdown links stay local; links to deeper source documents point to the version tag. The package includes the current README screenshot as a tracked source asset. The 2026-11-17 README update removed the previous screenshot while the packager still required it, so fresh builds failed before creating either platform’s ZIP; the packager now uses the replacement image. The workflow checks required ZIP entries, runs extracted CLI version/help/wrapper/quota commands, verifies checksums and waits for both builds before creating the tag's draft. Native tray, autostart and provider delivery still require Windows-session verification.

## GitHub setup and first release

1. In the repository's **Settings → Actions → General**, enable GitHub Actions and allow the actions used by the workflows (`actions/*` and `softprops/action-gh-release`). Organization policies can override this. The workflow grants only its final draft-release job `contents: write`. GitHub supplies `GITHUB_TOKEN`; no personal token or signing secret is needed. See [GitHub token permissions](https://docs.github.com/en/actions/tutorials/authenticate-with-github_token).
2. Push the reviewed commits to `origin/master` when ready. CI tests Python 3.10 and 3.12 on Linux and Windows, plus Linux GTK/X11 and native Wayland tests. The Release workflow also builds both platforms automatically on this push.
3. In **Actions → Release → Run workflow**, choose `master`. This runs the same checks and both platform builds, then uploads downloadable workflow artifacts. A branch run creates no release. Download them and complete the manual tests below.
4. Once checks and manual tests pass, create and push the matching tag:

   ```bash
   git tag -a v1.0 -m "Recharge AI-task 1.0"
   git push origin master
   git push origin v1.0
   ```

5. The tag build validates versions, reruns CI, builds on Ubuntu 24.04 and Windows Server 2022, verifies archives/checksums and creates a **draft** under **Releases** with the artifacts and [1.0 notes](docs/2026-11-09_release-notes-1.0.md).
6. Download and check the draft’s assets, including the Windows ZIP. Windows is approved for the release plan; record native verification results without claiming tests that have not been run. Then select **Publish release**. Nothing is automatically published.

No push, tag or remote release is performed by local build scripts. This task prepares the process; a successful GitHub run and real Windows session remain verification steps. Future versions must update both version declarations, the notes and the workflow's `body_path` before tagging. The tag must exactly match the version prefixed by `v` (for example 1.0.1 → v1.0.1).

## Build locally

For shared-checkout builds, artifact provenance checks and the unresolved historical extraction failure, see [build verification and shared-checkout lessons](doc/investigations/2026-11-11_build-verification-and-shared-checkouts.md).

Linux x86_64, Debian / Ubuntu / Mint with glibc 2.39+ (Ubuntu 24.04 / Mint 22 baseline):

```bash
sudo apt install python3-venv python3-gi python3-cairo python3-gi-cairo \
  gir1.2-gtk-3.0 gir1.2-xapp-1.0 gir1.2-atspi-2.0 \
  gir1.2-ayatanaappindicator3-0.1 dpkg-dev
/usr/bin/python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install -e ".[tray,dev]"
PYTHON=.venv/bin/python bash scripts/build_linux.sh
PYTHON=.venv/bin/python bash scripts/package_release.sh
.venv/bin/python scripts/build_appimage.py
```

Windows x86_64, from PowerShell in the source checkout:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[windows,tray,dev]"
.\scripts\build_windows.ps1
.\scripts\package_release.ps1
```

Build on the target OS; PyInstaller does not cross-compile. Windows EXEs include file/product version resources and icons, but are unsigned. Signing and a Windows installer can be added after native validation; unsigned downloads may trigger Windows reputation warnings.

Built executables go in `dist/`; uploadable packages go in `dist/release/`. Packaging uses an explicit input list, excluding unrelated files and previous builds. Build scripts remove only obsolete generated launchers.
## Verify before publishing

The GUI was tested on Linux Mint 22.3 “Zena” Cinnamon, the [latest stable Linux Mint release](https://linuxmint.com/download.php) as of 2026-11-10. This is the confirmed test environment; Debian and Ubuntu GUI sessions remain separate verification targets.

- On a compatible Debian / Ubuntu / Mint machine, launch the extracted ZIP, raw executable and installed `.deb`. Check `--version`, `--help`, `run --help`, `quota`, tray startup, dashboard open/close/reopen, terminal launch and autostart. Check package install/removal with apt; package removal leaves personal settings.
- Test selecting targets, resizing the dashboard, editing messages, and monitoring start/stop. Verify a real provider recovery without duplicate sends. Check X11 and Wayland separately, including the documented native Goal limits.
- On Windows 10/11 x86_64, launch the tray, configuration, quota, a real pywinpty wrapped provider, target selection and desktop delivery, start/stop and autostart. CLI unit tests use a fake PTY and do not establish these native behaviors.
- Verify downloaded checksums with `sha256sum -c SHA256SUMS-linux.txt` on Linux or `Get-FileHash` on Windows. GitHub workflow artifacts wrap release files in another ZIP; use the inner release packages for these checks.

The `.deb` is a direct-download package, not an apt repository with automatic updates. Portable menu/autostart registrations refer to the executable's location; refresh them after moving the file. AppImage retains the same tested Linux baseline; Flatpak, macOS and ARM remain unsupported. Record failed native checks before publishing; do not treat a build or mocked test suite as proof of end-to-end provider compatibility.

## Package name, descriptions, logo and repository

For the incorrect assumptions, root causes and verification gaps discovered during packaging, see [Debian packaging and installer lessons](doc/investigations/2026-11-11_debian-packaging-and-installer-behavior.md).

Edit [packaging/linux/metadata.json](packaging/linux/metadata.json), then run `PYTHON=.venv/bin/python bash scripts/package_release.sh` to regenerate the `.deb`. `summary` is the short description; `description` is a list of long-description paragraphs. `repository_description` adds a final Debian long-description paragraph with the GitHub repository URL so installers that omit `Homepage` can still show it. AppStream uses its dedicated homepage/source/bugtracker links because its description format rejects plain URLs. OpenCode is described as a wrapped interactive terminal integration, with its quota and target limitations. `name` is the human display name; keep `package` unchanged because it identifies the installed package and removal command.

Desktop launcher content is generated by [recharge_ai_task/desktop_entry.py](recharge_ai_task/desktop_entry.py). Edit `COMMENT` for the concise tooltip, `GENERIC_NAME` for the generic application label, and `KEYWORDS` for menu search terms (also used by AppStream). Both launchers expose the GitHub action; only the package-owned launcher exposes package removal. [recharge_ai_task/desktop_integration.py](recharge_ai_task/desktop_integration.py) writes portable launchers to `$XDG_DATA_HOME/applications/recharge-ai-task.desktop` (normally `~/.local/share/applications/`); [scripts/package_release.py](scripts/package_release.py) writes the system launcher and descriptions into the `.deb`. The desktop `Comment` is a short tooltip; the package and AppStream long descriptions are separate metadata.

The packager also calculates `Installed-Size` from the unpacked payload in KiB so Captain can display installed disk usage; the compressed download size is the `.deb` file’s size. It uses this metadata for `DEBIAN/control`, the package-owned desktop launcher and AppStream information. `Homepage` and AppStream homepage/source/bugtracker URLs point to GitHub. The package installs the Recharge icon and includes its repository URL with the copyright/license information. Supporting software managers can display the AppStream name, description, icon and links.

Mint’s Captain 1.1.2 reads the window title from the control `Package` field, the subtitle from `Version`, and its description from `Description`. It applies Python `summary.title()` to the summary, so both occurrences of `AI` appear as `Ai` even though `DEBIAN/control` preserves the exact uppercase text. Its installer does not read the package’s icon or Homepage for that window and implements reinstall without a Remove action. These installer controls cannot be changed through `.deb` metadata. Recharge therefore provides its own branded removal dialog through `recharge-ai-task --uninstall` and a desktop action. It opens the system apt removal command in a terminal so authentication, package changes and confirmation stay with the package manager; settings and logs are retained.

Installed builds use `/usr/share/applications/recharge-ai-task.desktop`, which dpkg owns. They must not create a user launcher with the same desktop ID: Cinnamon can mistake that unowned override for an app with no package. During Debian package configuration, `packaging/linux/postinst` runs launcher migration as each regular local account that has a default-location portable launcher. This happens before the first app launch, so installing and immediately choosing Cinnamon’s Uninstall uses the package-owned file. The helper drops privileges with `runuser` (from the `util-linux` dependency), retires only exact app-generated shadows, and preserves customized launchers. Installed builds also perform this check on launch, including a session’s custom `XDG_DATA_HOME`. Package configuration cannot discover arbitrary per-session XDG paths; those are repaired on launch or with `recharge-ai-task --install-desktop`. Portable builds keep their per-user integration.

The owner confirmed that `.deb` installation and use work and Synaptic removes the installed package. This does not establish Windows behavior or certify every distro/installer. The install-time migration and removal dialog are covered by regression tests. Installing the rebuilt package on the owner’s Mint 22.3 system retired the existing generated override. Cinnamon’s live application lookup then selected the dpkg-owned system launcher, and its native removal helper identified `recharge-ai-task` and opened the normal package-removal confirmation; that verification canceled before removal.

## Release-note image and documentation links

The source [1.0 notes](docs/2026-11-09_release-notes-1.0.md) use a relative logo path and relative documentation links, so they work in the repository and local previews without requiring a published tag. A GitHub Release body is a separate document context. Before creating the draft, the workflow runs `scripts/render_release_notes.py` to turn local image links into raw-content URLs and documentation links into GitHub file URLs using `GITHUB_SHA`. The pushed release commit already exists at that point, and later branch changes cannot redirect those links. The generated body stays under `build/`; the source Markdown remains relative.
