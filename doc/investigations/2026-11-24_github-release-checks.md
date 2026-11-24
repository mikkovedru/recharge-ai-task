# GitHub release checks for the v1.1 tag

The uploaded `2026-11-24_logs_123032114782.zip` shows the release prerequisite checks at `v1.1` (`b183afb51985a7924fca319ec30aae76c78b348e`). The Linux and Windows jobs on Python 3.10 and 3.12 failed during tests, as did the GTK/X11 job. The X11 failure prevented the following Wayland step from running, and the release build jobs depend on the checks.

The GTK logo test hard-coded `1.0`. The dashboard tooltip already used the runtime version, `1.1` in the failing run. The test now checks the full version line against the running package and still exercises focus, opening the repository and copying its URL. The GI version warnings in the log came from the test subprocess importing GTK bindings without selecting GTK 3 first. See the [logo test](../../tests/test_brand_ui.py).

The README had a relative link to a screenshot that existed in the local checkout but was absent from the tag. The portable packager also listed the screenshot under a different, missing filename. It writes the portable ZIP before creating the Debian package, so the ZIP error also stopped the Debian test. Keep the screenshot in Git and use the README’s exact case-sensitive path for its archive entry. See the [task-status screenshot](../../docs/assets/2026-11-23_Screenshot_Task-status-example.png) and [portable packager](../../scripts/package_release.py).

The release tests check that local Markdown targets resolve within both portable ZIPs. The repository image test checks that referenced images exist in the source tree. Run these checks from a Git-derived snapshot when verifying release assets, because untracked files in a developer checkout can hide missing source assets. See the [release tests](../../tests/test_release.py) and [repository image test](../../tests/test_release_notes.py).

## Local X11 verification limit

The focused release checks passed under Openbox. The full local X11 run had one separate failure in `test_pointer_double_click_multiselect_trash_and_narrow_window`. The same test reached 1000×762 after requesting 1000×760 on both the repaired source and the original tag under Openbox. The repaired source also reproduced it under Metacity and with Adwaita forced under Openbox. The supplied GitHub X11 log did not report this test failing. The minimum-height cause remains unknown. See the [known narrow-window verification limit](../architecture/2026-11-14_dashboard-information-and-controls.md#known-narrow-window-verification-limit).
