# Debian release requirements and owner preferences

These requirements preserve the outcomes of the 2026-11-09–2026-11-14 release work. They complement the [installer investigation](../investigations/2026-11-11_debian-packaging-and-installer-behavior.md), [build investigation](../investigations/2026-11-11_build-verification-and-shared-checkouts.md) and [operational release guide](../../RELEASE.md). They describe acceptance criteria, while those documents retain causes, uncertainty and commands.

## Editable fields and accepted wording

Edit [packaging/linux/metadata.json](../../packaging/linux/metadata.json): `summary` is the Debian short description, `description` is the ordered list of long-description paragraphs, and `repository_description` is the final standalone repository paragraph. The accepted short wording is `Continue selected AI tasks after AI provider token quota recovery`; preserve its uppercase `AI` unless the owner requests a wording change. The repository paragraph must contain `https://github.com/mikkovedru/recharge-ai-task`. Updating `Homepage` alone does not satisfy that requirement.

Edit [desktop_entry.py](../../recharge_ai_task/desktop_entry.py) for the concise `COMMENT` and semicolon-separated desktop `KEYWORDS` shared by portable and package launchers; [package_release.py](../../scripts/package_release.py) serializes the Debian fields and AppStream metadata. Rebuild the `.deb` after changes and inspect the archive's actual values. Do not substitute Python package keywords for the desktop field.

## Description and discovery

- D1: Keep the short description concise, with deliberate `AI` capitalization. Explain purpose, interfaces, supported providers and important capability limits in readable long-description paragraphs. Do not claim uniform desktop/quota support across providers.
- D2: Include the GitHub repository in its own Debian long-description paragraph, even when `Homepage` is present. Do not promise that an installer makes plain text clickable. AppStream must use dedicated URL fields because its description validator rejects plain URLs.
- D3: Keep `.desktop` `Comment` a concise tooltip. Populate actual desktop `Keywords`, including supported provider names and useful quota/terminal terms; Python project keywords alone are insufficient. Portable and packaged launcher metadata must agree.
- D4: Use clear natural English, full sentences and sensible paragraph grouping. Keep each Markdown paragraph on one source line. Preserve capability qualifications instead of promotional claims that exceed tested behavior.

## Installation and removal

- I1: Installing and immediately selecting Cinnamon Uninstall, before opening Recharge, must resolve the dpkg-owned launcher. Retire only exact recognized generated overrides during package configuration, running migration as their owner. Preserve customized entries, actions and symlinks, including across metadata revisions.
- I2: Keep the explicit fallback for arbitrary per-session XDG locations: on-launch or `--install-desktop` migration. Do not claim that the installer can discover every custom location.
- I3: Provide the installed icon, AppStream artwork/links and branded Recharge removal dialog. Captain 1.1.2's absent logo/Homepage button, title-cased description and reinstall-only controls are external behavior; the owner chose Recharge-only changes, not modification of Captain.
- I4: Leave authentication and final package-removal confirmation to the package manager. Keep user settings/logs after removal. Verify which endpoint was actually exercised: opening a dialog, canceling it and completing removal are different results.

## Package and build integrity

- B1: Ship one Linux executable for dashboard, tray and commands, with explicit packaging inputs; do not sweep unrelated files from `dist/`. Preserve README images and usable deeper documentation links in downloads.
- B2: Generate `Installed-Size` from unpacked payload in KiB. Validate root ownership, directory/executable mode 0755 and ordinary-file mode 0644 in the actual archive, including executable maintainer scripts.
- B3: Validate actual desktop and AppStream metadata, Debian paragraphs, dependencies and maintainer-script behavior. Check repeat configuration and nonconfiguration phases.
- B4: Build from a recorded immutable source snapshot when a checkout/output directory is shared. Verify source identity, executable startup, binary identity across raw/ZIP/deb and checksums after delivery copies. Retain extraction-failure evidence before replacing a suspect file; the earlier decompression failure has no proven cause.
- B5: Test the owner's interaction sequence and visible installer/menu surface. Source tests, valid metadata and Synaptic removal do not prove Cinnamon removal or Captain rendering. Separate sandbox/display failures from application failures and report untested Windows, Wayland or authenticated-provider behavior explicitly.

## Maintenance

Keep requirements and investigations mutually linked. Update existing dated documents for closely related findings; create a newer dated document with mutual supersession links when behavior materially changes. Keep temporary ledgers and local AGENTS.md outside Git. Never silently delete unrelated artifacts or user documentation during packaging cleanup.
