"""Process-scoped terminal observations, never an account-wide quota estimate."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

import psutil
from .config import config_dir


class TerminalObservation:
    def __init__(self, provider):
        self.path = None
        self.record = dict(provider=provider, pid=os.getpid(), session=uuid.uuid4().hex, sent=0)
        try:
            self.record['process_started'] = psutil.Process().create_time()
            folder = config_dir() / 'terminal-status'
            folder.mkdir(mode=0o700, exist_ok=True)
            self.path = folder / (self.record['session'] + '.json')
            self.update('running')
        except (OSError, psutil.Error):
            pass  # Observation failures must never interrupt the terminal.

    def update(self, state, wake_at=None):
        self.record.update(state=state, wake_at=wake_at, updated_at=time.time())
        if state == 'continued':
            self.record['sent'] += 1
        if self.path is None:
            return
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(self.record, stream)
            os.replace(temporary, self.path)
        except OSError:
            pass
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass

    def close(self):
        if self.path:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


def live_observations(provider):
    result = []
    for path in sorted((config_dir() / 'terminal-status').glob('*.json'))[:256]:
        try:
            if path.is_symlink() or path.stat().st_size > 16384:
                continue
            record = json.loads(path.read_text())
            if record['provider'] != provider:
                continue
            if record['state'] not in ('running', 'waiting', 'native', 'cancelled', 'continued'):
                continue
            pid = record['pid']
            if type(pid) is not int or pid <= 0:
                continue
            if not math.isfinite(record['process_started']):
                continue
            process = psutil.Process(pid)
            if process.status() == psutil.STATUS_ZOMBIE or abs(process.create_time() - record['process_started']) > .01:
                continue
            if not isinstance(record['session'], str) or not record['session'].isalnum():
                continue
            if type(record['sent']) is not int or record['sent'] < 0:
                continue
            if record.get('wake_at') is not None and (not isinstance(record['wake_at'], (int, float)) or not math.isfinite(record['wake_at'])):
                continue
            result.append(record)
        except (OSError, ValueError, TypeError, KeyError, psutil.Error):
            continue
    return result


def observation_lines(records, now):
    if not records:
        return ['No live wrapped sessions observed in this Recharge profile.']
    lines = ['Live wrapped sessions (observed terminal state, not shared account quota):']
    names = dict(running='Running', native='Native retry or choice dialog owns recovery',
                 cancelled='Pending continuation cancelled by typing', continued='Continuation sent')
    for record in records:
        state = record['state']
        text = names.get(state, 'Waiting for detected reset + grace')
        if state == 'waiting' and record.get('wake_at'):
            remaining = max(0, math.ceil(record['wake_at'] - now))
            hours, remainder = divmod(remaining, 3600)
            minutes, seconds = divmod(remainder, 60)
            text += f' · {hours:02}:{minutes:02}:{seconds:02} remaining'
        lines.append(f"Session {record['session'][:8]} · {text} · {record['sent']} continuations sent")
    return lines
