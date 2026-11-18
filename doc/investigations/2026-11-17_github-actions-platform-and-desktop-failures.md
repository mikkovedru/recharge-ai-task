# GitHub Actions platform and desktop failures

## Evidence and scope

The owner supplied the `2026-11-17_logs_119452756828.zip` workflow archive. Linux unit jobs on Python 3.10 and 3.12 each reported one failure; Windows 3.12 reported 26 failures and five setup errors, and Windows 3.10 reported 35 failures and five setup errors. The Ubuntu GTK/X11 job reported seven failures, preventing its following Wayland step and the dependent release builds from running. These were failures in the release workflow’s prerequisite checks, not evidence of a Windows executable build failure.

Logs were treated as diagnostic data. No source push, tag, remote workflow rerun or publication is part of the local repair. Native Windows verification still requires the GitHub matrix; a Linux ZIP fixture cannot establish Windows behavior.

## Platform and encoding findings

| Failure family | Confirmed observation and repair |
| --- | --- |
| Headless Linux Goal dispatch | The dispatch test imported the real GTK helper before replacing its entry point. Stub the helper module before dispatch, preserving the assertion that no tray starts. Pure unit jobs do not need GTK. |
| Windows Linux-launcher setup and execution | The desktop-integration module intentionally tests Linux menu files, Debian migration and POSIX filenames containing quotes/backslashes. Mark the module Linux-only, including fixture setup. Windows desktop behavior remains covered elsewhere. |
| Windows live Codex status | The fixture exercises Linux Unix-desktop discovery. Gate that test by the production platform, rather than expecting Linux IPC discovery on Windows. |
| ZIP permission bits on Windows | Windows filesystem modes do not implement the POSIX executable bits used by the Linux archive assertion. Keep allowlist, content and checksum checks on both hosts; assert POSIX permissions on POSIX hosts. |
| Unicode settings assertion | Settings already load and save UTF-8 explicitly. The failing test read the UTF-8 result with the Windows default code page. Read it explicitly as UTF-8; no settings migration change was needed. |
| Release notes and Markdown | The renderer and tests relied on the default text encoding. Specify UTF-8 for release-note source, generated output and Markdown inspection. A regression requires an explicit encoding at the renderer’s source read. |
| Epoch-adjacent quota timestamps | Naive `fromtimestamp(...).astimezone()` failed on the Windows runner for synthetic epoch timestamps. Convert from an aware UTC timestamp before localizing. A regression models the Windows failure of the naive conversion and checks freshness and quota-reset formatting. |
| Windows 3.10 provider acceptance subprocesses | Fixtures supplied an empty environment to Python subprocesses; the failures occurred in Windows process creation. Inherit the environment, matching production’s retention of system variables. This addresses the observed portability risk, but the Windows 3.10 rerun remains necessary to confirm elimination of WinError 87. Accepted-output tests also allow two seconds for process startup instead of 100ms; uncertain-delivery tests retain their short timeout. |
| Terminal observation integration | The fixture tried executing an extensionless shebang script on Windows. Run a `.py` fixture through `sys.executable` using the wrapper’s normal provider arguments, retaining real PTY observation/recovery coverage on Windows. |

The production timestamp and release-renderer fixes are independent of the test-environment corrections. Do not mask Windows encoding failures by merely forcing UTF-8 mode in CI, and do not skip real Windows provider/PTY coverage to make the matrix green.

## Native Linux environment and assertions

| Original failing test | Finding and repair |
| --- | --- |
| `test_real_cinnamon_icon` and `test_double_click_toggles_shared_dashboard_and_close_keeps_tray` | These require the real Cinnamon panel, while GitHub starts Openbox under Xvfb. Use the dedicated `RECHARGE_AI_TASK_CINNAMON_TESTS=1` opt-in for those two checks. A generic GUI-test flag must not imply a Cinnamon session. |
| `test_editor_drag_wrapping_and_log_layout` | Its FlowBox assertion expected Send now as a direct child, but the transfer-arrow/Send-now group is now the child. Check that grouping plus the reset controls and existing layout behavior. |
| `test_all_workspace_dividers_share_rendered_native_style` | Ubuntu does not ship Mint-X. Selecting a missing theme silently renders a fallback, which cannot satisfy Mint’s dot-texture assertion. Check installed themes before Mint variants and its missing-grip negative control; retain Adwaita comparisons on every Ubuntu run. Local Mint verification remains separate. |
| `test_theme_text_passive_rows_and_disclosure_contrast` | The test demanded exactly two caption lines despite supported responsive wrapping. Allow additional wrapped lines while retaining the exact caption, contrast and layout checks. Rendered crops confirmed readable two-line and three-line captions. An attempted extra geometry assertion double-counted GTK label placement; it and the proposed sizing change were discarded. |
| `test_real_accessibility_protocol_against_synthetic_gtk_application` | The runner lacked the `org.a11y.Bus` service. Install `at-spi2-core`, not just its GI typelib. Include `notification-daemon` for notification service support. Validate accessibility through the real synthetic GTK protocol test. |
| `test_activity_column_default_sort_refresh_and_saved_override` | The expected timestamp predated the deliberate comma between date and time. Update the display expectation while retaining numeric sorting, refresh and saved-override assertions. |

The existing [dashboard control contract](../architecture/2026-11-14_dashboard-information-and-controls.md) and [shared divider contract](../architecture/2026-11-14_shared-pane-dividers.md) describe the intended UI. The test repairs preserve those behaviors rather than changing the interface to match stale expectations.

## Reproduction and remaining limits

A temporary Ubuntu 24.04 container uses the workflow’s dependency list, a system-site-packages Python 3.12 environment, `dbus-run-session`, Xvfb at 1920×1200 and Openbox. Native checks use the tests’ isolated configuration fixture; they must not run against the real user profile. Build the test source snapshot from the current tracked files, including intended uncommitted repairs. A Git archive of HEAD alone would omit those repairs. Keep the snapshot unchanged during a complete verification run.

The final clean Ubuntu run passed 1,053 GTK/X11 tests with 14 skipped, followed by 23 passing Wayland checks. Eleven Goal-helper tests also passed in a fresh process with GTK imports deliberately blocked. Local focused batches passed 96 portable checks and 17 timestamp/release-note checks. The local theme checks passed the Mint-X grip/negative-control and readability tests, exercising the theme absent from Ubuntu.

A separate host-desktop overview resize/persistence check failed twice because a requested 1120×820 window retained its 1440×980 allocation. That same check passed in both isolated Ubuntu runs. The cause on the host was not established; do not describe this as a diagnosed window-manager or application bug. This does not negate the isolated CI pass, but host behavior remains an explicit verification limit. The existing [window-size findings](../architecture/2026-11-14_dashboard-information-and-controls.md#known-narrow-window-verification-limit) concern a different 1000×760 minimum-height observation.

The Linux executable, portable ZIP, Debian package and AppImage/zsync pair were rebuilt. Both SHA-256 manifests passed; the raw executable and extraction-and-run AppImage returned the expected version.

Windows 3.10/3.12 runtime tests, native Windows packaging and a successful remote release workflow remain unverified locally. Do not describe a source fix, a Linux run or a mock as a successful Windows release. Push authorization and the resulting GitHub run are separate steps.

## Follow-up

The [2026-11-18 Windows terminal-recovery investigation](2026-11-18_windows-terminal-recovery-blocking-reads.md) covers the next workflow logs. The prior Windows failures above are absent; only three real PTY recovery tests remain failing on each Windows version. That follow-up documents the blocking-read adapter mismatch and the subsequent repair.
