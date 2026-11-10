"""Public dispatch and release archives must work without companion Linux apps."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest
from recharge_ai_task import app, cli, gui, __version__


@pytest.mark.parametrize("args", [["run", "--goal"], ["quota"], ["watch"], ["targets", "--json"], ["configure"], ["--help"]])
def test_terminal_dispatch_never_initializes_gui(monkeypatch, args):
    monkeypatch.setattr(gui, "main", lambda _: pytest.fail("Loaded GUI"))
    monkeypatch.setattr(cli, "main", lambda actual: 7 if actual == args else 8)
    assert app.main(args) == 7


@pytest.mark.parametrize("args", [[], ["--tray"], ["gui"], ["tray"], ["--autostart"], ["--install-desktop"], ["--resume-goal-ui"]])
def test_desktop_dispatch_preserves_helper_and_startup(monkeypatch, args):
    monkeypatch.setattr(gui, "main", lambda actual: 7 if actual == args else 8)
    assert app.main(args) == 7


@pytest.mark.parametrize("module", ["recharge_ai_task", "recharge_ai_task.app"])
def test_public_version_without_display(module):
    result = subprocess.run([sys.executable, "-m", module, "--version"], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout.strip() == f"Recharge AI-task {__version__}"


@pytest.mark.parametrize("platform,names", [("linux", ["recharge-ai-task"]), ("windows", ["recharge-ai-task.exe", "recharge-ai-task-cli.exe"])])
def test_package_allowlist_permissions_and_checksums(tmp_path, platform, names):
    spec = importlib.util.spec_from_file_location("packaging_script", Path(__file__).resolve().parents[1] / "scripts/package_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in names:
        path = tmp_path / name
        path.write_bytes(b"test executable")
        path.chmod(0o755)
    (tmp_path / "private-settings.json").write_text("must not ship")
    outputs = module.package(platform, tmp_path, deb=False)
    with zipfile.ZipFile(outputs[0]) as z:
        assert set(z.namelist()) == {*names, "LICENSE", "README.md", "docs/assets/2026-11-09_Screenshot_Recharge-AI-task_Main-screen.png"}
        readme = z.read("README.md").decode()
        assert "](RELEASE.md)" not in readme
        assert f"/blob/v{__version__}/RELEASE.md" in readme
        assert z.read("docs/assets/2026-11-09_Screenshot_Recharge-AI-task_Main-screen.png") == (Path(__file__).resolve().parents[1] / "docs/assets/2026-11-09_Screenshot_Recharge-AI-task_Main-screen.png").read_bytes()
        assert z.getinfo(names[0]).external_attr >> 16 & 0o111
    for line in outputs[-1].read_text().splitlines():
        digest, name = line.split("  ")
        assert hashlib.sha256((outputs[-1].parent / name).read_bytes()).hexdigest() == digest


def test_deb_installs_safe_modes_and_one_executable(tmp_path):
    import io
    import shutil
    import tarfile
    if not shutil.which("dpkg-deb"):
        pytest.skip("Requires dpkg-deb")
    spec = importlib.util.spec_from_file_location("packaging_script", Path(__file__).resolve().parents[1] / "scripts/package_release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    (tmp_path / "recharge-ai-task").write_bytes(b"fixture")
    outputs = module.package("linux", tmp_path)
    deb = next(path for path in outputs if path.suffix == ".deb")
    control_dir = tmp_path / "control"
    subprocess.run(["dpkg-deb", "--control", str(deb), str(control_dir)], check=True)
    postinst = control_dir / "postinst"
    assert postinst.stat().st_mode & 0o111
    assert postinst.read_bytes() == (module.ROOT / "packaging/linux/postinst").read_bytes()
    assert "util-linux" in subprocess.check_output(["dpkg-deb", "--field", str(deb), "Depends"], text=True)
    data = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(deb)])
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            assert member.uid == member.gid == 0
            expected = 0o755 if member.isdir() or member.name == "./usr/bin/recharge-ai-task" else 0o644
            assert member.mode == expected, (member.name, oct(member.mode))
        assert [m.name for m in archive.getmembers() if m.name.startswith("./usr/bin/") and m.isfile()] == ["./usr/bin/recharge-ai-task"]
    assert subprocess.check_output(["dpkg-deb", "--field", str(deb), "Version"], text=True).strip() == __version__
    installed_size = int(subprocess.check_output(["dpkg-deb", "--field", str(deb), "Installed-Size"], text=True))
    assert installed_size > 0
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        payload_kib = sum((member.size + 1023) // 1024 for member in archive.getmembers() if member.isfile())
        assert installed_size >= payload_kib
    description = subprocess.check_output(["dpkg-deb", "--field", str(deb), "Description"], text=True)
    assert description.splitlines()[0] == "Continue selected AI tasks after AI provider token quota recovery"
    assert "OpenCode in wrapped interactive terminals" in description
    assert "OpenCode shared quota checks, dashboard chat recipients and Goal actions are unavailable." in description
    assert "\n .\n Project source, documentation and issues: https://github.com/mikkovedru/recharge-ai-task\n" in description
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        desktop = archive.extractfile("./usr/share/applications/recharge-ai-task.desktop").read().decode()
        assert "Exec=/usr/bin/recharge-ai-task\n" in desktop
        assert "Exec=/usr/bin/recharge-ai-task --uninstall\n" in desktop
        assert "Name=Project on GitHub" in desktop
        from recharge_ai_task.desktop_entry import COMMENT, GENERIC_NAME, KEYWORDS
        assert f"Comment={COMMENT}\n" in desktop
        assert f"GenericName={GENERIC_NAME}\n" in desktop
        assert f"Keywords={';'.join(KEYWORDS)};\n" in desktop
        assert "StartupWMClass=recharge-ai-task-tray\n" in desktop
        if shutil.which("desktop-file-validate"):
            launcher = tmp_path / "recharge-ai-task.desktop"
            launcher.write_text(desktop)
            subprocess.run(["desktop-file-validate", str(launcher)], check=True)
        import xml.etree.ElementTree as ET
        info = ET.fromstring(archive.extractfile("./usr/share/metainfo/io.github.mikkovedru.recharge_ai_task.metainfo.xml").read())
        assert info.findtext("name") == "Recharge AI-task"
        assert {keyword.text for keyword in info.findall("keywords/keyword")} == set(KEYWORDS)
        paragraphs = [paragraph.text for paragraph in info.findall("description/p")]
        assert "OpenCode in wrapped interactive terminals" in paragraphs[0]
        assert not any("https://" in paragraph for paragraph in paragraphs)
        assert info.find("url[@type='vcs-browser']").text == "https://github.com/mikkovedru/recharge-ai-task"
        assert info.findtext("icon") == "recharge-ai-task"
        assert info.find("url[@type='homepage']").text == "https://github.com/mikkovedru/recharge-ai-task"
        assert "https://github.com/mikkovedru/recharge-ai-task" in archive.extractfile("./usr/share/doc/recharge-ai-task/copyright").read().decode()



def test_release_tag_must_match_version():
    script = Path(__file__).resolve().parents[1] / "scripts/check_version.py"
    assert subprocess.run([sys.executable, str(script), "--tag", f"v{__version__}"], capture_output=True).returncode == 0
    assert subprocess.run([sys.executable, str(script), "--tag", "v99.99"], capture_output=True).returncode != 0


def test_windows_file_and_product_version_come_from_runtime(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/windows_version.py"
    output = tmp_path / "windows-version.txt"
    subprocess.run([sys.executable, str(script), str(output)], check=True)
    resource = output.read_text()
    assert f"StringStruct('FileVersion', '{__version__}')" in resource
    assert f"StringStruct('ProductVersion', '{__version__}')" in resource
    assert "filevers=(1, 0, 0, 0)" in resource
