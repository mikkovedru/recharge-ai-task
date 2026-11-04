"""Real manager process death and scaled drawing, on a private X11 server."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(os.environ.get('RECHARGE_AI_TASK_GUI_TESTS') != '1' or not shutil.which('Xephyr'),
    reason='Requires GTK and a nested Xephyr display')
HELPER = Path(__file__).with_name('tray_x11_fixture.py')


def line(process, timeout=5):
    assert select.select([process.stdout], [], [], timeout)[0], 'Native fixture did not respond'
    value = process.stdout.readline()
    assert value, 'Native fixture exited early'
    return json.loads(value)


def ask(process, command='status'):
    process.stdin.write(command+'\n');process.stdin.flush()
    return line(process)


def until(process, predicate, timeout=6):
    deadline = time.monotonic()+timeout
    last = None
    while time.monotonic()<deadline:
        last = ask(process)
        if predicate(last):return last
        time.sleep(.1)
    pytest.fail(f'Tray state did not recover: {last}')


@pytest.mark.parametrize('scale', [1, 2])
def test_manager_restart_and_relaunch_preserve_services_and_fill_pixels(tmp_path, scale):
    processes = []
    logs = []
    def start(argv, env=None):
        log = (tmp_path/f'process-{len(logs)}.log').open('w+')
        logs.append(log)
        process = subprocess.Popen(argv, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=log, text=True)
        processes.append(process)
        return process
    read_fd, write_fd = os.pipe()
    display_log = (tmp_path/'xephyr.log').open('w+')
    server = subprocess.Popen(['Xephyr', '-displayfd', str(write_fd), '-screen', '320x160',
        '-nolisten', 'tcp', '-ac', '-no-host-grab'], pass_fds=(write_fd,), stdout=display_log, stderr=display_log)
    processes.append(server)
    os.close(write_fd)
    try:
        assert select.select([read_fd], [], [], 5)[0], 'Xephyr did not start'
        number = os.read(read_fd, 100).decode().strip()
        assert number.isdigit(), 'Xephyr returned an invalid display number'
        env = dict(os.environ, DISPLAY=':'+number, GDK_SCALE=str(scale),
            XDG_CURRENT_DESKTOP='X-Cinnamon', PYSTRAY_BACKEND='gtk',
            RECHARGE_AI_TASK_CONFIG_DIR=str(tmp_path/'config'))
        size = 24 * scale
        manager = start([sys.executable, str(HELPER), 'manager', str(size)], env)
        assert line(manager)['ready']
        client = start([sys.executable, str(HELPER), 'client'], env)
        initial = until(client, lambda state: state.get('embedded') and state.get('blue', 0)>0)
        original = ask(client, 'start-watch')
        assert original['watch']
        for _ in range(2):
            manager.kill();manager.wait(timeout=3)
            # Longer than the 500ms refresh: its integer X.NONE reply must not
            # throw and make GLib remove the timeout while no manager exists.
            time.sleep(.8)
            missing = ask(client)
            assert missing['timer'], missing
            manager = start([sys.executable, str(HELPER), 'manager', str(size)], env)
            assert line(manager)['ready']
            recovered = until(client, lambda state: state.get('embedded') and state.get('blue', 0)>0)
            assert recovered['pid'] == original['pid']
            assert recovered['menu'] == original['menu']
            assert recovered['watch'] and recovered['watch_thread'] == original['watch_thread']
        assert (recovered['width'], recovered['height'], recovered['rendered']) == (size,size,size)
        assert recovered['white']>size and recovered['blue']>size
        assert all(0<min(rgb) and max(rgb)<100 for rgb in recovered['corners']), repr(recovered)
        for args in (['--tray'], []):
            broken = ask(client, 'break')
            assert not broken['timer']
            result = subprocess.run([sys.executable, '-m', 'recharge_ai_task.gui', *args],
                env=env, capture_output=True, text=True, timeout=8)
            assert result.returncode == 0, result.stderr
            repaired = until(client, lambda state: state.get('embedded') and state.get('blue', 0)>0)
            assert repaired['watch'] and repaired['watch_thread'] == original['watch_thread']
            assert repaired['pid'] == original['pid'] and repaired['menu'] == original['menu']
            assert (repaired['width'],repaired['height'],repaired['rendered']) == (size,size,size)
            assert all(0<min(rgb) and max(rgb)<100 for rgb in repaired['corners']), repr(repaired)
        ask(client, 'stop');client.wait(timeout=5)
        for log in logs:
            log.flush();log.seek(0)
            assert 'Traceback' not in log.read(), log.name
    finally:
        os.close(read_fd)
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        for log in logs:log.close()
        display_log.close()
