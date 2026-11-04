"""Combined dashboard and tray entry point."""
from __future__ import annotations

import sys

from .desktop_launch import _parser


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # Preserve the GUI/tray command forms from earlier releases.
    if args[:1] == ["gui"]:
        args = args[1:]
    elif args[:1] == ["tray"]:
        args = ["--tray", *args[1:]]
    # The native Goal helper uses the same packaged GTK runtime in its own
    # process, without opening a tray or dashboard or joining their controller.
    if args == ["--resume-goal-ui"]:
        from .desktop_goal_ui import main as goal_ui
        return goal_ui()
    parser = _parser()
    options = parser.parse_args(args)
    if sys.platform != "linux" and (options.targets or options.settings):
        parser.error("The graphical dashboard requires Linux GTK")
    if options.autostart and (options.targets or options.settings):
        parser.error("--autostart starts in the tray; it cannot open dashboard settings or targets")
    if options.install_desktop:
        if sys.platform != "linux":
            parser.error("--install-desktop requires Linux")
        if options.autostart:
            parser.error("--install-desktop cannot be combined with --autostart")
        from .desktop_integration import install_main
        return install_main()
    if sys.platform == "linux":
        from .desktop_integration import install_on_launch
        install_on_launch()
    tray_only = options.tray or options.autostart or sys.platform == "win32"
    tray_args = [] if tray_only else ["--settings" if options.settings else "--targets"]
    if options.autostart:
        tray_args.append("--autostart")
    from .tray import main as tray_main
    return tray_main(tray_args)


if __name__ == "__main__":
    raise SystemExit(main())
