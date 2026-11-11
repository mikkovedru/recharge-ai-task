"""The saved provider choice changes terminal launch defaults and their tray label."""
import pytest
from recharge_ai_task import cli
from recharge_ai_task.config import AppConfig, PROVIDERS
from recharge_ai_task.i18n import terminal_start_label


@pytest.mark.parametrize('provider,caption', [
    ('codex','Codex'), ('claude','Claude'), ('muse','Muse'),
    ('gemini','Gemini'), ('antigravity','Antigravity'), ('opencode','OpenCode')])
def test_terminal_default_drives_cli_and_live_tray_action(monkeypatch,provider,caption):
    monkeypatch.setenv('PYSTRAY_BACKEND','dummy')
    from recharge_ai_task import tray
    app=tray.TrayApp()
    monkeypatch.setattr(app,'_is_running',lambda:False)
    menu=app._build_menu()
    AppConfig(provider=provider).save()
    expected=f'Start {caption} terminal — auto-continue'
    assert terminal_start_label(provider)==expected
    item=next(item for item in menu.items if item.text==expected)
    assert item.enabled
    captured=[]
    monkeypatch.setattr(cli,'run_wrapper',lambda config:captured.append(config) or 0)
    assert cli.main(['run'])==0
    assert captured[0].provider==provider
    assert PROVIDERS[-1]=='opencode'
