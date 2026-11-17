"""Keep relaunches and registrations on the persistent AppImage, not its mount."""
import os
from pathlib import Path
import sys


def appimage_path():
    value = os.environ.get("APPIMAGE")
    if sys.platform != "linux" or not getattr(sys, "frozen", False) or not value:
        return None
    path = Path(value).expanduser().absolute()
    return path if path.is_file() else None
