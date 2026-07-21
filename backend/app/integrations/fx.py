"""FX helpers — convert Stripe currencies to store currency with historical daily rates."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import httpx

_rate_cache: dict[str, Decimal] = {}
_range_cache: dict[str, dict[str, Decimal]] = {}


def _norm(code: str | None) -> str:
    return (code or "").upper().strip()


async def get_rate(
    from_currency: str, to_currency: str, *, on_date: str | None = None
) -> Decimal:
    """
    Spot or historical rate from `from_currency` → `to_currency`.

    `on_date` is YYYY-MM-DD. Weekends/holidays fall back to the nearest prior
    business day (Frankfurter behaviour).
    """
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not src or not dst or src == dst:
        return Decimal("1")

    day = (on_date or "")[:10] or "latest"
    key = f"{src}:{dst}:{day}"
    if key in _rate_cache:
        return _rate_cache[key]

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            if day == "latest":
                url = "https://api.frankfurter.app/latest"
                params = {"from": src, "to": dst}
            else:
                url = f"https://api.frankfurter.app/{day}"
                params = {"from": src, "to": dst}
            resp = await client.get(url, params=params)
            # Historical date may be weekend — Frankfurter returns 404; try back a few days
            if resp.status_code == 404 and day != "latest":
                for back in range(1, 8):
                    d = datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=back)
                    resp = await client.get(
                        f"https://api.frankfurter.app/{d.isoformat()}",
                        params={"from": src, "to": dst},
                    )
                    if resp.status_code == 200:
                        break
            resp.raise_for_status()
            data = resp.json()
            rate = Decimal(str((data.get("rates") or {}).get(dst) or 0))
            if rate <= 0:
                return Decimal("1")
            _rate_cache[key] = rate
            return rate
    except Exception:
        return Decimal("1")


async def get_rates_range(
    from_currency: str, to_currency: str, *, since: str, until: str
) -> dict[str, Decimal]:
    """
    Map YYYY-MM-DD → rate for the inclusive range.

    Missing weekend/holiday days are filled from the previous known rate.
    """
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not src or not dst or src == dst:
        return {}

    since_d = since[:10]
    until_d = until[:10]
    cache_key = f"{src}:{dst}:{since_d}:{until_d}"
    if cache_key in _range_cache:
        return _range_cache[cache_key]

    rates: dict[str, Decimal] = {}
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(
                f"https://api.frankfurter.app/{since_d}..{until_d}",
                params={"from": src, "to": dst},
            )
            resp.raise_for_status()
            data = resp.json()
            for day, day_rates in (data.get("rates") or {}).items():
                r = Decimal(str(day_rates.get(dst) or 0))
                if r > 0:
                    rates[day] = r
    except Exception:
        # Fall back to single latest rate applied to the whole range
        latest = await get_rate(src, dst)
        rates = {}
        try:
            start = datetime.strptime(since_d, "%Y-%m-%d").date()
            end = datetime.strptime(until_d, "%Y-%m-%d").date()
            cur = start
            while cur <= end:
                rates[cur.isoformat()] = latest
                cur += timedelta(days=1)
        except ValueError:
            pass

    # Fill gaps (weekends) with previous business-day rate
    if rates:
        try:
            start = datetime.strptime(since_d, "%Y-%m-%d").date()
            end = datetime.strptime(until_d, "%Y-%m-%d").date()
            last: Decimal | None = None
            # Seed last from earliest available before/on start
            for d in sorted(rates.keys()):
                last = rates[d]
                break
            cur = start
            filled: dict[str, Decimal] = {}
            while cur <= end:
                key = cur.isoformat()
                if key in rates:
                    last = rates[key]
                if last is not None:
                    filled[key] = last
                cur += timedelta(days=1)
            rates = filled
        except ValueError:
            pass

    _range_cache[cache_key] = rates
    return rates


async def convert_amount(
    amount: Decimal,
    *,
    from_currency: str,
    to_currency: str,
    on_date: str | None = None,
) -> Decimal:
    """Convert a single amount. Uses historical rate when `on_date` is set."""
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not src or not dst or src == dst or amount == 0:
        return amount
    rate = await get_rate(src, dst, on_date=on_date)
    return (amount * rate).quantize(Decimal("0.01"))


async def convert_daily_map(
    daily_native: dict[str, Decimal],
    *,
    from_currency: str,
    to_currency: str,
    since: str,
    until: str,
) -> tuple[Decimal, dict[str, Decimal]]:
    """
    Convert a {YYYY-MM-DD: amount} map with per-day historical FX.

    Returns (total_converted, {day: converted_amount}).
    """
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not daily_native:
        return Decimal("0"), {}
    if not src or not dst or src == dst:
        total = sum(daily_native.values(), Decimal("0"))
        return total, dict(daily_native)

    rates = await get_rates_range(src, dst, since=since, until=until)
    converted: dict[str, Decimal] = {}
    total = Decimal("0")
    fallback = await get_rate(src, dst)
    for day, amt in daily_native.items():
        rate = rates.get(day[:10]) or fallback
        cad = (amt * rate).quantize(Decimal("0.01"))
        converted[day[:10]] = converted.get(day[:10], Decimal("0")) + cad
        total += cad
    return total, converted
