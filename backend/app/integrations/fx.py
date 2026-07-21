"""Lightweight FX helper for blending Stripe / Meta / Shopify currencies."""

from __future__ import annotations

from decimal import Decimal

import httpx

_rate_cache: dict[str, Decimal] = {}


async def convert_amount(
    amount: Decimal, *, from_currency: str, to_currency: str
) -> Decimal:
    """Convert amount between ISO currencies. Same currency → unchanged."""
    src = (from_currency or "").upper().strip()
    dst = (to_currency or "").upper().strip()
    if not src or not dst or src == dst or amount == 0:
        return amount
    rate = await get_rate(src, dst)
    return (amount * rate).quantize(Decimal("0.01"))


async def get_rate(from_currency: str, to_currency: str) -> Decimal:
    src = from_currency.upper().strip()
    dst = to_currency.upper().strip()
    if src == dst:
        return Decimal("1")
    key = f"{src}:{dst}"
    if key in _rate_cache:
        return _rate_cache[key]
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"https://api.frankfurter.app/latest",
                params={"from": src, "to": dst},
            )
            resp.raise_for_status()
            data = resp.json()
            rate = Decimal(str((data.get("rates") or {}).get(dst) or 0))
            if rate <= 0:
                return Decimal("1")
            _rate_cache[key] = rate
            return rate
    except Exception:
        # Fail open — better to show unconverted than block the dashboard
        return Decimal("1")
