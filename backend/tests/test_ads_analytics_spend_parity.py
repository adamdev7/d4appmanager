"""Ad spend can only match across tabs if both resolve the same window."""

from app.services.ads_service import AdsService
from app.services.analytics_service import AnalyticsService

PRESETS = ("1d", "7d", "14d", "30d", "90d")


def test_presets_resolve_to_the_same_window_in_both_tabs():
    ads = AdsService()
    analytics = AnalyticsService()
    # Include a timezone far from the default: both tabs must read the ad account
    # timezone the same way, or their windows drift around midnight.
    for timezone_name in (None, "America/Toronto", "Australia/Sydney", "Europe/London"):
        for period in PRESETS:
            _, _, ads_since, ads_until = ads._parse_range(
                period, timezone_name=timezone_name
            )
            _, _, an_since, an_until = analytics._parse_range(
                period, timezone_name=timezone_name
            )
            assert (an_since, an_until) == (ads_since, ads_until), (
                period,
                timezone_name,
            )


def test_presets_exclude_today():
    """Today is still accruing spend — Ads Manager leaves it out, so we do too."""
    from datetime import UTC, datetime

    today = datetime.now(UTC).date().isoformat()
    for period in PRESETS:
        _, _, _, until = AnalyticsService()._parse_range(period)
        assert until < today, period


def test_custom_range_is_taken_literally():
    _, _, since, until = AnalyticsService()._parse_range(
        "custom", custom_since="2026-08-01", custom_until="2026-08-31"
    )
    assert (since, until) == ("2026-08-01", "2026-08-31")
