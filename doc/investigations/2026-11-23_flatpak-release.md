# Standalone Flatpak and Flathub

The standalone x86_64 package is built from the same version-checked native Linux executable as the ZIP, Debian package and AppImage. It packages the launcher, MIT license, desktop icon and AppStream metadata. The app ID is `io.github.mikkovedru.recharge_ai_task` and the runtime is Freedesktop 26.08. A single-file bundle contains the application and points Flatpak to its runtime repository. The runtime may need to be downloaded on first install. [Flatpak single-file bundles](https://docs.flatpak.org/en/latest/single-file-bundles.html)

The default launcher uses `flatpak-spawn --host` with the exact installed executable from Flatpak's runtime instance metadata. Recharge runs on the host as the signed-in user. Provider executables, process IDs, private chat sockets and desktop accessibility use the same environment as the native package. The package therefore requests `org.freedesktop.Flatpak` access. Flatpak owns the exported menu entry and login startup refers to the stable app ID across upgrades. Host mode shares native settings. Quit any running Recharge tray before testing an upgrade. [Flatpak instance metadata and host commands](https://docs.flatpak.org/en/latest/flatpak-command-reference.html)

The separate `--sandboxed` launcher option supports isolated version and interface checks. External provider and desktop integrations depend on native host mode. That mode keeps the existing glibc 2.39+ host requirement.

A Flathub submission requires a separate maintainer decision. Flathub prohibits AI-authored and AI-assisted manifests and prohibits agents from opening or automating submission pull requests or writing their review material. It also requires disclosure of AI-generated material and reviews host dependencies and expanded permissions. This standalone packaging was AI-assisted and is intended for direct distribution. A human maintainer would need to author the separate manifest, evaluate sandbox-compatible provider integration with reviewers, and submit through the human review process. [Flathub requirements](https://docs.flathub.org/docs/for-app-authors/requirements) · [Submission process](https://docs.flathub.org/docs/for-app-authors/submission)

## Local build check

The source-tree `recharge_ai_task.egg-info` from a previous build can shadow an updated virtual environment's installed metadata. During 1.1 preparation, the version check saw 1.0 from that checkout directory and 1.1 in the virtual environment. Moving the stale generated directory out of the checkout let the normal version check confirm 1.1.

## Verification

Flatpak 1.18.4 exported the bundle and installed it into a temporary user installation with the system Freedesktop 26.08 runtime. The default launcher reported 1.1, opened its dashboard and tray on nested X11, and queried quota from a simulated Codex executable located outside the sandbox. The sandboxed version check, host CLI help, exported menu metadata, and package-management guidance also passed. Account sign-in, live quota recovery, accessibility delivery on a Wayland desktop, and automatic startup at a real login were outside this test.

An isolated test bus initially inherited the real session's document-portal cache location and produced a mount warning. Starting that bus with temporary XDG cache and runtime directories allowed the document portal to start normally. The bundle does not require that test environment for routine installation.
