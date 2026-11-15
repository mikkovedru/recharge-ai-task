"""The native fixture must reject default settings before importing GTK."""
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_monitoring_status_ui import BOOT


@pytest.mark.parametrize('directory', [None, str(Path.home() / '.recharge-ai-task'), str(Path.home() / '.codex-charge')])
def test_native_fixture_rejects_real_settings(directory):
    env = dict(os.environ)
    env.pop('RECHARGE_AI_TASK_CONFIG_DIR', None)
    if directory is not None:
        env['RECHARGE_AI_TASK_CONFIG_DIR'] = directory
    result = subprocess.run([sys.executable, '-c', BOOT], env=env, capture_output=True, text=True, timeout=5)
    assert result.returncode != 0
    assert 'Native UI fixtures require an explicit isolated' in result.stderr
