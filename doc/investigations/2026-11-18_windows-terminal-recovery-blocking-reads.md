# Windows terminal recovery and blocking reads

## Evidence

The owner’s `2026-11-18_logs_119870167447.zip` follows the [earlier platform/desktop CI investigation](2026-11-17_github-actions-platform-and-desktop-failures.md). Both Windows Python 3.10 and 3.12 jobs now pass 700 tests and fail only the three real terminal-observation tests for Gemini, Antigravity and OpenCode. The earlier encoding, timestamp, platform-fixture and process-creation failures are absent. Both Linux unit jobs and the native Linux job pass. The Windows release build remains blocked by these prerequisite checks.

The timeout occurs while collecting subprocess output. Captured output is not included in the failure, and the process representation’s exit code can reflect the test’s later forced cleanup; it does not independently establish an application crash.

## Confirmed backend mismatch

The [pywinpty 3.1.2 implementation used by these jobs](https://github.com/andfoy/pywinpty/blob/v3.1.2/winpty/ptyprocess.py#L167-L192) reads through a blocking socket and can wait for more bytes while assembling UTF-8 text. Recharge’s Unix backend polls at 100ms, while its Windows backend previously delegated directly to that blocking read.

Recovery waits repeatedly read terminal output before checking the reset deadline again. A provider that prints a limit banner and then waits silently for input can therefore block the Windows recovery loop indefinitely: the continuation that would produce new output is itself waiting for the read to return. This is a confirmed defect in the adapter contract and reproduces with a blocking process model. The supplied logs are consistent with it; native Windows rerun remains necessary to confirm that no additional ConPTY issue is hidden by the captured-output timeout.

## Repair and rationale

The Windows adapter now delegates the blocking API to a daemon reader and a bounded queue. Public reads return available text or an empty result after 100ms, allowing deadlines, cancellation and quota checks to run during silence. Buffered text retains order and requested read sizes; EOF and read failures remain visible after queued output has been consumed. The queue is bounded to avoid unlimited memory growth from a noisy provider.

A socket-readiness check alone would not bound the upstream UTF-8 assembly loop after a partial character. The adapter therefore uses the upstream Unicode reader in the background rather than adding a timeout that could discard its partially consumed bytes. Windows-only optional imports are deferred to their actual spawn/input paths, allowing platform-neutral contract tests to exercise the real adapter class on Linux. This does not establish real ConPTY behavior on Linux.

Terminal integration tests retain the real PTY/provider recovery checks. Output goes to diagnostic files instead of pipes, so an inherited handle held by a surviving provider cannot hide failure details inside `communicate()`. Timeouts include observed recovery states and both output logs. Windows timeout cleanup terminates the test process tree; normal recovery still requires the wrapper to exit successfully, publish waiting/continued states, write the expected continuation and remove its observation record.

## Verification and limits

Regressions exercise a genuinely blocking read model through `WinPtySession`: silent polling, reaching a reset deadline without further output, cancellation, Unicode text/order, partial-size reads, EOF persistence and error propagation. The silent-read assertion releases the model after a bounded wait, so restoring the original direct blocking read fails instead of hanging the test suite. Existing integration checks still run for all three terminal providers.

The full local suite passed 896 tests with 109 opt-in/platform checks skipped. Restoring the original direct-read behavior in an isolated test process makes the silent-read regression fail within its bounded assertion; the corrected backend passes. The Linux executable, portable ZIP, Debian package and AppImage/zsync pair were rebuilt. Both SHA-256 manifests and raw/AppImage version checks passed. Native Windows Python 3.10/3.12 execution and the remote workflow remain unverified until the new source is pushed and those jobs rerun. This repair changes runtime behavior rather than skipping the Windows tests or merely increasing their timeout.
