"""Shared reporting windows so Ads and Analytics never disagree on a date range.

Meta Ads Manager presets cover the last N *complete* days in the ad account
timezone — today is excluded because it is still accruing spend. Both the Ads
dashboard and the Analytics P&L use these helpers so their ad spend matches.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

# Meta bills this business in CAD. Never label ad spend with the Shopify or
# Stripe currency (often GBP) — that silently changes the number.
META_BILLING_CURRENCY = "CAD"

DEFAULT_ADS_TIMEZONE = "America/Toronto"

# Preset id → number of complete days to include.
PRESET_DAYS: dict[str, int] = {
    "1d": 1,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "90d": 90,
}


def ads_zone(name: str | None) -> ZoneInfo:
    """Ad account timezone, falling back to the account default then UTC."""
    for candidate in (name, DEFAULT_ADS_TIMEZONE, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(candidate)
        except Exception:
            continue
    return ZoneInfo("UTC")


def today_in_zone(timezone_name: str | None) -> date:
    return datetime.now(ads_zone(timezone_name)).date()


def complete_days_window(today: date, days: int) -> tuple[date, date]:
    """Last `days` complete days ending yesterday — Ads Manager preset behaviour."""
    end_d = today - timedelta(days=1)
    start_d = end_d - timedelta(days=max(days, 1) - 1)
    return start_d, end_d


def preset_window(period: str, today: date) -> tuple[date, date]:
    """Resolve a preset id (7d, 30d, …) to its complete-day window."""
    return complete_days_window(today, PRESET_DAYS.get(period, 30))


# An ad account's name, currency and timezone effectively never change, so both
# dashboards share one long-lived lookup instead of calling Graph on every load.
_ACCOUNT_INFO_TTL_SECONDS = 6 * 60 * 60
_account_info_cache: dict[str, tuple[float, dict]] = {}


async def cached_account_info(
    account_id: str | None, fetcher: Callable[[], Awaitable[dict]]
) -> dict:
    """Ad account metadata, cached per process."""
    key = account_id or ""
    hit = _account_info_cache.get(key)
    if hit and time.monotonic() - hit[0] < _ACCOUNT_INFO_TTL_SECONDS:
        return hit[1]
    info = await fetcher()
    if info:
        _account_info_cache[key] = (time.monotonic(), info)
    return info or {}
