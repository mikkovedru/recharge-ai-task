"""Panel membership migrates independently of delivery preferences."""
from dataclasses import replace
from recharge_ai_task.config import AppConfig
from recharge_ai_task.targets import Target


def test_membership_migration_and_passive_roundtrip():
    active = Target('thread', 'a', 'Active', send_prompt=True, send_goal=False)
    inactive = replace(active, id='b', send_prompt=False)
    config = AppConfig(desktop_targets=[active.to_dict(), inactive.to_dict()])
    config.save()
    assert AppConfig.load().recipients() == [active]
    config.recipient_keys = [active.key, inactive.key]
    config.save()
    assert AppConfig.load().recipients() == [active, inactive]
    assert AppConfig.load().targets() == [active]
    config.recipient_keys = []
    config.desktop_targets = [replace(active, send_prompt=False).to_dict(), inactive.to_dict()]
    config.save()
    assert AppConfig.load().recipients() == []
    assert len(AppConfig.load().all_targets()) == 2
