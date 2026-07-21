"""Stripe API helpers for multi-MID subscription / MRR aggregation."""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
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


def _pick_majority_currency(counts: dict[str, int], preferred: str | None = None) -> str | None:
    """Pick the currency with the most volume; prefer `preferred` only if it has data."""
    pref = _norm_currency(preferred)
    if pref and counts.get(pref, 0) > 0:
        return pref.upper()
    if not counts:
        return pref.upper() if pref else None
    best = max(counts.items(), key=lambda kv: kv[1])[0]
    return best.upper()


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
            acct_currency = None
            for bucket in ("available", "pending"):
                rows = data.get(bucket) or []
                if rows and isinstance(rows, list):
                    acct_currency = (rows[0].get("currency") or "").upper() or None
                    if acct_currency:
                        break
            return True, "Stripe key works", acct_currency

    async def account_default_currency(self) -> str | None:
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

    @staticmethod
    def _customer_key(obj: dict) -> str | None:
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

    @staticmethod
    def _sub_currency(sub: dict) -> str:
        cur = _norm_currency(sub.get("currency"))
        if cur:
            return cur
        items = ((sub.get("items") or {}).get("data")) or []
        for item in items:
            price = item.get("price") or {}
            cur = _norm_currency(price.get("currency"))
            if cur:
                return cur
        return ""

    async def period_charge_totals(
        self,
        *,
        since_ts: int,
        until_ts: int,
        currency: str | None = None,
        limit_pages: int = 100,
    ) -> dict[str, Any]:
        """
        Total Stripe revenue for a period = ALL successful charges (subscriptions + one-time).

        Returns native-currency totals plus `daily` maps (YYYY-MM-DD → amount) so callers
        can convert to store currency with historical per-day FX rates.
        """
        preferred = _norm_currency(currency)
        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "gross": Decimal("0"),
                "fees": Decimal("0"),
                "net": Decimal("0"),
                "subscription_gross": Decimal("0"),
                "one_time_gross": Decimal("0"),
                "subscription_net": Decimal("0"),
                "one_time_net": Decimal("0"),
                "charge_count": 0,
                "subscription_count": 0,
                "one_time_count": 0,
                "customers": set(),
                "daily_net": defaultdict(lambda: Decimal("0")),
                "daily_gross": defaultdict(lambda: Decimal("0")),
                "daily_fees": defaultdict(lambda: Decimal("0")),
                "daily_subscription_net": defaultdict(lambda: Decimal("0")),
                "daily_one_time_net": defaultdict(lambda: Decimal("0")),
            }
        )
        currency_counts: dict[str, int] = defaultdict(int)
        starting_after: str | None = None

        async with httpx.AsyncClient(timeout=120) as client:
            for _ in range(limit_pages):
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
                    if ch.get("captured") is False:
                        continue

                    cur = _norm_currency(ch.get("currency"))
                    if not cur:
                        continue
                    currency_counts[cur] += 1

                    created = int(ch.get("created") or since_ts)
                    day_key = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d")

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

                    is_subscription = bool(ch.get("invoice"))
                    b = buckets[cur]
                    b["gross"] += effective_gross
                    b["fees"] += fee
                    b["net"] += n
                    b["daily_net"][day_key] += n
                    b["daily_gross"][day_key] += effective_gross
                    b["daily_fees"][day_key] += fee
                    if is_subscription:
                        b["subscription_gross"] += effective_gross
                        b["subscription_net"] += n
                        b["daily_subscription_net"][day_key] += n
                        if effective_gross > 0:
                            b["subscription_count"] += 1
                    else:
                        b["one_time_gross"] += effective_gross
                        b["one_time_net"] += n
                        b["daily_one_time_net"][day_key] += n
                        if effective_gross > 0:
                            b["one_time_count"] += 1
                    if ch.get("paid") and effective_gross > 0:
                        b["charge_count"] += 1
                    cust_key = self._customer_key(ch)
                    if cust_key:
                        b["customers"].add(cust_key)

                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break

        chosen = _pick_majority_currency(dict(currency_counts), preferred)
        if not chosen:
            acct = await self.account_default_currency()
            chosen = acct
        cur_key = _norm_currency(chosen)
        empty_b = {
            "gross": Decimal("0"),
            "fees": Decimal("0"),
            "net": Decimal("0"),
            "subscription_gross": Decimal("0"),
            "one_time_gross": Decimal("0"),
            "subscription_net": Decimal("0"),
            "one_time_net": Decimal("0"),
            "charge_count": 0,
            "subscription_count": 0,
            "one_time_count": 0,
            "customers": set(),
            "daily_net": {},
            "daily_gross": {},
            "daily_fees": {},
            "daily_subscription_net": {},
            "daily_one_time_net": {},
        }
        b = buckets.get(cur_key) or empty_b

        def _plain(d: Any) -> dict[str, str]:
            if not d:
                return {}
            return {k: str(v) for k, v in dict(d).items()}

        return {
            "gross": b["gross"],
            "fees": b["fees"],
            "net": b["net"],
            "subscription_gross": b["subscription_gross"],
            "one_time_gross": b["one_time_gross"],
            "subscription_net": b["subscription_net"],
            "one_time_net": b["one_time_net"],
            "charge_count": int(b["charge_count"]),
            "subscription_count": int(b["subscription_count"]),
            "one_time_count": int(b["one_time_count"]),
            "unique_sources": len(b["customers"]),
            "currency": chosen.upper() if chosen else None,
            "currencies_seen": ",".join(sorted(c.upper() for c in currency_counts)),
            "daily_net": _plain(b.get("daily_net")),
            "daily_gross": _plain(b.get("daily_gross")),
            "daily_fees": _plain(b.get("daily_fees")),
            "daily_subscription_net": _plain(b.get("daily_subscription_net")),
            "daily_one_time_net": _plain(b.get("daily_one_time_net")),
        }

    async def compute_mrr(
        self, *, currency: str | None = None
    ) -> tuple[Decimal, int, str | None]:
        """
        Return (monthly_mrr, unique_subscriber_count, currency_used).

        Currency always comes from Stripe subscription/charge data (e.g. GBP),
        never relabeled as the Shopify store currency.
        """
        preferred = _norm_currency(currency)
        subs = await self.list_active_subscriptions()

        if subs:
            # First pass: detect majority subscription currency from Stripe
            cur_counts: dict[str, int] = defaultdict(int)
            for sub in subs:
                cur = self._sub_currency(sub)
                if cur:
                    cur_counts[cur] += 1
            chosen = _pick_majority_currency(dict(cur_counts), preferred)
            if not chosen:
                chosen = await self.account_default_currency()
            target = _norm_currency(chosen)

            total = Decimal("0")
            customers: set[str] = set()
            for sub in subs:
                sub_cur = self._sub_currency(sub)
                if target and sub_cur and sub_cur != target:
                    continue
                if target and not sub_cur:
                    # Missing currency — only include if we have no target yet
                    continue

                cust_key = self._customer_key(sub) or f"sub:{sub.get('id')}"
                customers.add(cust_key)

                items = ((sub.get("items") or {}).get("data")) or []
                for item in items:
                    qty = Decimal(str(item.get("quantity") or 1))
                    price = item.get("price") or {}
                    item_cur = _norm_currency(price.get("currency")) or sub_cur or target
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
            since_ts=since_ts, until_ts=until_ts, currency=preferred or None
        )
        used = totals.get("currency")
        used_str = str(used).upper() if used else None
        return Decimal(str(totals["net"])), int(totals["unique_sources"] or 0), used_str
