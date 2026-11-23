"""Build the standalone x86_64 Flatpak from the versioned native Linux build."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recharge_ai_task import __version__
from recharge_ai_task.desktop_entry import desktop_entry
from recharge_ai_task.launch_path import FLATPAK_ID


RUNTIME = "org.freedesktop.Platform/x86_64/26.08"
SDK = "org.freedesktop.Sdk/x86_64/26.08"
RUNTIME_REPOSITORY = "https://dl.flathub.org/repo/flathub.flatpakrepo"
BRANCH = "stable"


def stage_application(directory, binary):
    metadata = json.loads((ROOT / "packaging/linux/metadata.json").read_text(encoding="utf-8"))
    files = directory / "files"

    def install(source, relative):
        path = files / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, path)
        return path

    install(ROOT / "packaging/flatpak/launch.sh", "bin/recharge-ai-task").chmod(0o755)
    install(binary, "libexec/recharge-ai-task").chmod(0o755)
    install(ROOT / "LICENSE", f"share/licenses/{FLATPAK_ID}/LICENSE")
    install(ROOT / "recharge_ai_task/assets/icon-256.png",
            f"share/icons/hicolor/256x256/apps/{FLATPAK_ID}.png")

    desktop = files / f"share/applications/{FLATPAK_ID}.desktop"
    desktop.parent.mkdir(parents=True)
    desktop.write_text(desktop_entry("recharge-ai-task", FLATPAK_ID, name=metadata["name"],
        comment="Continue selected AI tasks using local providers and desktop integration"), encoding="utf-8")

    component = ET.Element("component", type="desktop-application")
    for tag, text in (("id", FLATPAK_ID), ("metadata_license", "CC0-1.0"),
                      ("project_license", "MIT"), ("name", metadata["name"]),
                      ("summary", "Continue AI tasks after provider quotas reset")):
        ET.SubElement(component, tag).text = text
    developer = ET.SubElement(component, "developer", id="io.github.mikkovedru")
    ET.SubElement(developer, "name").text = "Recharge AI-task contributors"
    description = ET.SubElement(component, "description")
    for paragraph in metadata["description"]:
        ET.SubElement(description, "p").text = paragraph
    ET.SubElement(description, "p").text = (
        "This standalone distribution launches Recharge on the host as the current user "
        "to access installed providers and the desktop session."
    )
    for kind, key in (("homepage", "homepage"), ("bugtracker", "issues"), ("vcs-browser", "homepage")):
        ET.SubElement(component, "url", type=kind).text = metadata[key]
    categories = ET.SubElement(component, "categories")
    ET.SubElement(categories, "category").text = "Utility"
    ET.SubElement(component, "launchable", type="desktop-id").text = desktop.name
    ET.SubElement(component, "content_rating", type="oars-1.1")
    releases = ET.SubElement(component, "releases")
    ET.SubElement(releases, "release", version=__version__, date="2026-11-23")
    ET.indent(component)
    metainfo = files / f"share/metainfo/{FLATPAK_ID}.metainfo.xml"
    metainfo.parent.mkdir(parents=True)
    metainfo.write_text(ET.tostring(component, encoding="unicode") + "\n", encoding="utf-8")

    (directory / "metadata").write_text(
        f"[Application]\nname={FLATPAK_ID}\nruntime={RUNTIME}\nsdk={SDK}\n",
        encoding="utf-8",
    )
    return desktop, metainfo


def bundle(binary, output):
    binary = binary.resolve()
    version = subprocess.check_output([binary, "--version"], text=True).strip()
    if version != f"Recharge AI-task {__version__}":
        raise ValueError(f"Expected Linux executable version {__version__}, got {version!r}")

    output.mkdir(parents=True, exist_ok=True)
    filename = f"recharge-ai-task-{__version__}-x86_64.flatpak"
    with tempfile.TemporaryDirectory(prefix="recharge-flatpak-", dir=output) as temp:
        workspace = Path(temp)
        stage = workspace / "stage"
        repo = workspace / "repo"
        desktop, metainfo = stage_application(stage, binary)
        subprocess.run(["desktop-file-validate", desktop], check=True)
        subprocess.run(["appstreamcli", "validate", "--no-net", metainfo], check=True)
        subprocess.run(["flatpak", "build-finish", "--command=recharge-ai-task",
                        "--share=ipc", "--socket=wayland", "--socket=fallback-x11",
                        "--talk-name=org.freedesktop.Flatpak", "--talk-name=org.kde.StatusNotifierWatcher",
                        "--persist=.recharge-ai-task", stage], check=True)
        # The desktop file and metadata were validated above. The exporter
        # needs no namespace sandbox to check the bundled, tracked PNG.
        subprocess.run(["flatpak", "build-export", "--disable-sandbox", "--arch=x86_64",
                        repo, stage, BRANCH], check=True)
        temporary = workspace / filename
        subprocess.run(["flatpak", "build-bundle", f"--runtime-repo={RUNTIME_REPOSITORY}",
                        repo, temporary, FLATPAK_ID, BRANCH], check=True)
        path = output / filename
        temporary.replace(path)

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    (output / "SHA256SUMS-flatpak.txt").write_text(f"{digest.hexdigest()}  {filename}\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "dist/recharge-ai-task")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release")
    arguments = parser.parse_args()
    print(bundle(arguments.binary, arguments.output))
