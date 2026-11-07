"""Separate Codex management listeners from app-server metadata connections."""
import os
import socket
import struct
import threading
from pathlib import Path

import pytest

from recharge_ai_task import targets


def peer_process(monkeypatch, executable, arguments, *, missing=False):
    original_readlink = os.readlink
    original_read_bytes = Path.read_bytes
    def readlink(path, *args, **kwargs):
        if str(path) == '/proc/123/exe':
            if missing:
                raise PermissionError('process unavailable')
            return executable
        return original_readlink(path, *args, **kwargs)
    def read_bytes(path):
        if str(path) == '/proc/123/cmdline':
            return b'\0'.join(os.fsencode(arg) for arg in arguments) + b'\0'
        return original_read_bytes(path)
    monkeypatch.setattr(os, 'readlink', readlink)
    monkeypatch.setattr(Path, 'read_bytes', read_bytes)
    class Connection:
        def getsockopt(self, *args):
            return struct.pack('3i', 123, os.getuid(), os.getgid())
    return Connection()


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'), reason='Linux peer credentials')
@pytest.mark.parametrize('executable,args,control', [
    ('/package/codex', ['codex','app-server','daemon'], True),
    ('/package/codex (deleted)', ['codex','-c','x=1','app-server','daemon'], True),
    ('/package/codex', ['codex','app-server','--listen','unix://','--managed-daemon'], False),
    ('/package/codex', ['codex','app-server','proxy'], False),
    ('/package/python', ['python','app-server','daemon'], False),
    ('/package/codex', ['codex','exec','app-server daemon'], False),
])
def test_management_role_uses_verified_peer_command(monkeypatch, executable, args, control):
    assert targets._daemon_control_peer(peer_process(monkeypatch, executable, args)) is control


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'), reason='Linux peer credentials')
def test_unknown_peer_is_not_silently_discarded(monkeypatch):
    assert not targets._daemon_control_peer(peer_process(monkeypatch, '', [], missing=True))


@pytest.mark.skipif(not hasattr(socket, 'AF_UNIX'), reason='Unix sockets')
def test_management_peer_receives_no_websocket_handshake(tmp_path, monkeypatch):
    path = tmp_path / 'control'
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(path)); listener.listen(); listener.settimeout(2)
    received = []
    def server():
        with listener.accept()[0] as connection:
            connection.settimeout(2)
            received.append(connection.recv(4096))
    worker = threading.Thread(target=server)
    worker.start()
    monkeypatch.setattr(targets, '_daemon_control_peer', lambda _: True)
    import websocket
    monkeypatch.setattr(websocket, 'create_connection', lambda *a, **k: pytest.fail('Sent a WebSocket handshake to management'))
    try:
        with pytest.raises(targets.DaemonControlSocket):
            with targets.AppServer(str(path)):
                pytest.fail('Entered metadata session on management')
        worker.join(3)
        assert not worker.is_alive() and received == [b'']
    finally:
        listener.close()
        worker.join(3)


def inventory(monkeypatch, tmp_path, endpoints):
    directory = tmp_path / 'sockets'; directory.mkdir()
    home = tmp_path / 'profile'; home.mkdir()
    listeners = []
    for name in endpoints:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.bind(str(directory / name)); listeners.append(listener)
    monkeypatch.setattr(targets, 'daemon_socket_directory', lambda: directory)
    monkeypatch.setattr(targets, 'discover_homes', lambda: {home})
    monkeypatch.setattr(targets, 'discover_windows', lambda: [])
    monkeypatch.setattr(targets, '_saved_threads', lambda _: [{'id':'saved','title':'Saved fallback'}])
    monkeypatch.setattr(targets, '_saved_goals', lambda _: None)
    monkeypatch.setattr(targets, '_saved_project_names', lambda _: {})
    class Server:
        def __init__(self, path): self.kind = Path(path).name
        def __enter__(self):
            if self.kind == 'control': raise targets.DaemonControlSocket()
            if self.kind == 'broken-worker': raise ConnectionResetError(104, 'Connection reset by peer')
            self.home = home
            return self
        def threads(self): return [{'id':'live','title':'Live worker metadata'}]
        def __exit__(self, *_): pass
    monkeypatch.setattr(targets, 'AppServer', Server)
    try:
        return targets.discover_targets()
    finally:
        for listener in listeners: listener.close()


@pytest.mark.skipif(not hasattr(socket, 'AF_UNIX'), reason='Unix sockets')
def test_healthy_worker_with_management_socket_has_no_daemon_warning(monkeypatch, tmp_path):
    result = inventory(monkeypatch, tmp_path, ('control','worker'))
    assert [t.id for t in result.targets] == ['live']
    assert not any('daemon' in warning.lower() for warning in result.warnings)


@pytest.mark.skipif(not hasattr(socket, 'AF_UNIX'), reason='Unix sockets')
def test_real_metadata_reset_stays_visible_and_preserves_saved_chats(monkeypatch, tmp_path):
    result = inventory(monkeypatch, tmp_path, ('control','broken-worker'))
    assert [t.id for t in result.targets] == ['saved']
    assert any('Codex daemon metadata (broken-worker)' in w and 'Connection reset by peer' in w for w in result.warnings)
    assert any('no metadata connection succeeded' in w for w in result.warnings)


@pytest.mark.skipif(not hasattr(socket, 'AF_UNIX'), reason='Unix sockets')
def test_management_without_worker_reports_missing_metadata(monkeypatch, tmp_path):
    result = inventory(monkeypatch, tmp_path, ('control',))
    assert [t.id for t in result.targets] == ['saved']
    assert any('no metadata connection succeeded' in w for w in result.warnings)


@pytest.mark.skipif(not hasattr(socket, 'SO_PEERCRED'), reason='Linux peer credentials')
def test_foreign_metadata_peer_is_rejected_before_protocol_io():
    class Connection:
        def getsockopt(self, *args):
            return struct.pack('3i', 123, os.getuid()+1, os.getgid())
    with pytest.raises(OSError, match='not owned by this user'):
        targets._daemon_control_peer(Connection())
