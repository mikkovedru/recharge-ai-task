import hashlib
import importlib.util
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_appimage', ROOT/'scripts/build_appimage.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)


def test_appdir_has_launchable_metadata_icon_license_and_no_host_paths(tmp_path):
    binary=tmp_path/'binary';binary.write_bytes(b'fixture')
    directory=builder.appdir(tmp_path/'AppDir',binary)
    assert (directory/'usr/bin/recharge-ai-task').read_bytes()==b'fixture'
    desktop=directory/'io.github.mikkovedru.recharge_ai_task.desktop'
    assert desktop.is_file()
    assert 'Exec=recharge-ai-task\n' in desktop.read_text()
    assert (directory/'.DirIcon').read_bytes()==(ROOT/'recharge_ai_task/assets/icon-256.png').read_bytes()
    assert '"$@"' in (directory/'AppRun').read_text()
    assert (directory/'usr/share/doc/recharge-ai-task/LICENSE').is_file()


def test_tool_checksum_is_mandatory(tmp_path):
    path=tmp_path/'tool';path.write_bytes(b'tool')
    with pytest.raises(RuntimeError,match='Checksum mismatch'):
        builder.checked_tool(path,{'sha256':'0'*64})
    assert builder.checked_tool(path,{'sha256':hashlib.sha256(b'tool').hexdigest()})==path


def test_update_pair_checks_final_bytes_and_url(tmp_path,monkeypatch):
    image=tmp_path/'recharge-ai-task-1.0-x86_64.AppImage';image.write_bytes(b'image')
    control=image.with_name(image.name+'.zsync')
    header=f'Filename: {image.name}\nURL: {image.name}\nLength: 5\nSHA-1: {hashlib.sha1(b"image").hexdigest()}\n\n'
    control.write_bytes(header.encode()+b'blocks')
    monkeypatch.setattr(builder.subprocess,'check_output',lambda *a,**k:builder.UPDATE_INFORMATION+'\n')
    assert builder.verify_pair(image)==control
    image.write_bytes(b'changed image')
    with pytest.raises(RuntimeError,match='final AppImage bytes'):
        builder.verify_pair(image)


def test_frozen_relaunches_use_persistent_appimage(tmp_path,monkeypatch):
    monkeypatch.setenv('PYSTRAY_BACKEND','dummy')
    from recharge_ai_task import desktop_launch,desktop_integration,autostart,tray
    image=tmp_path/'An App %.AppImage';image.write_bytes(b'image')
    monkeypatch.setattr(sys,'frozen',True,raising=False)
    monkeypatch.setattr(sys,'platform','linux')
    monkeypatch.setenv('APPIMAGE',str(image))
    assert desktop_launch.desktop_command()==[str(image)]
    assert desktop_integration._commands()=={'recharge-ai-task':[str(image)]}
    assert tray._resolve_cli_exe()==[str(image)]
    assert autostart._tray_command()==desktop_integration._exec_value([str(image),'--tray','--autostart'])
    monkeypatch.setenv('XDG_CONFIG_HOME',str(tmp_path/'xdg'))
    assert autostart.autostart_target().parent==tmp_path/'xdg/autostart'
    monkeypatch.delenv('APPIMAGE')
    assert desktop_launch.desktop_command()!=[str(image)]
