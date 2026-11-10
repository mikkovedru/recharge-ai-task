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

## Where the knowledge belongs

Keep reproducible build commands and current release requirements in the release guide. Keep non-obvious investigation findings and unresolved causal limits in this document. Tests should enforce practical regressions, such as archive contents, relative source images and metadata correctness. Temporary ledgers can record task progress and test counts, but they must not be the sole surviving location of reusable technical knowledge.
