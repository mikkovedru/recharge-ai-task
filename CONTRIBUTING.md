# Contributing

<p align="center">
  <img src="docs/assets/logo-lockup.png" width="200" alt="Recharge AI-task logo">
</p>

Thank you for considering a contribution to Recharge AI-task.

## Development setup

```bash
git clone https://github.com/mikkovedru/recharge-ai-task.git recharge-ai-task
cd recharge-ai-task
git remote add upstream https://github.com/Autumnpoem/codex-autocontinue.git
git fetch upstream
git branch --track upstream-sync upstream/main
git config remote.pushDefault origin
# Linux GTK builds: install the native dependencies listed in RELEASE.md,
# then use /usr/bin/python3 -m venv --system-site-packages .venv.
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[all,dev]"
pytest tests/ -v
```

`origin` is the Recharge AI-task repository. `upstream` is the original Autumnpoem project, used to fetch upstream changes. `master` is the only primary branch in this repository; do not create a second `main` branch. Work on `master` and push to `origin`.

`upstream-sync` tracks the original repository’s `upstream/main`. Fetch and update `upstream-sync` before integrating upstream work into `master`. The original repository keeps its own branch naming; its `main` is not a development branch in this fork.

## Platform notes

| OS | Extra deps |
|----|------------|
| Windows | `pip install "recharge-ai-task[windows]"` (pywinpty) |
| Linux tray | `pip install "recharge-ai-task[tray]"` |
| Linux desktop mode | `sudo apt install xdotool` (X11 only) |

## Pull requests

1. Keep changes focused; match existing style.
2. Add or update tests for behavior changes.
3. Run `pytest tests/ -v` before submitting.
4. Update `README.md` if user-facing behavior changes.
5. For dashboard changes, follow the [information and control review gate](doc/architecture/2026-11-14_dashboard-information-and-controls.md), including actual-theme reference comparisons and information-retention checks.

## Release targets

Release candidates are built for **x86_64** only:

- Windows: `scripts/build_windows.ps1`
- Ubuntu: `scripts/build_linux.sh`

See [RELEASE.md](RELEASE.md) for the full checklist.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

## Documentation style

Write each Markdown prose paragraph or list item on one source line. Do not add hard line breaks at a fixed column width. Preserve code blocks, tables, nested lists and explicit formatting breaks where their structure requires separate lines. `.editorconfig` records that Markdown has no maximum line length.

Source, releases and issue tracking are available in the [GitHub repository](https://github.com/mikkovedru/recharge-ai-task).
