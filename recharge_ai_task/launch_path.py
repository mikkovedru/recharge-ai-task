"""Identify persistent launcher paths for installed Linux bundles."""
import os
from pathlib import Path
import sys


FLATPAK_ID = "io.github.mikkovedru.recharge_ai_task"


def flatpak_hosted():
    return sys.platform == "linux" and os.environ.get("RECHARGE_AI_TASK_FLATPAK_HOST") == "1"


def appimage_path():
    value = os.environ.get("APPIMAGE")
    if sys.platform != "linux" or not getattr(sys, "frozen", False) or not value:
        return None
    path = Path(value).expanduser().absolute()
    return path if path.is_file() else None
