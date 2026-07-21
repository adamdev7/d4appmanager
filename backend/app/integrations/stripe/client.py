"""Stripe API helpers for multi-MID subscription / MRR aggregation."""

from __future__ import annotations

import time
from decimal import Decimal
from typing import Any

import httpx

STRIPE_API_BASE = "https://api.stripe.com/v1"

# Stripe zero-decimal currencies (amount is already in major units).
# https://stripe.com/docs/currencies#zero-decimal
ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "bif",
        "clp",
        "djf",
        "gnf",
        "jpy",
        "kmf",
        "krw",
        "mga",
        "pyg",
        "rwf",
        "ugx",
        "vnd",
        "vuv",
        "xaf",
        "xof",
        "xpf",
    }
)

# Paying / retained subscribers (exclude incomplete checkouts).
SUBSCRIBER_STATUSES = frozenset({"active", "past_due", "trialing"})


def _norm_currency(currency: str | None) -> str:
    return (currency or "").strip().lower()


def from_stripe_amount(amount: Any, currency: str | None) -> Decimal:
    """Convert Stripe integer amount to major currency units for the given currency."""
    raw = Decimal(str(amount or 0))
    cur = _norm_currency(currency)
    if cur in ZERO_DECIMAL_CURRENCIES:
        return raw
    return raw / Decimal("100")


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
                err = (
                    resp.json().get("error", {})
                    if resp.headers.get("content-type", "").startswith("application/json")
                    else {}
                )
                msg = err.get("message") or resp.text[:200]
                return False, f"Stripe error: {msg}", None
            data = resp.json()
            # Prefer available/pending balance currency as account hint
            acct_currency = None
            for bucket in ("available", "pending"):
                rows = data.get(bucket) or []
                if rows and isinstance(rows, list):
                    acct_currency = (rows[0].get("currency") or "").upper() or None
                    if acct_currency:
                        break
            return True, "Stripe key works", acct_currency

    async def account_default_currency(self) -> str | None:
        """Best-effort default currency for this Stripe account."""
        ok, _, currency = await self.test_connection()
        return currency.upper() if ok and currency else None

    async def list_active_subscriptions(self, *, limit_pages: int = 50) -> list[dict]:
        """Paginate subscriptions that count as current subscribers."""
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
                    status = (sub.get("status") or "").lower()
                    if status in SUBSCRIBER_STATUSES:
                        subs.append(sub)
                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break
        return subs

    async def period_charge_totals(
        self,
        *,
        since_ts: int,
        until_ts: int,
        currency: str | None = None,
    ) -> dict[str, Decimal | int | str | None]:
        """
        Sum charges in [since_ts, until_ts] for a single currency.

        Uses Charges API with `balance_transaction` expanded so `net` already
        excludes Stripe fees. When `currency` is set, other currencies are ignored
        so totals match the App Manager store currency.
        """
        target = _norm_currency(currency)
        gross = Decimal("0")
        fees = Decimal("0")
        net = Decimal("0")
        charge_count = 0
        customers: set[str] = set()
        currencies_seen: set[str] = set()
        starting_after: str | None = None

        async with httpx.AsyncClient(timeout=60) as client:
            for _ in range(30):
                params: list[tuple[str, str | int]] = [
                    ("limit", 100),
                    ("created[gte]", int(since_ts)),
                    ("created[lte]", int(until_ts)),
                    ("expand[]", "data.balance_transaction"),
                ]
                if starting_after:
                    params.append(("starting_after", starting_after))
                resp = await client.get(
                    f"{STRIPE_API_BASE}/charges",
                    params=params,
                    auth=(self.secret_key, ""),
                )
                resp.raise_for_status()
                payload = resp.json()
                batch = list(payload.get("data") or [])
                for ch in batch:
                    if ch.get("status") != "succeeded":
                        continue
                    cur = _norm_currency(ch.get("currency"))
                    if cur:
                        currencies_seen.add(cur.upper())
                    if target and cur and cur != target:
                        continue

                    amt = from_stripe_amount(ch.get("amount"), cur)
                    refunded = from_stripe_amount(ch.get("amount_refunded"), cur)
                    effective_gross = amt - refunded
                    bt = ch.get("balance_transaction")
                    if isinstance(bt, dict):
                        bt_cur = _norm_currency(bt.get("currency")) or cur
                        fee = from_stripe_amount(bt.get("fee"), bt_cur)
                        n = from_stripe_amount(bt.get("net"), bt_cur)
                        if amt > 0 and refunded > 0:
                            remaining_ratio = effective_gross / amt
                            n = n * remaining_ratio
                            fee = fee * remaining_ratio
                    else:
                        fee = Decimal("0")
                        n = effective_gross

                    gross += effective_gross
                    fees += fee
                    net += n
                    if ch.get("paid") and effective_gross > 0:
                        charge_count += 1
                    cust_key = self._customer_key(ch)
                    if cust_key:
                        customers.add(cust_key)

                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break

        return {
            "gross": gross,
            "fees": fees,
            "net": net,
            "charge_count": charge_count,
            "unique_sources": len(customers),
            "currency": (target.upper() if target else (next(iter(currencies_seen), None))),
            "currencies_seen": ",".join(sorted(currencies_seen)),
        }

    @staticmethod
    def _customer_key(obj: dict) -> str | None:
        """Stable unique key for a paying customer."""
        cust = obj.get("customer")
        if isinstance(cust, dict) and cust.get("id"):
            return f"cus:{cust['id']}"
        if isinstance(cust, str) and cust:
            return f"cus:{cust}"
        billing = obj.get("billing_details") or {}
        email = (billing.get("email") or obj.get("email") or "").strip().lower()
        if email:
            return f"email:{email}"
        return None

    async def compute_mrr(
        self, *, currency: str | None = None
    ) -> tuple[Decimal, int, str | None]:
        """
        Return (monthly_mrr, unique_subscriber_count, currency_used).

        Subscribers = unique Stripe customers with active / past_due / trialing
        subscriptions in the target currency (not raw subscription row count).

        Falls back to unique paying customers from last-30-day charges (net of fees)
        when Billing subscriptions are empty (Phoenix / charge-only MIDs).
        """
        target = _norm_currency(currency)
        if not target:
            detected = await self.account_default_currency()
            target = _norm_currency(detected)

        subs = await self.list_active_subscriptions()
        if subs:
            total = Decimal("0")
            customers: set[str] = set()
            for sub in subs:
                sub_cur = _norm_currency(sub.get("currency"))
                items = ((sub.get("items") or {}).get("data")) or []
                # Resolve currency from subscription or first price
                if not sub_cur and items:
                    price0 = (items[0].get("price") or {}) if items else {}
                    sub_cur = _norm_currency(price0.get("currency"))
                if target and sub_cur and sub_cur != target:
                    continue

                cust_key = self._customer_key(sub)
                if not cust_key:
                    # Still count subscription if no customer id (rare)
                    cust_key = f"sub:{sub.get('id')}"
                customers.add(cust_key)

                for item in items:
                    qty = Decimal(str(item.get("quantity") or 1))
                    price = item.get("price") or {}
                    item_cur = _norm_currency(price.get("currency")) or sub_cur
                    if target and item_cur and item_cur != target:
                        continue
                    unit = from_stripe_amount(price.get("unit_amount") or 0, item_cur)
                    recurring = price.get("recurring") or {}
                    interval = recurring.get("interval") or "month"
                    interval_count = int(recurring.get("interval_count") or 1)
                    total += _interval_to_monthly_factor(unit * qty, interval, interval_count)

            return total, len(customers), (target.upper() if target else None)

        # Charge-only MID fallback: trailing 30d net + unique customers
        until_ts = int(time.time())
        since_ts = until_ts - 30 * 24 * 3600
        totals = await self.period_charge_totals(
            since_ts=since_ts, until_ts=until_ts, currency=target or None
        )
        used = totals.get("currency")
        used_str = str(used).upper() if used else (target.upper() if target else None)
        return (
            Decimal(str(totals["net"])),
            int(totals["unique_sources"] or 0),
            used_str,
        )
