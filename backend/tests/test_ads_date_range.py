from datetime import date

from app.services.ads_service import _complete_days_window


def test_seven_day_window_matches_ads_manager():
    """On 8 Sept 2026, Ads Manager last 7 days is 1–7 Sept, not 2–8."""
    since, until = _complete_days_window(date(2026, 9, 8), 7)
    assert since == date(2026, 9, 1)
    assert until == date(2026, 9, 7)


def test_thirty_day_window_ends_yesterday():
    since, until = _complete_days_window(date(2026, 9, 8), 30)
    assert until == date(2026, 9, 7)
    assert since == date(2026, 8, 9)
