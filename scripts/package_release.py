"""Package only explicit release inputs; never sweep a developer's dist folder."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile
from posixpath import dirname, join, normpath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recharge_ai_task import __version__
from recharge_ai_task.desktop_entry import KEYWORDS, desktop_entry


DOCUMENTS = ("README.md", "RELEASE.md", "OPEN_SOURCE.md", "CONTRIBUTING.md",
             "docs/target-selection.md", "docs/2026-11-17_windows-portable.md")
SCREENSHOT = "docs/assets/2026-11-17_Screenshot_Recharge-AI-task_Main-screen.png"


def archive_document(name, homepage):
    """Keep shipped documentation links local; send deeper links to the source tag."""
    content = (ROOT / name).read_text(encoding="utf-8")
    def documentation_link(match):
        label, target = match.groups()
        parsed = urlsplit(target)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return match.group(0)
        resolved = normpath(join(dirname(name), parsed.path))
        if resolved in (*DOCUMENTS, "LICENSE", SCREENSHOT):
            return match.group(0)
        suffix = ("?" + parsed.query if parsed.query else "") + ("#" + parsed.fragment if parsed.fragment else "")
        return f"[{label}]({homepage}/blob/v{__version__}/{resolved}{suffix})"
    return re.sub(r"(?<!!)\[([^\]]+)\]\(([^)]+)\)", documentation_link, content)


def package(platform, dist, *, deb=True):
    metadata = json.loads((ROOT / "packaging/linux/metadata.json").read_text())
    dist = Path(dist)
    output = dist / "release"
    output.mkdir(parents=True, exist_ok=True)
    names = ["recharge-ai-task"] if platform == "linux" else ["recharge-ai-task.exe", "recharge-ai-task-cli.exe"]
    inputs = [dist / name for name in names]
    for path in inputs:
        if not path.is_file():
            raise FileNotFoundError(f"Missing build: {path}")
    prefix = f"recharge-ai-task-{__version__}-{platform}-x86_64"
    outputs = []
    archive = output / f"{prefix}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as z:
        for path in inputs + [ROOT / "LICENSE"]:
            z.write(path, path.name)
        for name in DOCUMENTS:
            z.writestr(name, archive_document(name, metadata["homepage"]))
        z.write(ROOT / SCREENSHOT, SCREENSHOT)
    outputs.append(archive)
    if platform == "linux":
        raw = output / "recharge-ai-task"
        shutil.copy2(inputs[0], raw)
        raw.chmod(0o755)
        outputs.append(raw)
        if deb:
            with tempfile.TemporaryDirectory(prefix="recharge-deb-") as folder:
                tree = Path(folder)
                tree.chmod(0o755)
                binary = tree / "usr/bin/recharge-ai-task"
                binary.parent.mkdir(parents=True)
                shutil.copy2(raw, binary)
                control = tree / "DEBIAN/control"
                control.parent.mkdir()
                description = "\n .\n".join("\n".join(" " + line for line in paragraph.splitlines()) for paragraph in [*metadata["description"], metadata["repository_description"]])
                control.write_text(
                    f"Package: {metadata['package']}\nVersion: {__version__}\nArchitecture: amd64\n"
                    f"Maintainer: {metadata['maintainer']}\n"
                    "Section: utils\nPriority: optional\nDepends: libc6 (>= 2.39), libstdc++6, libgcc-s1, util-linux\n"
                    "Recommends: xdotool, x-terminal-emulator, sudo, xdg-utils\n"
                    f"Homepage: {metadata['homepage']}\n"
                    f"Description: {metadata['summary']}\n{description}\n")
                postinst = tree / "DEBIAN/postinst"
                shutil.copy2(ROOT / "packaging/linux/postinst", postinst)
                desktop = tree / "usr/share/applications/recharge-ai-task.desktop"
                desktop.parent.mkdir(parents=True)
                desktop.write_text(desktop_entry("/usr/bin/recharge-ai-task", "recharge-ai-task",
                                                 name=metadata["name"], homepage=metadata["homepage"], installed=True))
                metainfo = tree / "usr/share/metainfo/io.github.mikkovedru.recharge_ai_task.metainfo.xml"
                metainfo.parent.mkdir(parents=True)
                component = ET.Element("component", type="desktop-application")
                for tag, text in (("id", "io.github.mikkovedru.recharge_ai_task"), ("metadata_license", "CC0-1.0"),
                                  ("project_license", "MIT"), ("name", metadata["name"]), ("summary", metadata["summary"]),
                                  ("pkgname", metadata["package"])):
                    ET.SubElement(component, tag).text = text
                developer = ET.SubElement(component, "developer", id="io.github.mikkovedru")
                ET.SubElement(developer, "name").text = "Recharge AI-task contributors"
                categories = ET.SubElement(component, "categories")
                ET.SubElement(categories, "category").text = "Utility"
                keywords = ET.SubElement(component, "keywords")
                for keyword in KEYWORDS:
                    ET.SubElement(keywords, "keyword").text = keyword
                launchable = ET.SubElement(component, "launchable", type="desktop-id")
                launchable.text = "recharge-ai-task.desktop"
                ET.SubElement(component, "icon", type="stock").text = "recharge-ai-task"
                for kind, url in (("homepage", metadata["homepage"]), ("vcs-browser", metadata["homepage"]), ("bugtracker", metadata["issues"])):
                    ET.SubElement(component, "url", type=kind).text = url
                paragraphs = ET.SubElement(component, "description")
                for paragraph in metadata["description"]:
                    ET.SubElement(paragraphs, "p").text = paragraph
                ET.SubElement(component, "content_rating", type="oars-1.1")
                ET.indent(component)
                metainfo.write_text(ET.tostring(component, encoding="unicode") + "\n")
                icon = tree / "usr/share/icons/hicolor/256x256/apps/recharge-ai-task.png"
                icon.parent.mkdir(parents=True)
                shutil.copy2(ROOT / "recharge_ai_task/assets/icon-256.png", icon)
                copyright_file = tree / "usr/share/doc/recharge-ai-task/copyright"
                copyright_file.parent.mkdir(parents=True)
                shutil.copy2(ROOT / "LICENSE", copyright_file)
                # Debian must never install the temporary directory's private
                # mode (0700) or the builder's group-write umask onto system paths.
                for entry in tree.rglob("*"):
                    entry.chmod(0o755 if entry.is_dir() or entry in (binary, postinst) else 0o644)
                # Debian/Captain display this value in KiB, not compressed bytes.
                installed_size = sum((entry.lstat().st_size + 1023) // 1024 for entry in tree.rglob("*")
                                     if "DEBIAN" not in entry.relative_to(tree).parts)
                control.write_text(control.read_text() + f"Installed-Size: {installed_size}\n")
                target = output / f"recharge-ai-task_{__version__}_amd64.deb"
                subprocess.run(["dpkg-deb", "--root-owner-group", "--build", str(tree), str(target.resolve())], check=True)
                outputs.append(target)
    checksums = output / f"SHA256SUMS-{platform}.txt"
    checksums.write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in outputs))
    return [*outputs, checksums]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=["linux", "windows"])
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    parser.add_argument("--no-deb", action="store_true")
    args = parser.parse_args()
    for output in package(args.platform, args.dist, deb=not args.no_deb):
        print(output)
