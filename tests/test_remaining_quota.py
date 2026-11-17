from recharge_ai_task.quota import RateWindow, Quota, format_quota
import pytest


@pytest.mark.parametrize('used,left', [(0,100),(40,60),(85,15),(100,0),(105,0),(-5,100)])
def test_quota_uses_clamped_remaining_percent(used,left):
    window=RateWindow(used,300,1999999999)
    assert window.remaining_percent==left
    assert f'{left}% left' in format_quota(Quota('test',window,None,False))
    assert '% used' not in format_quota(Quota('test',window,None,False))
