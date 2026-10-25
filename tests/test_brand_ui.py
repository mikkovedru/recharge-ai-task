import os
import subprocess
import sys
import pytest

@pytest.mark.skipif(os.environ.get("RECHARGE_AI_TASK_GUI_TESTS") != "1", reason="Requires GTK")
def test_logo_version_repository_and_copy_menu():
    result = subprocess.run([sys.executable, "-c", '''
from types import SimpleNamespace
from recharge_ai_task import __version__
from recharge_ai_task.brand_ui import ProjectLogo, Gtk, Gdk, REPOSITORY_URL
window = Gtk.Window()
logo = ProjectLogo(Gtk.Image())
window.add(logo)
assert __version__ in logo.get_tooltip_text()
calls = []
Gtk.show_uri_on_window = lambda *args: calls.append(args)
assert logo._press(logo, SimpleNamespace(button=1,time=42))
assert calls == [(window,REPOSITORY_URL,42)]
logo.menu.get_children()[0].activate()
assert Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text() == REPOSITORY_URL
assert not logo._press(logo, SimpleNamespace(button=2))
window.destroy()
'''], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
