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

    @staticmethod
    def _empty_money_bucket() -> dict[str, Any]:
        return {
            "gross": Decimal("0"),
            "fees": Decimal("0"),
            "net": Decimal("0"),
            "refunds": Decimal("0"),
            "subscription_gross": Decimal("0"),
            "one_time_gross": Decimal("0"),
            "subscription_net": Decimal("0"),
            "one_time_net": Decimal("0"),
            "charge_count": 0,
            "subscription_count": 0,
            "one_time_count": 0,
            "refund_count": 0,
            "customers": set(),
            "daily_net": defaultdict(lambda: Decimal("0")),
            "daily_gross": defaultdict(lambda: Decimal("0")),
            "daily_fees": defaultdict(lambda: Decimal("0")),
            "daily_subscription_net": defaultdict(lambda: Decimal("0")),
            "daily_one_time_net": defaultdict(lambda: Decimal("0")),
        }

    async def period_charge_totals(
        self,
        *,
        since_ts: int,
        until_ts: int,
        currency: str | None = None,
        limit_pages: int = 200,
    ) -> dict[str, Any]:
        """
        Period revenue from Stripe in **settlement currency** (balance_transaction).

        Charge presentment may be GBP/USD while the account settles to CAD — gross,
        fees, and net are always taken from the balance transaction so they share one
        currency. Refunds in the window are applied from their own settlement BTs.
        """
        preferred = _norm_currency(currency)
        buckets: dict[str, dict[str, Any]] = defaultdict(self._empty_money_bucket)
        settlement_counts: dict[str, int] = defaultdict(int)
        presentment_counts: dict[str, int] = defaultdict(int)
        # charge_id → settlement currency / whether subscription (for refund attribution)
        charge_meta: dict[str, dict[str, Any]] = {}

        async with httpx.AsyncClient(timeout=120) as client:
            starting_after: str | None = None
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

                    presentment = _norm_currency(ch.get("currency"))
                    if presentment:
                        presentment_counts[presentment] += 1

                    created = int(ch.get("created") or since_ts)
                    day_key = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d")
                    is_subscription = bool(ch.get("invoice"))
                    bt = ch.get("balance_transaction")

                    if isinstance(bt, dict):
                        settle_cur = _norm_currency(bt.get("currency")) or presentment
                        gross = from_stripe_amount(bt.get("amount"), settle_cur)
                        fee = from_stripe_amount(bt.get("fee"), settle_cur)
                        net = from_stripe_amount(bt.get("net"), settle_cur)
                    else:
                        # No BT yet (rare) — keep presentment amounts consistent
                        settle_cur = presentment
                        if not settle_cur:
                            continue
                        amt = from_stripe_amount(ch.get("amount"), settle_cur)
                        refunded = from_stripe_amount(ch.get("amount_refunded"), settle_cur)
                        gross = amt - refunded
                        fee = Decimal("0")
                        net = gross

                    if not settle_cur:
                        continue

                    settlement_counts[settle_cur] += 1
                    charge_id = str(ch.get("id") or "")
                    if charge_id:
                        charge_meta[charge_id] = {
                            "settle_cur": settle_cur,
                            "is_subscription": is_subscription,
                        }

                    b = buckets[settle_cur]
                    b["gross"] += gross
                    b["fees"] += fee
                    b["net"] += net
                    b["daily_net"][day_key] += net
                    b["daily_gross"][day_key] += gross
                    b["daily_fees"][day_key] += fee
                    if is_subscription:
                        b["subscription_gross"] += gross
                        b["subscription_net"] += net
                        b["daily_subscription_net"][day_key] += net
                        b["subscription_count"] += 1
                    else:
                        b["one_time_gross"] += gross
                        b["one_time_net"] += net
                        b["daily_one_time_net"][day_key] += net
                        b["one_time_count"] += 1
                    if gross > 0 or net != 0:
                        b["charge_count"] += 1
                    cust_key = self._customer_key(ch)
                    if cust_key:
                        b["customers"].add(cust_key)

                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break

            # Refunds post separate settlement BTs — subtract them so net matches Stripe.
            starting_after = None
            for _ in range(limit_pages):
                params = [
                    ("limit", 100),
                    ("created[gte]", int(since_ts)),
                    ("created[lte]", int(until_ts)),
                    ("expand[]", "data.balance_transaction"),
                    ("expand[]", "data.charge"),
                ]
                if starting_after:
                    params.append(("starting_after", starting_after))
                resp = await client.get(
                    f"{STRIPE_API_BASE}/refunds",
                    params=params,
                    auth=(self.secret_key, ""),
                )
                if resp.status_code == 403:
                    break
                resp.raise_for_status()
                payload = resp.json()
                batch = list(payload.get("data") or [])
                for rf in batch:
                    status = (rf.get("status") or "").lower()
                    if status not in ("succeeded", "pending"):
                        continue
                    bt = rf.get("balance_transaction")
                    created = int(rf.get("created") or since_ts)
                    day_key = datetime.utcfromtimestamp(created).strftime("%Y-%m-%d")

                    charge_ref = rf.get("charge")
                    charge_id = (
                        charge_ref.get("id")
                        if isinstance(charge_ref, dict)
                        else (str(charge_ref) if charge_ref else "")
                    )
                    meta = charge_meta.get(charge_id) or {}
                    is_subscription = bool(meta.get("is_subscription"))

                    if isinstance(bt, dict):
                        settle_cur = _norm_currency(bt.get("currency")) or meta.get(
                            "settle_cur"
                        )
                        # Refund BT amount/net are typically negative
                        gross_delta = from_stripe_amount(bt.get("amount"), settle_cur)
                        fee_delta = from_stripe_amount(bt.get("fee"), settle_cur)
                        net_delta = from_stripe_amount(bt.get("net"), settle_cur)
                        refund_abs = abs(gross_delta)
                    else:
                        settle_cur = _norm_currency(rf.get("currency")) or meta.get(
                            "settle_cur"
                        )
                        if not settle_cur:
                            continue
                        refund_abs = from_stripe_amount(rf.get("amount"), settle_cur)
                        gross_delta = -refund_abs
                        fee_delta = Decimal("0")
                        net_delta = -refund_abs

                    if not settle_cur:
                        continue

                    settlement_counts[settle_cur] += 1
                    b = buckets[settle_cur]
                    b["gross"] += gross_delta
                    b["fees"] += fee_delta
                    b["net"] += net_delta
                    b["refunds"] += refund_abs
                    b["refund_count"] += 1
                    b["daily_net"][day_key] += net_delta
                    b["daily_gross"][day_key] += gross_delta
                    b["daily_fees"][day_key] += fee_delta
                    if is_subscription:
                        b["subscription_gross"] += gross_delta
                        b["subscription_net"] += net_delta
                        b["daily_subscription_net"][day_key] += net_delta
                    else:
                        b["one_time_gross"] += gross_delta
                        b["one_time_net"] += net_delta
                        b["daily_one_time_net"][day_key] += net_delta

                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break

        chosen = _pick_majority_currency(dict(settlement_counts), preferred)
        if not chosen:
            chosen = await self.account_default_currency()
        cur_key = _norm_currency(chosen)
        b = buckets.get(cur_key) or self._empty_money_bucket()

        # If preferred settlement (e.g. CAD) has volume, use it; otherwise sum all
        # settlement buckets that match chosen. When multiple settlement currencies
        # exist, prefer the preferred/store currency bucket only.
        if preferred and preferred in buckets and buckets[preferred]["charge_count"] > 0:
            cur_key = preferred
            b = buckets[preferred]
            chosen = preferred.upper()

        def _plain(d: Any) -> dict[str, str]:
            if not d:
                return {}
            return {k: str(v) for k, v in dict(d).items()}

        return {
            "gross": b["gross"],
            "fees": b["fees"],
            "net": b["net"],
            "refunds": b["refunds"],
            "subscription_gross": b["subscription_gross"],
            "one_time_gross": b["one_time_gross"],
            "subscription_net": b["subscription_net"],
            "one_time_net": b["one_time_net"],
            "charge_count": int(b["charge_count"]),
            "subscription_count": int(b["subscription_count"]),
            "one_time_count": int(b["one_time_count"]),
            "refund_count": int(b["refund_count"]),
            "unique_sources": len(b["customers"]),
            "currency": (chosen.upper() if chosen else None),
            "settlement_currency": (chosen.upper() if chosen else None),
            "currencies_seen": ",".join(sorted(c.upper() for c in presentment_counts)),
            "settlement_currencies_seen": ",".join(
                sorted(c.upper() for c in settlement_counts)
            ),
            "daily_net": _plain(b.get("daily_net")),
            "daily_gross": _plain(b.get("daily_gross")),
            "daily_fees": _plain(b.get("daily_fees")),
            "daily_subscription_net": _plain(b.get("daily_subscription_net")),
            "daily_one_time_net": _plain(b.get("daily_one_time_net")),
        }

    async def period_dispute_stats(
        self,
        *,
        since_ts: int,
        until_ts: int,
        limit_pages: int = 50,
    ) -> dict[str, Any]:
        """Chargeback / dispute stats for the period (amounts in dispute currency)."""
        open_statuses = frozenset(
            {
                "warning_needs_response",
                "warning_under_review",
                "needs_response",
                "under_review",
            }
        )
        stats: dict[str, Any] = {
            "count": 0,
            "open_count": 0,
            "won_count": 0,
            "lost_count": 0,
            "amount": Decimal("0"),
            "open_amount": Decimal("0"),
            "won_amount": Decimal("0"),
            "lost_amount": Decimal("0"),
            "currency": None,
            "currency_counts": defaultdict(int),
            "reasons": defaultdict(int),
        }
        starting_after: str | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            for _ in range(limit_pages):
                params: list[tuple[str, str | int]] = [
                    ("limit", 100),
                    ("created[gte]", int(since_ts)),
                    ("created[lte]", int(until_ts)),
                ]
                if starting_after:
                    params.append(("starting_after", starting_after))
                resp = await client.get(
                    f"{STRIPE_API_BASE}/disputes",
                    params=params,
                    auth=(self.secret_key, ""),
                )
                if resp.status_code == 403:
                    stats["error"] = "Stripe key lacks disputes read permission"
                    break
                resp.raise_for_status()
                payload = resp.json()
                batch = list(payload.get("data") or [])
                for d in batch:
                    cur = _norm_currency(d.get("currency"))
                    if not cur:
                        continue
                    amt = from_stripe_amount(d.get("amount"), cur)
                    status = (d.get("status") or "").lower()
                    reason = (d.get("reason") or "unknown").lower()
                    stats["count"] += 1
                    stats["amount"] += amt
                    stats["currency_counts"][cur] += 1
                    stats["reasons"][reason] += 1
                    if status in open_statuses:
                        stats["open_count"] += 1
                        stats["open_amount"] += amt
                    elif status == "won":
                        stats["won_count"] += 1
                        stats["won_amount"] += amt
                    elif status in ("lost", "charge_refunded"):
                        stats["lost_count"] += 1
                        stats["lost_amount"] += amt
                if not payload.get("has_more") or not batch:
                    break
                starting_after = batch[-1].get("id")
                if not starting_after:
                    break

        chosen = _pick_majority_currency(dict(stats["currency_counts"]))
        stats["currency"] = chosen
        stats["reasons"] = dict(stats["reasons"])
        stats["currency_counts"] = {
            k.upper(): v for k, v in dict(stats["currency_counts"]).items()
        }
        return stats

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
