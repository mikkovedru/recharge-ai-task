"""Public entry point; terminal commands do not initialize the desktop runtime."""
from __future__ import annotations

import sys

from . import __version__

COMMANDS = frozenset({"run", "watch", "quota", "configure", "targets", "help"})


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(f"Recharge AI-task {__version__}")
        return 0
    if args and args[0] in COMMANDS | {"--help", "-h"}:
        from .cli import main as cli_main
        return cli_main(args)
    # Keep explicit desktop options, tray mode and the isolated Goal helper.
    from .gui import main as gui_main
    return gui_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
