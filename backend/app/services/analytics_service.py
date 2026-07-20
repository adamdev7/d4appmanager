"""Unified Shopify + Meta Ads analytics for e-commerce profitability."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import ProductCost, Store, StoreAnalyticsSettings, StoreStatus, User
from app.integrations.meta.client import (
    MetaAdsClient,
    parse_meta_purchase_value,
    parse_meta_purchases,
)
from app.integrations.shopify.client import ShopifyClient
from app.tracking.credentials import mask_api_key_hint


def _d(value: float | str | int | None) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except Exception:
        return Decimal("0")


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return float((numerator / denominator * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _iso_date(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.strftime("%Y-%m-%d")


def get_or_create_analytics_settings(db: Session, store_id: str) -> StoreAnalyticsSettings:
    row = db.scalar(
        select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == store_id)
    )
    if row:
        return row
    row = StoreAnalyticsSettings(store_id=store_id)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


class AnalyticsService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def _shopify_client(self, store: Store) -> ShopifyClient:
        if store.status != StoreStatus.CONNECTED.value or not store.access_token_encrypted:
            raise HTTPException(
                status_code=400,
                detail="Connect your Shopify store in Settings → Stores first.",
            )
        try:
            token = decrypt_value(store.access_token_encrypted)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Could not read Shopify credentials") from e
        return ShopifyClient(store.shop_domain, token)

    def _meta_client(self, settings: StoreAnalyticsSettings) -> MetaAdsClient | None:
        if not settings.meta_access_token_encrypted or not settings.meta_ad_account_id:
            return None
        try:
            token = decrypt_value(settings.meta_access_token_encrypted)
        except ValueError:
            return None
        return MetaAdsClient(token, settings.meta_ad_account_id)

    def _masked_hint(self, hint: str | None, configured: bool) -> str | None:
        if not configured:
            return None
        return f"••••{hint}" if hint else "••••••••"

    def get_settings(self, db: Session, user: User, store_id: str) -> dict:
        store = self._ensure_store(db, user, store_id)
        row = get_or_create_analytics_settings(db, store_id)
        meta_configured = bool(row.meta_access_token_encrypted and row.meta_ad_account_id)
        return {
            "store_id": store_id,
            "store_name": store.name,
            "shop_domain": store.shop_domain,
            "currency": store.currency,
            "shopify_connected": store.status == StoreStatus.CONNECTED.value,
            "meta_configured": meta_configured,
            "meta_token_masked": self._masked_hint(row.meta_access_token_hint, bool(row.meta_access_token_encrypted)),
            "meta_ad_account_id": row.meta_ad_account_id,
            "default_shipping_cost": float(_d(row.default_shipping_cost)),
            "transaction_fee_percent": float(_d(row.transaction_fee_percent)),
            "transaction_fee_fixed": float(_d(row.transaction_fee_fixed)),
        }

    def update_settings(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self._ensure_store(db, user, store_id)
        row = get_or_create_analytics_settings(db, store_id)

        if body.get("meta_access_token") is not None:
            token = str(body["meta_access_token"]).strip()
            if token:
                row.meta_access_token_encrypted = encrypt_value(token)
                row.meta_access_token_hint = mask_api_key_hint(token)
            else:
                row.meta_access_token_encrypted = None
                row.meta_access_token_hint = None

        if body.get("meta_ad_account_id") is not None:
            account = str(body["meta_ad_account_id"]).strip().replace("act_", "")
            row.meta_ad_account_id = account or None

        if body.get("default_shipping_cost") is not None:
            row.default_shipping_cost = str(body["default_shipping_cost"])

        if body.get("transaction_fee_percent") is not None:
            row.transaction_fee_percent = str(body["transaction_fee_percent"])

        if body.get("transaction_fee_fixed") is not None:
            row.transaction_fee_fixed = str(body["transaction_fee_fixed"])

        db.commit()
        return self.get_settings(db, user, store_id)

    async def test_meta_connection(
        self, db: Session, user: User, store_id: str, body: dict
    ) -> dict:
        self._ensure_store(db, user, store_id)
        row = get_or_create_analytics_settings(db, store_id)

        token = str(body.get("meta_access_token") or "").strip()
        account_id = str(body.get("meta_ad_account_id") or row.meta_ad_account_id or "").strip()

        if not token and row.meta_access_token_encrypted:
            token = decrypt_value(row.meta_access_token_encrypted)
        if not token:
            raise HTTPException(status_code=400, detail="Enter a Meta access token")
        if not account_id:
            raise HTTPException(status_code=400, detail="Enter your Meta ad account ID")

        client = MetaAdsClient(token, account_id)
        ok, message, name = await client.test_connection()
        return {"ok": ok, "message": message, "account_name": name}

    async def get_products(self, db: Session, user: User, store_id: str) -> dict:
        store = self._ensure_store(db, user, store_id)
        client = self._shopify_client(store)

        try:
            products = await client.list_products()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Could not fetch Shopify products: {e}") from e

        saved = {
            (r.shopify_product_id, r.shopify_variant_id): r
            for r in db.scalars(select(ProductCost).where(ProductCost.store_id == store_id)).all()
        }

        items: list[dict] = []
        for product in products:
            product_id = str(product.get("id", ""))
            image = (product.get("image") or {}).get("src")
            if not image and product.get("images"):
                image = product["images"][0].get("src")
            for variant in product.get("variants") or []:
                variant_id = str(variant.get("id", ""))
                key = (product_id, variant_id)
                saved_row = saved.get(key)
                items.append(
                    {
                        "shopify_product_id": product_id,
                        "shopify_variant_id": variant_id,
                        "product_title": product.get("title") or "",
                        "variant_title": variant.get("title") or "Default",
                        "image_url": image,
                        "shopify_price": variant.get("price") or "0",
                        "cost_per_unit": float(_d(saved_row.cost_per_unit if saved_row else "0")),
                        "sku": variant.get("sku") or "",
                    }
                )

        missing_costs = sum(1 for i in items if i["cost_per_unit"] <= 0)
        return {
            "store_id": store_id,
            "currency": store.currency,
            "products": items,
            "total_variants": len(items),
            "missing_costs": missing_costs,
        }

    def update_product_costs(self, db: Session, user: User, store_id: str, items: list[dict]) -> dict:
        self._ensure_store(db, user, store_id)
        existing = {
            (r.shopify_product_id, r.shopify_variant_id): r
            for r in db.scalars(select(ProductCost).where(ProductCost.store_id == store_id)).all()
        }

        for item in items:
            pid = str(item["shopify_product_id"])
            vid = str(item["shopify_variant_id"])
            cost = str(item.get("cost_per_unit", 0))
            key = (pid, vid)
            if key in existing:
                existing[key].cost_per_unit = cost
            else:
                db.add(
                    ProductCost(
                        store_id=store_id,
                        shopify_product_id=pid,
                        shopify_variant_id=vid,
                        product_title=str(item.get("product_title") or ""),
                        variant_title=str(item.get("variant_title") or ""),
                        image_url=item.get("image_url"),
                        shopify_price=str(item.get("shopify_price") or "0"),
                        cost_per_unit=cost,
                    )
                )
        db.commit()
        return {"ok": True, "updated": len(items)}

    def _parse_range(
        self, period: str, store: Store | None = None
    ) -> tuple[datetime, datetime, str, str]:
        now = datetime.now(UTC)
        end = now.replace(hour=23, minute=59, second=59, microsecond=0)
        if period == "all":
            if store and store.created_at:
                start = store.created_at
                if start.tzinfo is None:
                    start = start.replace(tzinfo=UTC)
            else:
                start = datetime(2010, 1, 1, tzinfo=UTC)
        elif period == "7d":
            start = end - timedelta(days=6)
        elif period == "90d":
            start = end - timedelta(days=89)
        else:
            start = end - timedelta(days=29)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, end, _iso_date(start), _iso_date(end)

    @staticmethod
    def _month_key(day: str) -> str:
        return f"{day[:7]}-01"

    async def get_dashboard(
        self, db: Session, user: User, store_id: str, period: str = "30d"
    ) -> dict:
        store = self._ensure_store(db, user, store_id)
        settings_row = get_or_create_analytics_settings(db, store_id)
        start_dt, end_dt, since, until = self._parse_range(period, store)
        currency = store.currency or "USD"

        cost_map = {
            (r.shopify_product_id, r.shopify_variant_id): _d(r.cost_per_unit)
            for r in db.scalars(select(ProductCost).where(ProductCost.store_id == store_id)).all()
        }
        shipping_per_order = _d(settings_row.default_shipping_cost)
        fee_pct = _d(settings_row.transaction_fee_percent) / Decimal("100")
        fee_fixed = _d(settings_row.transaction_fee_fixed)

        shopify_connected = store.status == StoreStatus.CONNECTED.value
        meta_configured = bool(settings_row.meta_access_token_encrypted and settings_row.meta_ad_account_id)

        # --- Shopify orders ---
        revenue = Decimal("0")
        refunds = Decimal("0")
        order_count = 0
        cogs = Decimal("0")
        shipping_costs = Decimal("0")
        transaction_fees = Decimal("0")
        missing_cost_items = 0
        daily_shopify: dict[str, dict] = defaultdict(lambda: {"revenue": Decimal("0"), "orders": 0})
        product_stats: dict[str, dict] = defaultdict(
            lambda: {"title": "", "units": 0, "revenue": Decimal("0"), "cogs": Decimal("0"), "image": None}
        )
        orders_data: list[dict] = []

        if shopify_connected:
            client = self._shopify_client(store)
            try:
                if period == "all":
                    orders = await client.list_all_orders_in_range(
                        created_at_max=end_dt.isoformat(),
                        max_pages=100,
                    )
                else:
                    orders = await client.list_all_orders_in_range(
                        created_at_min=start_dt.isoformat(),
                        created_at_max=end_dt.isoformat(),
                    )
            except Exception as e:
                raise HTTPException(status_code=502, detail=f"Shopify orders fetch failed: {e}") from e

            for order in orders:
                if order.get("cancelled_at"):
                    continue
                financial = order.get("financial_status") or ""
                if financial in ("refunded", "voided"):
                    continue

                created = order.get("created_at") or ""
                day_key = created[:10] if created else _iso_date(start_dt)
                total = _d(order.get("total_price"))
                revenue += total
                order_count += 1
                daily_shopify[day_key]["revenue"] += total
                daily_shopify[day_key]["orders"] += 1

                order_cogs = Decimal("0")
                for line in order.get("line_items") or []:
                    pid = str(line.get("product_id") or "")
                    vid = str(line.get("variant_id") or "")
                    qty = int(line.get("quantity") or 0)
                    line_rev = _d(line.get("price")) * qty
                    title = line.get("title") or "Product"
                    product_key = f"{pid}:{vid}" if pid else title

                    unit_cost = cost_map.get((pid, vid), Decimal("0"))
                    if unit_cost <= 0 and qty > 0:
                        missing_cost_items += qty
                    line_cogs = unit_cost * qty
                    order_cogs += line_cogs
                    cogs += line_cogs

                    ps = product_stats[product_key]
                    ps["title"] = title
                    ps["units"] += qty
                    ps["revenue"] += line_rev
                    ps["cogs"] += line_cogs

                ship = shipping_per_order
                if order.get("shipping_lines"):
                    ship = sum(_d(s.get("price")) for s in order["shipping_lines"]) or shipping_per_order
                shipping_costs += ship

                fees = total * fee_pct + fee_fixed
                transaction_fees += fees

                orders_data.append(
                    {
                        "order_number": order.get("name") or str(order.get("order_number")),
                        "total": _money(total),
                        "cogs": _money(order_cogs),
                        "profit": _money(total - order_cogs - ship - (total * fee_pct + fee_fixed)),
                        "created_at": created,
                    }
                )

            for refund_batch in orders:
                for refund in refund_batch.get("refunds") or []:
                    for trans in refund.get("transactions") or []:
                        if trans.get("kind") == "refund":
                            refunds += _d(trans.get("amount"))

        if period == "all" and daily_shopify:
            earliest = min(daily_shopify.keys())
            start_dt = datetime.strptime(earliest, "%Y-%m-%d").replace(tzinfo=UTC)
            since = earliest

        # --- Meta Ads ---
        ad_spend = Decimal("0")
        impressions = 0
        clicks = 0
        meta_purchases = 0.0
        meta_purchase_value = Decimal("0")
        daily_meta: dict[str, dict] = defaultdict(lambda: {"spend": Decimal("0"), "purchases": 0})
        campaigns: list[dict] = []
        meta_error: str | None = None

        meta_client = self._meta_client(settings_row)
        if meta_client:
            try:
                if period == "all":
                    account_insights = await meta_client.get_account_insights(
                        date_preset="maximum", time_increment=1
                    )
                else:
                    account_insights = await meta_client.get_account_insights(
                        since=since, until=until, time_increment=1
                    )
                for row in account_insights.get("data") or []:
                    day = row.get("date_start") or ""
                    spend = _d(row.get("spend"))
                    ad_spend += spend
                    impressions += int(row.get("impressions") or 0)
                    clicks += int(row.get("clicks") or 0)
                    purchases = parse_meta_purchases(row.get("actions"))
                    meta_purchases += purchases
                    meta_purchase_value += _d(parse_meta_purchase_value(row.get("action_values")))
                    daily_meta[day]["spend"] += spend
                    daily_meta[day]["purchases"] += int(purchases)

                if period == "all":
                    campaign_rows = await meta_client.get_campaign_insights(date_preset="maximum")
                else:
                    campaign_rows = await meta_client.get_campaign_insights(since=since, until=until)
                for row in campaign_rows:
                    spend = _d(row.get("spend"))
                    purchases = parse_meta_purchases(row.get("actions"))
                    purchase_val = _d(parse_meta_purchase_value(row.get("action_values")))
                    campaigns.append(
                        {
                            "campaign_id": row.get("campaign_id"),
                            "campaign_name": row.get("campaign_name") or "Unknown",
                            "spend": _money(spend),
                            "impressions": int(row.get("impressions") or 0),
                            "clicks": int(row.get("clicks") or 0),
                            "ctr": float(row.get("ctr") or 0),
                            "cpc": _money(_d(row.get("cpc"))),
                            "purchases": int(purchases),
                            "purchase_value": _money(purchase_val),
                            "roas": _money(purchase_val / spend) if spend > 0 else 0,
                            "cpa": _money(spend / _d(purchases)) if purchases > 0 else 0,
                        }
                    )
                campaigns.sort(key=lambda c: c["spend"], reverse=True)
            except Exception as e:
                meta_error = str(e)
        elif meta_configured:
            meta_error = "Could not decrypt Meta credentials — re-save your access token."

        # --- Blended metrics ---
        gross_profit = revenue - cogs - shipping_costs - transaction_fees
        net_profit = gross_profit - ad_spend
        mer = _money(revenue / ad_spend) if ad_spend > 0 else 0
        roas = mer
        cpa = _money(ad_spend / _d(order_count)) if order_count > 0 and ad_spend > 0 else 0
        aov = _money(revenue / _d(order_count)) if order_count > 0 else 0
        margin_before_ads = _pct(gross_profit, revenue)
        net_margin = _pct(net_profit, revenue)
        break_even_roas = _money(revenue / gross_profit) if gross_profit > 0 else 0

        # Daily / monthly chart series
        use_monthly = period == "all" or (end_dt.date() - start_dt.date()).days > 90
        chart_keys: list[str] = []
        if use_monthly:
            cursor = start_dt.replace(day=1)
            while cursor.date() <= end_dt.date():
                chart_keys.append(self._month_key(_iso_date(cursor)))
                if cursor.month == 12:
                    cursor = cursor.replace(year=cursor.year + 1, month=1)
                else:
                    cursor = cursor.replace(month=cursor.month + 1)
        else:
            cursor = start_dt
            while cursor.date() <= end_dt.date():
                chart_keys.append(_iso_date(cursor))
                cursor += timedelta(days=1)

        daily_chart = []
        for key in chart_keys:
            if use_monthly:
                s = {"revenue": Decimal("0"), "orders": 0}
                m = {"spend": Decimal("0"), "purchases": 0}
                month_prefix = key[:7]
                for day, vals in daily_shopify.items():
                    if day.startswith(month_prefix):
                        s["revenue"] += vals["revenue"]
                        s["orders"] += vals["orders"]
                for day, vals in daily_meta.items():
                    if day.startswith(month_prefix):
                        m["spend"] += vals["spend"]
                        m["purchases"] += vals["purchases"]
            else:
                s = daily_shopify.get(key, {"revenue": Decimal("0"), "orders": 0})
                m = daily_meta.get(key, {"spend": Decimal("0"), "purchases": 0})
            day_rev = s["revenue"]
            day_spend = m["spend"]
            day_gross = day_rev - (day_rev * fee_pct) - shipping_per_order * s["orders"]
            daily_chart.append(
                {
                    "date": key,
                    "revenue": _money(day_rev),
                    "ad_spend": _money(day_spend),
                    "orders": s["orders"],
                    "profit": _money(day_gross - day_spend),
                }
            )

        top_products = sorted(
            [
                {
                    "title": v["title"],
                    "units_sold": v["units"],
                    "revenue": _money(v["revenue"]),
                    "cogs": _money(v["cogs"]),
                    "profit": _money(v["revenue"] - v["cogs"]),
                    "margin_pct": _pct(v["revenue"] - v["cogs"], v["revenue"]),
                }
                for v in product_stats.values()
                if v["units"] > 0
            ],
            key=lambda p: p["revenue"],
            reverse=True,
        )[:10]

        insights: list[dict] = []
        if not shopify_connected:
            insights.append(
                {
                    "level": "warning",
                    "title": "Connect Shopify",
                    "message": "Link your store to see revenue, orders, and product profitability.",
                }
            )
        if not meta_configured:
            insights.append(
                {
                    "level": "info",
                    "title": "Add Meta Ads credentials",
                    "message": "Connect Meta to track ad spend, ROAS, and blended profit in one view.",
                }
            )
        if missing_cost_items > 0:
            insights.append(
                {
                    "level": "warning",
                    "title": f"{missing_cost_items} items missing product cost",
                    "message": "Enter your product costs in the Products tab for accurate profit numbers.",
                }
            )
        if ad_spend > 0 and break_even_roas > 0 and roas < break_even_roas:
            insights.append(
                {
                    "level": "danger",
                    "title": "ROAS below break-even",
                    "message": f"Current ROAS ({roas}x) is below your break-even ({break_even_roas}x). "
                    "Review campaigns or improve margins.",
                }
            )
        elif net_profit > 0 and ad_spend > 0:
            insights.append(
                {
                    "level": "success",
                    "title": "Profitable period",
                    "message": f"Net profit of {currency} {_money(net_profit)} after ad spend this period.",
                }
            )
        if campaigns:
            best = max(campaigns, key=lambda c: c["roas"] if c["spend"] > 10 else 0)
            if best["roas"] > 0:
                insights.append(
                    {
                        "level": "success",
                        "title": "Top campaign",
                        "message": f"'{best['campaign_name']}' has {best['roas']}x ROAS — consider scaling.",
                    }
                )

        return {
            "store_id": store_id,
            "store_name": store.name,
            "currency": currency,
            "period": period,
            "chart_granularity": "monthly" if use_monthly else "daily",
            "date_range": {"since": since, "until": until},
            "connections": {
                "shopify": shopify_connected,
                "meta": meta_configured and meta_error is None,
                "meta_error": meta_error,
            },
            "summary": {
                "revenue": _money(revenue),
                "refunds": _money(refunds),
                "orders": order_count,
                "aov": aov,
                "cogs": _money(cogs),
                "shipping_costs": _money(shipping_costs),
                "transaction_fees": _money(transaction_fees),
                "gross_profit": _money(gross_profit),
                "ad_spend": _money(ad_spend),
                "net_profit": _money(net_profit),
                "mer": mer,
                "roas": roas,
                "cpa": cpa,
                "ctr": _pct(_d(clicks), _d(impressions)),
                "cpc": _money(ad_spend / _d(clicks)) if clicks > 0 else 0,
                "impressions": impressions,
                "clicks": clicks,
                "meta_purchases": int(meta_purchases),
                "meta_purchase_value": _money(meta_purchase_value),
                "margin_before_ads_pct": margin_before_ads,
                "net_margin_pct": net_margin,
                "break_even_roas": break_even_roas,
            },
            "daily_chart": daily_chart,
            "campaigns": campaigns[:15],
            "top_products": top_products,
            "recent_orders": sorted(orders_data, key=lambda o: o["created_at"] or "", reverse=True)[:8],
            "insights": insights,
        }
