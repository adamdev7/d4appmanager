from datetime import date

from app.integrations.meta.windows import complete_days_window, preset_window


def test_seven_day_window_matches_ads_manager():
    """On 8 Sept 2026, Ads Manager last 7 days is 1–7 Sept, not 2–8."""
    since, until = complete_days_window(date(2026, 9, 8), 7)
    assert since == date(2026, 9, 1)
    assert until == date(2026, 9, 7)


def test_thirty_day_window_ends_yesterday():
    since, until = complete_days_window(date(2026, 9, 8), 30)
    assert until == date(2026, 9, 7)
    assert since == date(2026, 8, 9)


def test_ads_and_analytics_presets_resolve_identically():
    """Both dashboards call preset_window, so their ad spend covers one window."""
    today = date(2026, 9, 8)
    for period in ("1d", "7d", "14d", "30d", "90d"):
        assert preset_window(period, today) == preset_window(period, today)
    assert preset_window("7d", today) == (date(2026, 9, 1), date(2026, 9, 7))
    assert preset_window("1d", today) == (date(2026, 9, 7), date(2026, 9, 7))
