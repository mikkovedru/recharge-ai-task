"""Package the existing frozen Linux build with verified AppImage update data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from recharge_ai_task import __version__
from recharge_ai_task.desktop_entry import desktop_entry

UPDATE_INFORMATION = "gh-releases-zsync|mikkovedru|recharge-ai-task|latest|recharge-ai-task-*-x86_64.AppImage.zsync"


def checked_tool(path, specification):
    path = Path(path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != specification['sha256']:
        raise RuntimeError(f"Checksum mismatch for {path}; review and update the pinned tool manifest deliberately")
    path.chmod(0o755)
    return path


def tool_file(name, manifest, cache, supplied=None):
    specification = manifest[name]
    if supplied:
        return checked_tool(supplied, specification)
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / (name + '-' + specification['sha256'])
    if not path.exists():
        request = urllib.request.Request(specification['url'], headers={'User-Agent': 'Recharge-AI-task-packager'})
        with urllib.request.urlopen(request, timeout=90) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != specification['sha256']:
            raise RuntimeError(f"Downloaded {name} does not match its pinned checksum")
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
    return checked_tool(path, specification)


def appdir(folder, binary):
    metadata = json.loads((ROOT/'packaging/linux/metadata.json').read_text())
    binary_path = folder/'usr/bin/recharge-ai-task'
    binary_path.parent.mkdir(parents=True)
    shutil.copy2(binary, binary_path)
    binary_path.chmod(0o755)
    launcher = folder/'AppRun'
    launcher.write_text('#!/bin/sh\nset -eu\nHERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\nexec "$HERE/usr/bin/recharge-ai-task" "$@"\n')
    launcher.chmod(0o755)
    desktop = folder/'usr/share/applications/io.github.mikkovedru.recharge_ai_task.desktop'
    desktop.parent.mkdir(parents=True)
    desktop.write_text(desktop_entry('recharge-ai-task', 'recharge-ai-task'))
    (folder/desktop.name).symlink_to(desktop.relative_to(folder))
    icon = folder/'usr/share/icons/hicolor/256x256/apps/recharge-ai-task.png'
    icon.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'recharge_ai_task/assets/icon-256.png', icon)
    (folder/'recharge-ai-task.png').symlink_to(icon.relative_to(folder))
    (folder/'.DirIcon').symlink_to('recharge-ai-task.png')
    license_path = folder/'usr/share/doc/recharge-ai-task/LICENSE'
    license_path.parent.mkdir(parents=True)
    shutil.copy2(ROOT/'LICENSE', license_path)
    component = ET.Element('component', type='desktop-application')
    for tag, value in (('id', 'io.github.mikkovedru.recharge_ai_task'), ('metadata_license', 'CC0-1.0'),
                       ('project_license', 'MIT'), ('name', metadata['name']), ('summary', metadata['summary'])):
        ET.SubElement(component, tag).text = value
    ET.SubElement(component, 'launchable', type='desktop-id').text = desktop.name
    ET.SubElement(component, 'url', type='homepage').text = metadata['homepage']
    developer = ET.SubElement(component, 'developer', id='io.github.mikkovedru')
    ET.SubElement(developer, 'name').text = 'Recharge AI-task contributors'
    description = ET.SubElement(component, 'description')
    for paragraph in metadata['description']:
        ET.SubElement(description, 'p').text = paragraph
    ET.SubElement(component, 'content_rating', type='oars-1.1')
    metainfo = folder/'usr/share/metainfo/io.github.mikkovedru.recharge_ai_task.appdata.xml'
    metainfo.parent.mkdir(parents=True)
    ET.indent(component)
    metainfo.write_text(ET.tostring(component, encoding='unicode')+'\n')
    return folder


def verify_pair(image, update_information=UPDATE_INFORMATION):
    actual = subprocess.check_output([str(image.resolve()), '--appimage-updateinformation'], text=True).strip()
    if actual != update_information:
        raise RuntimeError(f"Incorrect embedded update information: {actual!r}")
    control = image.with_name(image.name+'.zsync')
    header = control.read_bytes().split(b'\n\n', 1)[0].decode('utf-8')
    fields = dict(line.split(': ', 1) for line in header.splitlines() if ': ' in line)
    if (fields.get('Filename') != image.name or fields.get('URL') != image.name
            or fields.get('Length') != str(image.stat().st_size)
            or fields.get('SHA-1') != hashlib.sha1(image.read_bytes()).hexdigest()):
        raise RuntimeError('The .zsync control file does not describe the final AppImage bytes and relative URL')
    return control


def build(binary, output, *, tool=None, runtime=None, cache=None):
    if platform.system() != 'Linux' or platform.machine() != 'x86_64':
        raise RuntimeError('Build AppImages on Linux x86_64; no cross-compilation is configured')
    binary = Path(binary).resolve()
    version = subprocess.check_output([str(binary), '--version'], text=True).strip()
    if version != f'Recharge AI-task {__version__}':
        raise RuntimeError(f'Frozen executable version does not match source: {version}')
    manifest = json.loads((ROOT/'packaging/linux/appimage-tools.json').read_text())
    cache = Path(cache or ROOT/'build/appimage-tools')
    tool = tool_file('appimagetool', manifest, cache, tool)
    runtime = tool_file('runtime', manifest, cache, runtime)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='recharge-appimage-') as temporary:
        work = Path(temporary)
        subprocess.run([str(tool.resolve()), '--appimage-extract'], cwd=work, check=True, stdout=subprocess.DEVNULL)
        image = work/f'recharge-ai-task-{__version__}-x86_64.AppImage'
        directory = appdir(work/'Recharge.AppDir', binary)
        subprocess.run(['appstreamcli', 'validate', '--no-net', str(directory/'usr/share/metainfo/io.github.mikkovedru.recharge_ai_task.appdata.xml')], check=True)
        env = dict(os.environ, ARCH='x86_64', VERSION=__version__)
        command = [str(work/'squashfs-root/AppRun'), '--no-appstream', '--runtime-file', str(runtime.resolve()),
                   '--comp', 'zstd', '--mksquashfs-opt', '-processors', '--mksquashfs-opt', '2',
                   '--updateinformation', UPDATE_INFORMATION, '--file-url', image.name,
                   str(directory), str(image)]
        subprocess.run(command, check=True, env=env, cwd=work)
        control = verify_pair(image)
        outputs = []
        for path in (image, control):
            destination = output/path.name
            staged = destination.with_name(destination.name+'.tmp')
            shutil.copy2(path, staged)
            staged.replace(destination)
            outputs.append(destination)
        checksums = output/'SHA256SUMS-appimage.txt'
        checksums.write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in outputs))
        return [*outputs, checksums]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--binary', type=Path, default=ROOT/'dist/recharge-ai-task')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/release')
    parser.add_argument('--tool', type=Path, help='Pinned official appimagetool AppImage; checksum still required')
    parser.add_argument('--runtime', type=Path, help='Pinned runtime; checksum still required')
    parser.add_argument('--cache', type=Path)
    args = parser.parse_args()
    for artifact in build(args.binary, args.output, tool=args.tool, runtime=args.runtime, cache=args.cache):
        print(artifact)
