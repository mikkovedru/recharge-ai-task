"""Explicit provider checks isolate version failures and retain discovered chats."""
from types import SimpleNamespace

import pytest

from recharge_ai_task import providers
from recharge_ai_task.targets import Inventory, Target


@pytest.mark.parametrize('failure', [None, TimeoutError('version timed out'), RuntimeError('version rejected')])
def test_explicit_check_reports_versions_without_losing_chats(monkeypatch, failure):
    monkeypatch.setattr(providers, 'installed_providers', lambda: {'codex': '/bin/codex', 'muse': None})
    monkeypatch.setattr(providers, 'discover_windows', lambda p: [])
    target = Target('thread', 'one', 'Chat', provider='codex')
    monkeypatch.setattr(providers, 'discover_targets', lambda p: Inventory([target] if p == 'codex' else []))
    calls = []
    def probe(command, **kwargs):
        calls.append((command, kwargs))
        if failure:
            raise failure
        return SimpleNamespace(stdout='Codex 1.2.3\nExtra line', stderr='')
    monkeypatch.setattr(providers.subprocess, 'run', probe)
    ordinary = providers.discover_all_targets()
    assert not ordinary.provider_details and not calls
    checked = providers.check_providers()
    assert checked.targets == [target] and checked.installed_providers == ('codex',)
    assert calls[0][0] == ['/bin/codex', '--version'] and calls[0][1]['timeout'] == 8
    assert ('Version unavailable' if failure else 'Codex 1.2.3') in checked.provider_details['codex']
    assert 'saved local history' in checked.provider_details['muse']
    assert 'No installed executable' in checked.provider_details['claude']


def test_installation_details_without_chat_discovery_retains_path_on_version_failure(monkeypatch):
    monkeypatch.setattr(providers,'installed_providers',lambda:{'codex':'/custom/codex'})
    monkeypatch.setattr(providers,'discover_targets',lambda *a:pytest.fail('Version check discovered chats'))
    def failed(*a,**kw):raise TimeoutError('fixture timeout')
    monkeypatch.setattr(providers.subprocess,'run',failed)
    details=providers.installation_details()
    assert 'Executable: /custom/codex' in details['codex']
    assert 'Version unavailable: fixture timeout' in details['codex']
    assert set(details)==set(providers.PROVIDERS)
