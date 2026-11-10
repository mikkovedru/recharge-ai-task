"""Command-line entry for recharge-ai-task."""

from __future__ import annotations

from dataclasses import replace
import argparse
import sys
import json
import subprocess
from pathlib import Path

from .config import AppConfig, config_path, PROVIDERS
from .configure import run_configure
from .i18n import t
from .quota import discover_codex, fetch_quota, format_quota
from .watch import WatchConfig, run_desktop_watch
from .wrapper import WrapperConfig, run_wrapper

PROG = "recharge-ai-task-cli.exe" if sys.platform == "win32" else "recharge-ai-task"


def _build_run_parser(prog: str = PROG) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=t("cli.description"),
    )
    parser.add_argument("--codex", metavar="PATH", help="Path to codex executable")
    parser.add_argument("--provider", choices=PROVIDERS, help="AI provider (default from settings)")
    parser.add_argument("--claude", metavar="PATH", help="Path to Claude Code executable")
    parser.add_argument("--muse", metavar="PATH", help="Path to Meta Muse Code executable")
    parser.add_argument("--opencode", metavar="PATH", help="Path to OpenCode executable (interactive terminal)")
    goal = parser.add_mutually_exclusive_group()
    goal.add_argument("--goal", dest="goal_mode", action="store_true", help="CLI: first /goal resume; desktop: native recovery of quota-stopped goals")
    goal.add_argument("--no-goal", dest="goal_mode", action="store_false", help="Use the normal continue prompt")
    parser.set_defaults(goal_mode=None)
    parser.add_argument(
        "--continue",
        dest="continue_prompt",
        default=None,
        metavar="TEXT",
        help='Text to send after reset (default from config or "Continue")',
    )
    parser.add_argument("--grace", type=int, default=None, metavar="SECONDS")
    parser.add_argument("--enter-presses", type=int, default=1, metavar="N")
    parser.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to the selected AI CLI (prefix with -- if needed)",
    )
    return parser


def _normalize_codex_args(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _load_user_config() -> AppConfig:
    config = AppConfig.load()
    return config


def _cmd_quota(codex_path: str | None, provider="codex") -> int:
    try:
        if provider == "opencode":
            from .opencode import fetch_opencode_quota
            quota = fetch_opencode_quota()
        elif provider == "claude":
            from .claude import fetch_claude_quota
            quota = fetch_claude_quota()
        elif provider == "muse":
            from .muse import fetch_muse_quota
            quota = fetch_muse_quota(codex_path)
        else:
            quota = fetch_quota(discover_codex(codex_path))
    except Exception as exc:
        sys.stderr.write(f"{PROG}: {exc}\n")
        return 1
    print(format_quota(quota))
    return 0


def _cmd_configure(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"{PROG} configure")
    parser.add_argument("--mode", choices=["cli", "desktop"])
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--claude", dest="claude_path", metavar="PATH")
    parser.add_argument("--muse", dest="muse_path", metavar="PATH")
    parser.add_argument("--opencode", dest="opencode_path", metavar="PATH")
    parser.add_argument("--goal", action="store_true")
    parser.add_argument("--no-goal", action="store_true")
    parser.add_argument("--grace", type=int)
    parser.add_argument("--continue", dest="continue_prompt")
    ns = parser.parse_args(argv)

    overrides = {}
    if ns.provider:
        overrides["provider"] = ns.provider
    if ns.claude_path:
        overrides["claude_path"] = ns.claude_path
    if ns.muse_path:
        overrides["muse_path"] = ns.muse_path
    if ns.opencode_path:
        overrides["opencode_path"] = ns.opencode_path
    if ns.mode:
        overrides["mode"] = ns.mode
    if ns.goal:
        overrides["goal_mode"] = True
    if ns.no_goal:
        overrides["goal_mode"] = False
    if ns.grace is not None:
        overrides["grace_seconds"] = ns.grace
    if ns.continue_prompt:
        overrides["continue_prompt"] = ns.continue_prompt

    run_configure(non_interactive=overrides or None)
    return 0


def _cmd_watch(argv: list[str]) -> int:
    user = _load_user_config()
    parser = argparse.ArgumentParser(prog=f"{PROG} watch", description=t("help.desktop_mode"))
    parser.add_argument("--desktop", action="store_true", default=True)
    parser.add_argument("--codex", metavar="PATH")
    parser.add_argument("--provider", choices=("all", *PROVIDERS), default="all")
    goal = parser.add_mutually_exclusive_group()
    goal.add_argument("--goal", action="store_true", dest="goal", help="Verify native recovery of quota-stopped goals for Linux chat IDs")
    goal.add_argument("--no-goal", action="store_false", dest="goal", help="Send only the normal signal text; allows window targets")
    parser.set_defaults(goal=None)
    parser.add_argument("--grace", type=int, default=None)
    parser.add_argument("--continue", dest="continue_prompt", default=None)
    ns = parser.parse_args(argv)

    recipients = user.targets(None if ns.provider == "all" else ns.provider)
    if ns.goal is not None:
        recipients = [replace(target, send_goal=ns.goal and target.kind == "thread",
                              send_prompt=target.send_prompt if ns.goal else True) for target in recipients]
    config = WatchConfig(
        provider=ns.provider,
        codex_path=ns.codex or user.codex_path,
        muse_path=user.muse_path,
        continue_prompt=ns.continue_prompt or user.continue_prompt,
        goal_mode=user.goal_mode if ns.goal is None else ns.goal,
        grace_seconds=ns.grace if ns.grace is not None else user.grace_seconds,
        poll_seconds=user.poll_seconds,
        desktop_window_titles=user.window_titles(),
        desktop_targets=tuple(recipients),
    )
    return run_desktop_watch(config)


def _cmd_targets(argv):
    from .targets import discover_targets
    parser = argparse.ArgumentParser(prog=f"{PROG} targets", description="Discover installed AI chats and windows, and select signal recipients")
    parser.add_argument("--json", action="store_true", help="Print all metadata as JSON")
    parser.add_argument("--gui", action="store_true", help="Open the multi-target picker")
    parser.add_argument("--select", action="append", metavar="ID", help="Save this target (repeat for multiple targets)")
    parser.add_argument("--clear", action="store_true", help="Clear saved selection")
    parser.add_argument("--provider", choices=("all", *PROVIDERS), default="all")
    ns = parser.parse_args(argv)
    if ns.gui:
        config = _load_user_config()
        config.chat_provider_filter = ns.provider
        config.save()
        from .desktop_launch import launch
        return launch([])
    from .providers import discover_all_targets
    inventory = discover_all_targets() if ns.provider == "all" else discover_targets(ns.provider)
    config = _load_user_config()
    if ns.select is not None and ns.clear:
        parser.error("--select and --clear cannot be combined")
    if ns.select:
        selection = []
        for value in ns.select:
            matches = [t for t in inventory.targets if value in (t.id, t.key)]
            if len(matches) != 1:
                parser.error(f"Target {value!r} is unavailable or ambiguous; use its full key from --json")
            if matches[0].key not in {t.key for t in selection}:
                selection.append(matches[0])
        previous = {t.key: t for t in config.all_targets()}
        def choose(target):
            saved = previous.get(target.key)
            active = saved is not None and any(saved.signal_actions())
            return replace(target.with_preferences(saved), send_prompt=saved.send_prompt if active else True,
                           send_goal=saved.send_goal if active else False)
        chosen = [choose(t) for t in selection]
        keys = {t.key for t in chosen}
        inactive = [replace(t, send_prompt=False, send_goal=False) if ns.provider == "all" or t.provider == ns.provider else t
                    for key, t in previous.items() if key not in keys]
        config.desktop_targets = [t.to_dict() for t in chosen + inactive]
        config.mode = "desktop"
        config.save()
    elif ns.clear:
        config.desktop_targets = [(replace(t, send_prompt=False, send_goal=False) if ns.provider == "all" or t.provider == ns.provider else t).to_dict() for t in config.all_targets()]
        config.save()
    selected = {t.key: t for t in config.targets()}
    preferences = {t.key: t for t in config.all_targets()}
    if ns.json:
        print(json.dumps({"targets": [dict(t.with_preferences(preferences.get(t.key)).to_dict(), key=t.key, selected=t.key in selected,
                send_prompt=selected[t.key].send_prompt if t.key in selected else False,
                send_goal=selected[t.key].send_goal if t.key in selected else False) for t in inventory.targets], "warnings": inventory.warnings}, indent=2, ensure_ascii=False))
    else:
        for t in inventory.targets:
            print(f"{'[x]' if t.key in selected else '[ ]'} {t.provider:6} {t.kind:7} {t.title}\n    ID: {t.id}  PID: {t.pid or '—'}  Instance: {t.instance}\n    Task: {t.task_status}  Goal: {t.goal_status}\n    {t.deeplink or t.status}")
        for warning in inventory.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
    return 0


def _cmd_run(argv: list[str]) -> int:
    user = _load_user_config()
    parser = _build_run_parser(f"{PROG} run")
    ns = parser.parse_args(argv)

    config = WrapperConfig(
        provider=ns.provider or user.provider,
        claude_path=ns.claude or user.claude_path,
        claude_args=_normalize_codex_args(ns.codex_args) or user.claude_args,
        muse_path=ns.muse or user.muse_path,
        opencode_path=ns.opencode or user.opencode_path,
        opencode_args=_normalize_codex_args(ns.codex_args) or user.opencode_args,
        muse_args=_normalize_codex_args(ns.codex_args) or user.muse_args,
        codex_path=ns.codex or user.codex_path,
        codex_args=_normalize_codex_args(ns.codex_args) or user.codex_args,
        continue_prompt=ns.continue_prompt or user.continue_prompt,
        goal_mode=user.goal_mode if ns.goal_mode is None else ns.goal_mode,
        grace_seconds=ns.grace if ns.grace is not None else user.grace_seconds,
        enter_presses=ns.enter_presses,
        poll_seconds=user.poll_seconds,
    )
    try:
        return run_wrapper(config)
    except (FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"{PROG}: {exc}\n")
        return 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv == ["--version"]:
        from . import __version__
        print(f"Recharge AI-task {__version__}")
        return 0

    if argv and argv[0] in {"--help", "-h", "help"}:
        parser = _build_run_parser()
        parser.usage = "%(prog)s [COMMAND] [OPTIONS] [-- AI_ARGS...]"
        parser.formatter_class = argparse.RawDescriptionHelpFormatter
        parser.epilog = f"""Commands:
  --version        Show the application version
  gui              Open the graphical dashboard, targets and settings
  tray             Start directly in the system tray without a dashboard
  targets --gui    Open the same graphical dashboard
  targets --json   List chats from all installed providers as JSON
  run              Run Codex, Claude Code, Muse Code or OpenCode with auto-continue
  watch            Watch quota and signal saved desktop recipients
  quota            Show current quota and reset times
  configure        Configure command-line settings

Use {PROG} COMMAND --help for command options.
Run recharge-ai-task to open the dashboard directly.
Use recharge-ai-task --tray to start only the tray.
Use recharge-ai-task gui --help for desktop options (Linux).
Use recharge-ai-task --uninstall for Debian package removal (Linux)."""
        parser.print_help()
        return 0

    if argv and argv[0] in {"gui", "tray"}:
        from .desktop_launch import launch
        return launch(argv[1:], tray=argv[0] == "tray")

    if (
        not config_path().exists()
        and sys.stdin.isatty()
        and (not argv or argv[0] not in {"configure", "quota", "targets", "help", "-h", "--help"})
    ):
        run_configure()

    user = _load_user_config()

    if not argv:
        if user.mode == "desktop":
            return _cmd_watch([])
        return _cmd_run([])

    head = argv[0]
    tail = argv[1:]

    if head == "quota":
        parser = argparse.ArgumentParser(prog=f"{PROG} quota")
        parser.add_argument("--codex", metavar="PATH")
        parser.add_argument("--muse", metavar="PATH")
        parser.add_argument("--provider", choices=PROVIDERS, default=user.provider)
        ns = parser.parse_args(tail)
        path = ns.muse or user.muse_path if ns.provider == "muse" else ns.codex or user.codex_path
        return _cmd_quota(path, ns.provider)

    if head == "configure":
        return _cmd_configure(tail)

    if head == "targets":
        return _cmd_targets(tail)

    if head == "watch":
        return _cmd_watch(tail)

    if head == "run":
        return _cmd_run(tail)

    return _cmd_run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
