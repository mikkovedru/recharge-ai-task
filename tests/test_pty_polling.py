"""Exercise Windows-style blocking terminal reads without a Windows console."""
import queue
import time
import threading
from types import SimpleNamespace

import pytest

from recharge_ai_task.pty_win import WinPtySession
from recharge_ai_task.pty_backend import StopEvent
from recharge_ai_task.wrapper import wait_for_opencode_reset


class BlockingProcess:
    def __init__(self):
        self.output = queue.Queue()
        self.writes = []
        self.exitstatus = 0

    def read(self, size):
        chunk = self.output.get()  # Models pywinpty's blocking read, including silence.
        if isinstance(chunk, Exception):
            raise chunk
        return chunk

    def write(self, data):
        self.writes.append(data)

    def isalive(self):
        return True

    def finish(self):
        self.output.put(EOFError('terminal closed'))


def next_output(session):
    deadline = time.monotonic() + 1
    while time.monotonic() < deadline:
        data = session.read(4096)
        if data:
            return data
    pytest.fail('Output did not arrive')


def test_windows_silent_read_returns_so_deadlines_and_cancellation_can_run():
    process = BlockingProcess()
    session = WinPtySession(process)
    try:
        complete = threading.Event()
        result = []
        def read():
            try:
                result.append(session.read(4096))
            finally:
                complete.set()
        reader = threading.Thread(target=read, daemon=True)
        reader.start()
        assert complete.wait(0.5), 'Silent read blocked the recovery timer'
        assert result == ['']
        stop = StopEvent()
        watcher = SimpleNamespace(native_retry=False, feed=lambda data: None)
        assert wait_for_opencode_reset(session, stop, time.time()+0.2, watcher, 0, stop) is True
        manual_input = threading.Event()
        manual_input.set()
        assert wait_for_opencode_reset(session, stop, time.time()+10, watcher, 0, manual_input) is None
        stop.set()
        assert wait_for_opencode_reset(session, stop, time.time()+10, watcher, 0, stop) is False
    finally:
        process.finish()
        reader.join(timeout=1)


def test_windows_polling_preserves_unicode_order_requested_size_and_eof():
    process = BlockingProcess()
    session = WinPtySession(process)
    process.output.put('α🙂text')
    process.output.put('second')
    process.finish()
    assert next_output(session) == 'α🙂text'
    assert session.read(2) == 'se'
    assert session.read(2) == 'co'
    assert session.read(10) == 'nd'
    with pytest.raises(EOFError):
        session.read(10)
    with pytest.raises(EOFError):
        session.read(10)
    session.write('Continue\r')
    assert process.writes == ['Continue\r'] and session.exitstatus == 0


def test_windows_polling_retains_output_before_read_errors():
    process = BlockingProcess()
    session = WinPtySession(process)
    process.output.put('last output')
    process.output.put(OSError('read failed'))
    assert next_output(session) == 'last output'
    with pytest.raises(OSError, match='read failed'):
        session.read(10)
