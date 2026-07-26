"""FX helpers — convert Stripe currencies to store currency with historical daily rates."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)

_rate_cache: dict[str, Decimal] = {}
_range_cache: dict[str, dict[str, Decimal]] = {}


class FxError(RuntimeError):
    """Raised when no FX provider returns a usable rate."""


def _norm(code: str | None) -> str:
    return (code or "").upper().strip()


def _parse_rate(data: dict, dst: str) -> Decimal | None:
    rates = data.get("rates") or {}
    raw = rates.get(dst) or rates.get(dst.lower())
    if raw is None:
        return None
    rate = Decimal(str(raw))
    return rate if rate > 0 else None


async def _fetch_frankfurter(
    client: httpx.AsyncClient, src: str, dst: str, day: str
) -> Decimal | None:
    if day == "latest":
        urls = [
            ("https://api.frankfurter.app/latest", {"from": src, "to": dst}),
            ("https://api.frankfurter.dev/v1/latest", {"base": src, "symbols": dst}),
        ]
        for url, params in urls:
            resp = await client.get(url, params=params)
            if resp.status_code != 200:
                continue
            rate = _parse_rate(resp.json(), dst)
            if rate:
                return rate
        return None

    for host in ("https://api.frankfurter.app", "https://api.frankfurter.dev/v1"):
        resp = await client.get(f"{host}/{day}", params={"from": src, "to": dst})
        if resp.status_code == 404:
            for back in range(1, 8):
                d = datetime.strptime(day, "%Y-%m-%d").date() - timedelta(days=back)
                resp = await client.get(
                    f"{host}/{d.isoformat()}",
                    params={"from": src, "to": dst},
                )
                if resp.status_code == 200:
                    break
        if resp.status_code != 200:
            # frankfurter.dev uses base/symbols
            resp = await client.get(
                f"{host}/{day}", params={"base": src, "symbols": dst}
            )
        if resp.status_code == 200:
            rate = _parse_rate(resp.json(), dst)
            if rate:
                return rate
    return None


async def _fetch_open_er_api(client: httpx.AsyncClient, src: str, dst: str) -> Decimal | None:
    """Spot rates only (no historical). Free, no API key."""
    resp = await client.get(f"https://open.er-api.com/v6/latest/{src}")
    if resp.status_code != 200:
        return None
    data = resp.json()
    if str(data.get("result") or "").lower() not in ("success", "true", ""):
        # Some responses omit result; still try rates
        if "rates" not in data:
            return None
    return _parse_rate(data, dst)


async def get_rate(
    from_currency: str, to_currency: str, *, on_date: str | None = None
) -> Decimal:
    """
    Spot or historical rate from `from_currency` → `to_currency`.

    `on_date` is YYYY-MM-DD. Weekends/holidays fall back to the nearest prior
    business day (Frankfurter behaviour).

    Raises FxError when currencies differ and no provider returns a rate
    (never silently returns 1.0 — that would leave GBP amounts labeled as CAD).
    """
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not src or not dst or src == dst:
        return Decimal("1")

    day = (on_date or "")[:10] or "latest"
    key = f"{src}:{dst}:{day}"
    if key in _rate_cache:
        return _rate_cache[key]

    errors: list[str] = []
    async with httpx.AsyncClient(timeout=20) as client:
        try:
            rate = await _fetch_frankfurter(client, src, dst, day)
            if rate:
                _rate_cache[key] = rate
                return rate
            errors.append("frankfurter: no rate")
        except Exception as e:
            errors.append(f"frankfurter: {e}")

        # Historical date unavailable → still try latest spot
        if day != "latest":
            try:
                rate = await _fetch_frankfurter(client, src, dst, "latest")
                if rate:
                    logger.warning(
                        "FX historical %s→%s on %s unavailable; using latest %s",
                        src,
                        dst,
                        day,
                        rate,
                    )
                    _rate_cache[key] = rate
                    return rate
            except Exception as e:
                errors.append(f"frankfurter-latest: {e}")

        try:
            rate = await _fetch_open_er_api(client, src, dst)
            if rate:
                logger.info("FX %s→%s via open.er-api: %s", src, dst, rate)
                _rate_cache[key] = rate
                return rate
            errors.append("open.er-api: no rate")
        except Exception as e:
            errors.append(f"open.er-api: {e}")

    msg = f"No FX rate for {src}→{dst} ({day}): {'; '.join(errors)}"
    logger.error(msg)
    raise FxError(msg)


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
    except Exception as e:
        logger.warning("FX range fetch failed (%s→%s): %s — using latest spot", src, dst, e)
        latest = await get_rate(src, dst)
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
    converted, _rate = await convert_amount_with_rate(
        amount,
        from_currency=from_currency,
        to_currency=to_currency,
        on_date=on_date,
    )
    return converted


async def convert_amount_with_rate(
    amount: Decimal,
    *,
    from_currency: str,
    to_currency: str,
    on_date: str | None = None,
) -> tuple[Decimal, Decimal]:
    """Convert amount and return (converted_amount, fx_rate_used)."""
    src = _norm(from_currency)
    dst = _norm(to_currency)
    if not src or not dst or src == dst or amount == 0:
        return amount, Decimal("1")
    rate = await get_rate(src, dst, on_date=on_date)
    return (amount * rate).quantize(Decimal("0.01")), rate


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
