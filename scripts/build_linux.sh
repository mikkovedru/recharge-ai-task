#!/usr/bin/env bash
# Build standalone Linux x86_64 executables.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import gi; gi.require_version("Gtk", "3.0"); gi.require_version("XApp", "1.0"); gi.require_version("Atspi", "2.0"); gi.require_foreign("cairo"); from gi.repository import Atspi, Gio' || { echo "Install python3-gi python3-cairo python3-gi-cairo gir1.2-gtk-3.0 gir1.2-xapp-1.0 gir1.2-atspi-2.0 and use a system-site-packages virtualenv." >&2; exit 1; }
"$PYTHON" -c 'import gi; gi.require_version("AyatanaAppIndicator3", "0.1"); from gi.repository import AyatanaAppIndicator3' || { echo "Install gir1.2-ayatanaappindicator3-0.1 for Wayland tray support." >&2; exit 1; }

arch="$(uname -m)"
if [[ "$arch" != "x86_64" ]]; then
  echo "Release builds target x86_64 Linux only (got: $arch)" >&2
  exit 1
fi

# Remove only obsolete generated launchers, preserving unrelated dist contents.
rm -f dist/install-desktop.sh dist/recharge-ai-task-cli dist/recharge-ai-task-gui dist/recharge-ai-task-tray

echo "Building recharge-ai-task (dashboard, tray and terminal commands)..."
PYSTRAY_BACKEND=dummy "$PYTHON" -m PyInstaller --noconfirm scripts/gui_linux.spec
"$ROOT/dist/recharge-ai-task" --version
"$ROOT/dist/recharge-ai-task" run --help >/dev/null

echo "Output: dist/recharge-ai-task"
echo "X11/XWayland window input also requires: sudo apt install xdotool"
echo "Wayland: enable native accessibility in AI apps and StatusNotifier/AppIndicator support in your panel."
