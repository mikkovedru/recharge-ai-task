# Build verification and shared checkouts

This investigation records reusable findings from the Linux 1.0 release preparation on 2026-11-09–2026-11-10. The environment was Linux Mint 22.3 Cinnamon, Python 3.12 and PyInstaller 6.22.3. It complements the [release and build guide](../../RELEASE.md); package formats, editable fields and publishing steps remain there. The [Debian packaging investigation](2026-11-11_debian-packaging-and-installer-behavior.md) preserves the installer misunderstandings, failed assumptions and reasons behind their corrections.

## Build from a known source tree

A shared checkout can change while a build runs. During release preparation, another task staged and committed OpenCode work while documentation and packaging were being verified. The checkout and its index therefore stopped representing the original release-only tree. A clean `git status` after someone commits is insufficient evidence that an already built executable came from that commit.

Use an immutable source snapshot when concurrent work cannot be paused. In this investigation, a Git archive of a recorded commit plus explicitly selected task changes provided the build input. Build and package inside that snapshot so its `build/` and `dist/` paths are not shared with another builder. This requires no branch or worktree. Archive only authorized source; include intended uncommitted files explicitly rather than silently treating `git archive HEAD` as the complete working tree.

Record the snapshot's base commit and exact additions. Before delivering its artifacts, compare the final intended source tree with the tested snapshot. Keep staged changes from other tasks separate from the task's changes. If history is rewritten, compare final tree content; a new commit hash alone does not require rebuilding identical source, and an unchanged filename does not prove that its executable is current.

## Verify the artifacts that will be delivered

Source tests, a successful PyInstaller invocation and a successful `--version` check establish different things. They do not collectively establish every packaged workflow. The release preparation found that ZIPs could contain a README whose screenshot and deeper documentation targets were absent from the archive, despite the source Markdown links being valid.

Check each delivery boundary: the built executable, the copied raw executable, the executable inside the ZIP and the executable extracted from the Debian package. Compare their bytes or hashes. Inspect the archive's explicit file list, its README image targets and documentation links. Generate checksums from the final upload files after packaging, then verify them again after copying those files to the delivery directory. Do not regenerate a checksum over an unexpected binary and treat that as verification of its provenance.

Exercise packaged entry points and the affected native interaction. Unit tests with mocked providers do not establish real provider authentication, quota recovery or Windows behavior. Likewise, reading Debian control metadata does not establish how a particular installer displays it. The [Debian packaging investigation](2026-11-11_debian-packaging-and-installer-behavior.md) explains why correct metadata and a valid installed package did not establish the expected installer display or menu-uninstall behavior. Preserve that reasoning alongside the [release guide](../../RELEASE.md#package-name-descriptions-logo-and-repository), which describes the current operational setup.

## Extraction failure: observation and limits

One shared-output build's immediate smoke check reported a PyInstaller extraction failure for `PIL/_imagingcms.cpython-312-x86_64-linux-gnu.so`, with “decompression resulted in return code 0”. A later inspection decompressed all 360 outer archive entries successfully, and five consecutive executable startups passed. An isolated source build, startup check, package extraction and checksum verification also passed.

The failure's root cause was not established. Concurrent work was present, but that does not prove that simultaneous writes caused the extraction failure. Successful retries and an isolated build do not prove that a persistent runtime defect is impossible. Do not document corruption, a race, disk exhaustion or a Pillow defect as a confirmed diagnosis without additional evidence.

If it recurs, retain the failing executable's hash and size, the source snapshot identity, tool versions and complete error before rebuilding or replacing the file. Verify the exact failing archive and its copied versions. Use separate build/output paths to remove shared-output ambiguity, then distinguish a reproducible build problem from a failure observed only in the original environment. Preserve the uncertainty until a cause is demonstrated.

## Native dependencies and sandbox failures

The Linux build uses system GTK/GObject bindings, including the foreign Cairo bridge, XApp, AT-SPI and Ayatana AppIndicator. A normal isolated Python virtualenv may not expose those distro packages. [build_linux.sh](../../scripts/build_linux.sh) checks the imports before freezing; use a system-site-packages environment as described in the release guide. The [PyInstaller spec](../../scripts/gui_linux.spec) includes the GI/Cairo hooks and excludes `pkg_resources`, whose setuptools dependency is unnecessary for Cairo's extension-build-only `get_include()` path. Preserve these constraints when changing build environments rather than treating a successful pure-Python test run as a native dependency check.

A sandboxed native test can fail because it cannot reach the X11 display or local IPC sockets. During the desktop metadata investigation, GTK initialization failed in the sandbox and the same focused tests passed with local display/IPC access. Diagnose the actual error and rerun only the required checks with that access; do not label an inaccessible display as an application regression or silently count the check as passed. A running desktop shared with other tasks can also make mouse-coordinate tests unreliable. Record the display conditions and test actual pointer/keyboard interaction when layout or focus is the acceptance criterion.

For pointer-sensitive GTK checks, a temporary nested Xephyr display can isolate test geometry from the active desktop. In the 2026-11-14 checks, the existing editor-drag test failed on the shared desktop but passed on a 1600×1100 Xephyr display with Metacity; the exact cause of the shared-desktop failures was not established. Minimize the Xephyr host window before driving its display with `xdotool` so host pointer movement does not enter it. Give the test window manager `GSETTINGS_BACKEND=memory` and isolated XDG config/data/cache directories. Run the tests with the nested `DISPLAY`, `RECHARGE_AI_TASK_GUI_TESTS=1` and `RECHARGE_AI_TASK_POINTER_TESTS=1`, then terminate both temporary processes. This preserves actual X11 mouse/keyboard interaction without changing the user's window-manager settings. Tests requesting a 1100-pixel window need a taller virtual screen to leave room for window decorations; 1600×1440 accommodated that resize check.

## Isolate application settings as well as the display

`config_dir()` defaults to `~/.recharge-ai-task`; it does not use `XDG_CONFIG_HOME`. Isolating XDG directories and running Xephyr therefore does not isolate Recharge settings. On 2026-11-15, a standalone reference helper reused the native test fixture outside pytest, bypassed the autouse settings fixture and overwrote the real configuration. The open dashboard retained targets, per-chat preferences and the original message, allowing recovery through its normal save path. Recovery of every earlier global or layout setting could not be established from that evidence.

Every standalone native helper must set `RECHARGE_AI_TASK_CONFIG_DIR` to a fresh temporary directory before constructing the fixture. The shared native fixture now rejects a missing override or either real default directory before importing GTK or saving anything; dedicated subprocess tests exercise those rejection paths. Normal pytest checks continue to receive their per-test directory from the autouse fixture. A separate display, a mocked control function and isolated XDG directories are insufficient substitutes for this application-specific override.

## Where the knowledge belongs

Keep reproducible build commands and current release requirements in the release guide. Keep non-obvious investigation findings and unresolved causal limits in this document. Tests should enforce practical regressions, such as archive contents, relative source images and metadata correctness. Temporary ledgers can record task progress and test counts, but they must not be the sole surviving location of reusable technical knowledge.
