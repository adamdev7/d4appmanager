""""All time" has to mean all of it.

The store row is created when a user connects the store, so bounding the window
with it truncated revenue to a few weeks while Shopify orders and Meta spend
still used their own lifetime — the P&L then compared weeks of sales against
months of ad spend and reported a loss on a profitable store.
"""

from datetime import UTC, datetime

from app.services.analytics_service import AnalyticsService, lifetime_window_start

STORE_CREATED = datetime(2026, 8, 4, 19, 9, 19, tzinfo=UTC)


def test_window_widens_to_the_first_stripe_transaction():
    first = datetime(2026, 4, 7, 3, 16, 19, tzinfo=UTC)
    start = lifetime_window_start(STORE_CREATED, first)
    assert start == datetime(2026, 4, 7, tzinfo=UTC)
    # Whole first day is included, not the timestamp of the first charge
    assert (start.hour, start.minute, start.second) == (0, 0, 0)


def test_window_never_moves_forward():
    later = datetime(2026, 9, 1, tzinfo=UTC)
    assert lifetime_window_start(STORE_CREATED, later) == STORE_CREATED
    assert lifetime_window_start(STORE_CREATED, None) == STORE_CREATED
    assert lifetime_window_start(STORE_CREATED, STORE_CREATED) == STORE_CREATED


def test_all_time_ends_today_unlike_the_complete_day_presets():
    """Presets stop at yesterday; All time should include today's sales."""
    service = AnalyticsService()
    _, _, since, until = service._parse_range("all")
    today = datetime.now(UTC).date().isoformat()
    assert until == today
    assert since < until


def test_analytics_start_date_still_bounds_all_time():
    """An explicit Shopify launch date is a deliberate floor and must be kept."""
    service = AnalyticsService()
    _, _, since, _ = service._parse_range("all", None, "2026-06-01")
    assert since == "2026-06-01"
