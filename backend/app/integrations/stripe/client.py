"""Stripe API helpers for multi-MID subscription / MRR aggregation."""

from __future__ import annotations

from decimal import Decimal

import httpx

STRIPE_API_BASE = "https://api.stripe.com/v1"


def _interval_to_monthly_factor(amount: Decimal, interval: str, interval_count: int) -> Decimal:
    """Normalize a recurring amount to monthly MRR contribution."""
    count = max(interval_count or 1, 1)
    interval = (interval or "month").lower()
    if interval == "month":
        return amount / count
    if interval == "year":
        return amount / (Decimal("12") * count)
    if interval == "week":
        return amount * Decimal("52") / (Decimal("12") * count)
    if interval == "day":
        return amount * Decimal("30.44") / count
    return amount


class StripeClient:
    def __init__(self, secret_key: str) -> None:
        self.secret_key = secret_key.strip()

    async def test_connection(self) -> tuple[bool, str, str | None]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{STRIPE_API_BASE}/balance",
                auth=(self.secret_key, ""),
            )
            if resp.status_code != 200:
                err = resp.json().get("error", {}) if resp.headers.get("content-type", "").startswith("application/json") else {}
                msg = err.get("message") or resp.text[:200]
                return False, f"Stripe error: {msg}", None
            return True, "Stripe key works", None

    async def list_active_subscriptions(self, *, limit_pages: int = 20) -> list[dict]:
        """Paginate active + trialing subscriptions with price expansion."""
        subs: list[dict] = []
        starting_after: str | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            for _ in range(limit_pages):
                params: list[tuple[str, str | int]] = [
                    ("limit", 100),
                    ("expand[]", "data.items.data.price"),
                ]
                if starting_after:
                    params.append(("starting_after", starting_after))
                resp = await client.get(
                    f"{STRIPE_API_BASE}/subscriptions",
                    params=params,
                    auth=(self.secret_key, ""),
                )
                resp.raise_for_status()
                payload = resp.json()
                batch = list(payload.get("data") or [])
                for sub in batch:
                    status = sub.get("status") or ""
                    if status in ("active", "trialing", "past_due"):
                        subs.append(sub)
                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break
        return subs

    async def compute_mrr(self) -> tuple[Decimal, int]:
        """Return (monthly_mrr, subscriber_count) from Stripe Billing subscriptions."""
        subs = await self.list_active_subscriptions()
        total = Decimal("0")
        for sub in subs:
            items = ((sub.get("items") or {}).get("data")) or []
            for item in items:
                qty = Decimal(str(item.get("quantity") or 1))
                price = item.get("price") or {}
                unit = Decimal(str(price.get("unit_amount") or 0)) / Decimal("100")
                recurring = price.get("recurring") or {}
                interval = recurring.get("interval") or "month"
                interval_count = int(recurring.get("interval_count") or 1)
                total += _interval_to_monthly_factor(unit * qty, interval, interval_count)
        return total, len(subs)
