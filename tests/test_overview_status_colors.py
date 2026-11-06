"""Overview colors describe displayed states without changing recovery policy."""
import pytest
from recharge_ai_task.status_display import overview_status_level


@pytest.mark.parametrize('text,level',[
    ('No send scheduled','warning'),
    ('Desktop monitoring is off.','error'),
    ('Next reset forecast: 2026-11-06 20:00:00','success'),
    ('Forecast: 2026-11-06 20:00:00','success'),
    ('Updating…','warning'),
    ('Checking…','warning'),
    ('Waiting for worker schedule','normal'),
    ('Allowances unavailable','normal'),
    ('Worker update overdue','normal'),
    ('Sending now','normal'),
])
def test_overview_status_color(text,level):
    assert overview_status_level(text)==level
