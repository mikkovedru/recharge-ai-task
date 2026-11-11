# Debian packaging and installer behavior: corrected assumptions

These findings come from the 1.0 packaging work on Linux Mint 22.3 Cinnamon, including Captain 1.1.2. This document preserves the incorrect assumptions, their consequences and the reasoning behind the corrections. The [release guide](../../RELEASE.md#package-name-descriptions-logo-and-repository) remains the source for current editable fields, commands and supported behavior. The [build-verification investigation](2026-11-11_build-verification-and-shared-checkouts.md) covers source snapshots and artifact identity.

## Correct metadata did not establish correct installer display

The initial verification checked that the package contained the requested description, Homepage, icon and AppStream information. That established the stored data, not what the owner would see when opening the `.deb`. Describing those additions as satisfying the visible installer request was an incorrect assurance.

Captain's installed `set_description` implementation calls `summary.title()`. It therefore renders both occurrences of `AI` as `Ai` even when the Debian `Description` field contains the exact uppercase text. Its package window also does not read the package icon or Homepage as application artwork and a website button. An AppStream validation pass cannot establish that Captain displays AppStream metadata. These findings are specific to the inspected installer/version, not universal Debian behavior.

The owner chose not to modify Captain. The correction is to preserve the exact package text, document Captain's transformation, and distinguish the installed launcher icon, AppStream presentation, Recharge's own removal dialog and Captain's window. A logo visible in one surface does not prove it is visible in another. Likewise, the downloaded `.deb` file's generic file-manager icon is a separate surface from the installed application's icon.

Ignoring `Homepage` does not prevent a repository URL from appearing as plain description text. The Debian long description now includes a separate repository paragraph. Do not promise that Captain turns it into a clickable button: its description is ordinary text. AppStream uses dedicated homepage/source/bugtracker URL elements; putting the same plain URL in its description was rejected by validation. Different consumers require different representations of the same information.

## A valid installed package did not establish a package-owned menu item

The owner could remove Recharge through Synaptic while Cinnamon reported that its menu item was not associated with a package. Treating successful package installation as proof that Cinnamon's Uninstall would work missed a separate identity lookup.

Mint's installed `mint-remove-application` runs `dpkg -S` on the selected desktop file. Recharge's portable integration had written a per-user `recharge-ai-task.desktop`, which could shadow `/usr/share/applications/recharge-ai-task.desktop`. The generated user file pointed to a portable build and had no dpkg owner. The package itself remained valid. The cause was the selected launcher's ownership, not missing package registration.

The installed app must prefer its package-owned launcher and retire only recognized app-generated shadows. Customized entries and symlinks must be preserved. See [desktop integration](../../recharge_ai_task/desktop_integration.py), the shared [desktop-entry generator](../../recharge_ai_task/desktop_entry.py) and their [regression tests](../../tests/test_desktop_integration.py).

## Repair on launch was too late for immediate uninstall

The first correction migrated the shadow when Recharge started. That did not satisfy the owner's sequence of installing the package and immediately selecting Cinnamon's Uninstall before the first launch. A working migration function alone did not establish the required timing.

The package now runs migration during its `configure` phase through [postinst](../../packaging/linux/postinst). It invokes the helper as each relevant regular account with `runuser`, rather than manipulating user-controlled files with root privileges. It clears the installer's `XDG_DATA_HOME` and supplies the account's home. Tests execute the actual maintainer script against generated, customized and symlink launchers, check repeat configuration and ensure unrelated maintainer-script phases do not migrate files.

Package configuration cannot discover every arbitrary per-session XDG location. Those paths retain on-launch or explicit `--install-desktop` repair. This limit must remain documented rather than claiming universal install-time cleanup.

## Desktop content and command quoting are separate contracts

The short desktop `Comment` is a tooltip, while the Debian long description and AppStream description are separate fields with different formatting rules. Python project keywords do not populate desktop `Keywords` automatically. Both launcher types now use the shared desktop-entry generator, and AppStream receives the same search terms; package paragraphs remain editable in the Linux metadata JSON. Keep the distinction visible in the [release guide](../../RELEASE.md#package-name-descriptions-logo-and-repository).

A portable executable path is serialized through both desktop string escaping and `Exec` argument quoting. Literal percent signs require desktop field-code escaping; dollar signs, backticks, double quotes and backslashes also need correct round trips. Shell quoting alone is insufficient. Shadow migration originally used `shlex` decoding that retained escapes before dollar signs and backticks, so an exact generated file with those path characters could fail recognition. The migration now corrects that decoding and re-encodes the expected command before comparison. Native GIO launcher tests exercise a path containing all these characters. Changing a generated comment or keyword list can otherwise make the previous generated launcher look customized. Keep exact prior metadata versions recognizable during migration; the managed marker alone is not sufficient authority to delete a file. Preserve exact-content checks for actions as well as the main entry: a user's edited website action makes the entry customized too.

## An external installer's controls are not package controls

Captain implements installation/reinstallation without a Remove action in its `.deb` window. Adding metadata cannot add that button. This should have been established before suggesting package-side display changes would satisfy that window's requirements.

The agreed Recharge-only alternative is a branded `--uninstall` dialog and desktop action. They hand off to the system package manager in a terminal, leaving password entry and removal confirmation there. They do not change Captain. Opening this dialog or launching a terminal does not prove that removal completed.

## Package size and permissions required explicit generation

The early package omitted `Installed-Size`, so Captain's size field was empty. Its value is unpacked payload size in KiB, not the compressed `.deb` download size. The [packager](../../scripts/package_release.py) now calculates it, and [package tests](../../tests/test_release.py) inspect the actual control field and payload.

An intermediate staging tree also carried `TemporaryDirectory`'s private root mode and the builder's directory permissions into the archive. A successful `dpkg-deb --build` did not validate the intended installation permissions. The packager now explicitly sets root ownership, directory modes, ordinary-file modes and executable modes, including the maintainer script. Regression checks inspect the packaged archive. The finding does not establish that the incorrect intermediate archive changed permissions on the owner's system.

## Verify the owner's sequence and record the actual endpoint

Metadata inspection, archive extraction, AppStream/desktop validation, installation, application discovery, removal confirmation and completed removal are distinct acceptance points. Check the requested visible surface and interaction sequence, including behavior before the first app launch. Do not present success at an earlier point as success at a later one.

After installation of the corrected package on the owner's Mint system, the generated override was absent, Cinnamon selected the dpkg-owned launcher and its native helper opened the expected removal confirmation for `recharge-ai-task`. That check canceled before removal. The owner separately reported successful removal through Synaptic. Neither observation is a completed native Cinnamon uninstall test.

The reusable lesson is to retain the failed inference and the correction, not merely the final configuration. Operational facts in a release guide do not replace the rationale needed to prevent the same misunderstanding on another package or installer.
