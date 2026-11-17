# Source and distribution

[Recharge AI-task](https://github.com/mikkovedru/recharge-ai-task) is [MIT licensed](LICENSE), derived from [Autumnpoem/codex-autocontinue](https://github.com/Autumnpoem/codex-autocontinue). The source includes the multi-provider dashboard, tray, terminal wrapper, target discovery/delivery, artwork, English messages, tests and build workflows.

| Path | Purpose |
|---|---|
| `recharge_ai_task/` | Application, provider integrations, settings and assets |
| `scripts/` | Build, packaging and development tools |
| `tests/` | Unit, provider, GUI and display-session coverage |
| `.github/workflows/` | CI and draft release builds |
| `docs/`, `doc/` | User details, architecture and investigations |

End users download [release binaries](README.md#download-and-start). Source setup is in [CONTRIBUTING.md](CONTRIBUTING.md); packaging and publication are in [RELEASE.md](RELEASE.md). No PyPI publication is part of this release. Linux ships one executable; Windows retains a console companion for its tray.

Build outputs, local settings, agent notes, original input artwork and local instructions stay out of Git. Commit only converted assets used by the project. [UPLOAD_CHECKLIST.md](UPLOAD_CHECKLIST.md) describes the final source review.
