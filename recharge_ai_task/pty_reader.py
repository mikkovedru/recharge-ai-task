"""Bounded polling over a terminal API whose reads may block indefinitely."""
from __future__ import annotations

import queue
import threading
import time


class PollingReader:
    def __init__(self, read, *, timeout=0.1):
        self._read = read
        self._timeout = timeout
        self._chunks = queue.Queue(maxsize=64)
        self._pending = ""
        self._error = None
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        try:
            while True:
                data = self._read(4096)
                if data:
                    self._chunks.put(data)
                else:
                    time.sleep(0.01)
        except Exception as exc:
            self._chunks.put(exc)

    def read(self, size):
        if size <= 0:
            return ""
        if not self._pending:
            if self._error is not None:
                raise self._error
            try:
                chunk = self._chunks.get(timeout=self._timeout)
            except queue.Empty:
                return ""
            if isinstance(chunk, Exception):
                self._error = chunk
                raise chunk
            self._pending = chunk
        result, self._pending = self._pending[:size], self._pending[size:]
        return result
