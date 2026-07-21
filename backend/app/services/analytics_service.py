"""Unified Shopify + Meta Ads analytics for e-commerce profitability."""

from __future__ import annotations

import secrets
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import (
    AnalyticsStripeAccount,
    MrrSnapshot,
    ProductCost,
    Store,
    StoreAnalyticsSettings,
    StoreStatus,
    User,
)
from app.integrations.meta.client import (
    MetaAdsClient,
    parse_meta_funnel,
    parse_meta_purchase_roas,
    parse_meta_purchase_value,
    parse_meta_purchases,
)
from app.integrations.shopify.client import ShopifyClient
from app.integrations.stripe.client import StripeClient
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
            "analytics_start_date": row.analytics_start_date,
            "prior_external_revenue": float(_d(row.prior_external_revenue)),
            "prior_external_costs": float(_d(row.prior_external_costs)),
            "prior_external_label": row.prior_external_label or "Prior site (Stripe)",
            "mrr_enabled": bool(row.mrr_enabled),
            "mrr_source": row.mrr_source or "manual",
            "mrr_manual_amount": float(_d(row.mrr_manual_amount)),
            "mrr_manual_subscribers": int(row.mrr_manual_subscribers or 0),
            "mrr_manual_churn_pct": float(_d(row.mrr_manual_churn_pct)),
            "mrr_webhook_configured": bool(row.mrr_webhook_secret_encrypted),
            "mrr_webhook_secret_masked": self._masked_hint(
                row.mrr_webhook_secret_hint, bool(row.mrr_webhook_secret_encrypted)
            ),
            "mrr_webhook_secret": None,  # only returned once on regenerate
            "mrr_last_synced_at": row.mrr_last_synced_at.isoformat() if row.mrr_last_synced_at else None,
            "stripe_accounts": self._list_stripe_accounts(db, store_id),
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

        if "analytics_start_date" in body:
            raw = body.get("analytics_start_date")
            if raw is None or str(raw).strip() == "":
                row.analytics_start_date = None
            else:
                day = str(raw).strip()[:10]
                try:
                    datetime.strptime(day, "%Y-%m-%d")
                except ValueError as e:
                    raise HTTPException(
                        status_code=400, detail="analytics_start_date must be YYYY-MM-DD"
                    ) from e
                row.analytics_start_date = day

        if body.get("prior_external_revenue") is not None:
            row.prior_external_revenue = str(body["prior_external_revenue"])

        if body.get("prior_external_costs") is not None:
            row.prior_external_costs = str(body["prior_external_costs"])

        if body.get("prior_external_label") is not None:
            label = str(body["prior_external_label"]).strip()[:64]
            row.prior_external_label = label or "Prior site (Stripe)"

        if body.get("mrr_enabled") is not None:
            row.mrr_enabled = bool(body["mrr_enabled"])

        if body.get("mrr_source") is not None:
            source = str(body["mrr_source"]).strip().lower()
            if source not in ("manual", "multi_stripe"):
                raise HTTPException(status_code=400, detail="mrr_source must be manual or multi_stripe")
            row.mrr_source = source

        if body.get("mrr_manual_amount") is not None:
            row.mrr_manual_amount = str(body["mrr_manual_amount"])

        if body.get("mrr_manual_subscribers") is not None:
            row.mrr_manual_subscribers = int(body["mrr_manual_subscribers"] or 0)

        if body.get("mrr_manual_churn_pct") is not None:
            row.mrr_manual_churn_pct = str(body["mrr_manual_churn_pct"])

        fresh_webhook_secret: str | None = None
        if body.get("regenerate_mrr_webhook_secret") or (
            body.get("mrr_enabled") and not row.mrr_webhook_secret_encrypted
        ):
            fresh_webhook_secret = secrets.token_urlsafe(32)
            row.mrr_webhook_secret_encrypted = encrypt_value(fresh_webhook_secret)
            row.mrr_webhook_secret_hint = mask_api_key_hint(fresh_webhook_secret)

        # Persist a snapshot when manual MRR is saved while enabled
        should_snapshot = bool(row.mrr_enabled) and (
            body.get("mrr_manual_amount") is not None
            or body.get("mrr_manual_subscribers") is not None
            or body.get("mrr_enabled") is True
        )

        db.commit()

        if should_snapshot and (row.mrr_source or "manual") == "manual":
            self._upsert_mrr_snapshot(
                db,
                store_id,
                mrr=_d(row.mrr_manual_amount),
                subscribers=int(row.mrr_manual_subscribers or 0),
                churn_pct=_d(row.mrr_manual_churn_pct),
                source="manual",
            )
            row.mrr_last_synced_at = datetime.now(UTC)
            db.commit()

        settings = self.get_settings(db, user, store_id)
        if fresh_webhook_secret:
            settings["mrr_webhook_secret"] = fresh_webhook_secret
        return settings

    def _list_stripe_accounts(self, db: Session, store_id: str) -> list[dict]:
        rows = db.scalars(
            select(AnalyticsStripeAccount)
            .where(AnalyticsStripeAccount.store_id == store_id)
            .order_by(AnalyticsStripeAccount.created_at.asc())
        ).all()
        return [
            {
                "id": r.id,
                "label": r.label,
                "secret_key_masked": self._masked_hint(r.secret_key_hint, True),
                "is_active": bool(r.is_active),
                "last_error": r.last_error,
                "last_mrr": float(_d(r.last_mrr)),
                "last_subscribers": int(r.last_subscribers or 0),
                "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
            }
            for r in rows
        ]

    def _upsert_mrr_snapshot(
        self,
        db: Session,
        store_id: str,
        *,
        mrr: Decimal,
        subscribers: int,
        churn_pct: Decimal,
        source: str,
        snapshot_date: str | None = None,
        note: str | None = None,
    ) -> None:
        day = snapshot_date or _iso_date(datetime.now(UTC))
        existing = db.scalar(
            select(MrrSnapshot).where(
                MrrSnapshot.store_id == store_id, MrrSnapshot.snapshot_date == day
            )
        )
        if existing:
            existing.mrr = str(mrr)
            existing.subscribers = subscribers
            existing.churn_pct = str(churn_pct)
            existing.source = source
            if note is not None:
                existing.note = note
        else:
            db.add(
                MrrSnapshot(
                    store_id=store_id,
                    snapshot_date=day,
                    mrr=str(mrr),
                    subscribers=subscribers,
                    churn_pct=str(churn_pct),
                    source=source,
                    note=note,
                )
            )
        db.commit()

    async def add_stripe_account(
        self, db: Session, user: User, store_id: str, body: dict
    ) -> dict:
        self._ensure_store(db, user, store_id)
        label = str(body.get("label") or "Stripe").strip()[:128]
        key = str(body.get("secret_key") or "").strip()
        if not key.startswith("sk_"):
            raise HTTPException(
                status_code=400,
                detail="Enter a Stripe secret key (sk_live_… or sk_test_…). Prefer a restricted key with Billing read.",
            )
        client = StripeClient(key)
        ok, message, _ = await client.test_connection()
        if not ok:
            raise HTTPException(status_code=400, detail=message)

        db.add(
            AnalyticsStripeAccount(
                id=str(uuid4()),
                store_id=store_id,
                label=label or "Stripe",
                secret_key_encrypted=encrypt_value(key),
                secret_key_hint=mask_api_key_hint(key),
                is_active=True,
            )
        )
        db.commit()
        return {"ok": True, "accounts": self._list_stripe_accounts(db, store_id)}

    def delete_stripe_account(self, db: Session, user: User, store_id: str, account_id: str) -> dict:
        self._ensure_store(db, user, store_id)
        row = db.get(AnalyticsStripeAccount, account_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=404, detail="Stripe account not found")
        db.delete(row)
        db.commit()
        return {"ok": True, "accounts": self._list_stripe_accounts(db, store_id)}

    async def sync_mrr_from_stripe(self, db: Session, user: User, store_id: str) -> dict:
        self._ensure_store(db, user, store_id)
        settings = get_or_create_analytics_settings(db, store_id)
        accounts = db.scalars(
            select(AnalyticsStripeAccount).where(
                AnalyticsStripeAccount.store_id == store_id,
                AnalyticsStripeAccount.is_active.is_(True),
            )
        ).all()
        if not accounts:
            raise HTTPException(
                status_code=400,
                detail="Add at least one Stripe secret key, or use Manual / Phoenix MRR mode.",
            )

        total_mrr = Decimal("0")
        total_subs = 0
        errors: list[str] = []
        for acct in accounts:
            try:
                key = decrypt_value(acct.secret_key_encrypted)
                client = StripeClient(key)
                mrr, subs = await client.compute_mrr()
                acct.last_mrr = str(mrr)
                acct.last_subscribers = subs
                acct.last_error = None
                acct.last_synced_at = datetime.now(UTC)
                total_mrr += mrr
                total_subs += subs
            except Exception as e:
                acct.last_error = str(e)[:500]
                errors.append(f"{acct.label}: {e}")
        settings.mrr_source = "multi_stripe"
        settings.mrr_enabled = True
        settings.mrr_manual_amount = str(total_mrr)
        settings.mrr_manual_subscribers = total_subs
        settings.mrr_last_synced_at = datetime.now(UTC)
        db.commit()

        self._upsert_mrr_snapshot(
            db,
            store_id,
            mrr=total_mrr,
            subscribers=total_subs,
            churn_pct=_d(settings.mrr_manual_churn_pct),
            source="multi_stripe",
            note=f"Synced from {len(accounts)} Stripe account(s)",
        )
        return {
            "ok": len(errors) == 0,
            "mrr": _money(total_mrr),
            "subscribers": total_subs,
            "errors": errors,
            "accounts": self._list_stripe_accounts(db, store_id),
        }

    def ingest_mrr_webhook(self, db: Session, store_id: str, secret: str, body: dict) -> dict:
        row = get_or_create_analytics_settings(db, store_id)
        if not row.mrr_webhook_secret_encrypted:
            raise HTTPException(status_code=400, detail="MRR webhook not configured")
        try:
            expected = decrypt_value(row.mrr_webhook_secret_encrypted)
        except ValueError as e:
            raise HTTPException(status_code=400, detail="Invalid webhook secret stored") from e
        if not secret or not secrets.compare_digest(secret, expected):
            raise HTTPException(status_code=401, detail="Invalid webhook secret")

        mrr = _d(body.get("mrr"))
        subscribers = int(body.get("subscribers") or 0)
        churn = _d(body.get("churn_pct"))
        day = body.get("snapshot_date")
        if day:
            try:
                datetime.strptime(str(day)[:10], "%Y-%m-%d")
                day = str(day)[:10]
            except ValueError as e:
                raise HTTPException(status_code=400, detail="snapshot_date must be YYYY-MM-DD") from e

        row.mrr_enabled = True
        row.mrr_manual_amount = str(mrr)
        row.mrr_manual_subscribers = subscribers
        row.mrr_manual_churn_pct = str(churn)
        row.mrr_last_synced_at = datetime.now(UTC)
        db.commit()

        self._upsert_mrr_snapshot(
            db,
            store_id,
            mrr=mrr,
            subscribers=subscribers,
            churn_pct=churn,
            source="webhook",
            snapshot_date=day,
            note=body.get("note"),
        )
        return {"ok": True, "mrr": _money(mrr), "subscribers": subscribers}

    def _mrr_block(self, db: Session, store_id: str, settings_row: StoreAnalyticsSettings) -> dict | None:
        if not settings_row.mrr_enabled:
            return None
        mrr = _d(settings_row.mrr_manual_amount)
        subscribers = int(settings_row.mrr_manual_subscribers or 0)
        churn = float(_d(settings_row.mrr_manual_churn_pct))
        arpu = _money(mrr / _d(subscribers)) if subscribers > 0 else 0
        snapshots = db.scalars(
            select(MrrSnapshot)
            .where(MrrSnapshot.store_id == store_id)
            .order_by(MrrSnapshot.snapshot_date.desc())
            .limit(12)
        ).all()
        history = [
            {
                "date": s.snapshot_date,
                "mrr": float(_d(s.mrr)),
                "subscribers": int(s.subscribers or 0),
                "churn_pct": float(_d(s.churn_pct)),
                "source": s.source,
            }
            for s in reversed(snapshots)
        ]
        mrr_delta = 0.0
        if len(history) >= 2:
            mrr_delta = _money(_d(history[-1]["mrr"]) - _d(history[-2]["mrr"]))
        return {
            "enabled": True,
            "source": settings_row.mrr_source or "manual",
            "mrr": _money(mrr),
            "arr": _money(mrr * Decimal("12")),
            "subscribers": subscribers,
            "arpu": arpu,
            "churn_pct": churn,
            "mrr_delta": mrr_delta,
            "last_synced_at": (
                settings_row.mrr_last_synced_at.isoformat() if settings_row.mrr_last_synced_at else None
            ),
            "history": history,
            "stripe_account_count": len(self._list_stripe_accounts(db, store_id)),
        }

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
        self, period: str, store: Store | None = None, analytics_start: str | None = None
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

        # Clip to Shopify launch / analytics start so pre-Shopify Meta spend is ignored
        if analytics_start:
            try:
                clip = datetime.strptime(analytics_start[:10], "%Y-%m-%d").replace(tzinfo=UTC)
                if clip > start:
                    start = clip
            except ValueError:
                pass

        return start, end, _iso_date(start), _iso_date(end)

    @staticmethod
    def _month_key(day: str) -> str:
        return f"{day[:7]}-01"

    async def get_dashboard(
        self, db: Session, user: User, store_id: str, period: str = "30d"
    ) -> dict:
        store = self._ensure_store(db, user, store_id)
        settings_row = get_or_create_analytics_settings(db, store_id)
        start_dt, end_dt, since, until = self._parse_range(
            period, store, settings_row.analytics_start_date
        )
        currency = store.currency or "USD"

        cost_map = {
            (r.shopify_product_id, r.shopify_variant_id): _d(r.cost_per_unit)
            for r in db.scalars(select(ProductCost).where(ProductCost.store_id == store_id)).all()
        }
        shipping_per_order = _d(settings_row.default_shipping_cost)
        fee_pct = _d(settings_row.transaction_fee_percent) / Decimal("100")
        fee_fixed = _d(settings_row.transaction_fee_fixed)

        # Prior site (e.g. Stripe) — included on All-time (or when window starts at analytics_start)
        prior_revenue = _d(settings_row.prior_external_revenue)
        prior_costs = _d(settings_row.prior_external_costs)
        prior_label = settings_row.prior_external_label or "Prior site (Stripe)"
        include_prior = period == "all" and (prior_revenue > 0 or prior_costs > 0)

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
                if period == "all" and not settings_row.analytics_start_date:
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
        meta_add_to_cart = 0.0
        meta_initiate_checkout = 0.0
        meta_view_content = 0.0
        meta_landing_page_views = 0.0
        meta_link_clicks = 0.0
        daily_meta: dict[str, dict] = defaultdict(
            lambda: {
                "spend": Decimal("0"),
                "purchases": 0,
                "purchase_value": Decimal("0"),
            }
        )
        campaigns: list[dict] = []
        meta_error: str | None = None

        meta_client = self._meta_client(settings_row)
        if meta_client:
            try:
                if period == "all" and not settings_row.analytics_start_date:
                    account_insights = await meta_client.get_account_insights(
                        date_preset="maximum", time_increment=1
                    )
                else:
                    account_insights = await meta_client.get_account_insights(
                        since=since, until=until, time_increment=1
                    )
                for row in account_insights.get("data") or []:
                    day = row.get("date_start") or ""
                    if day and day < since:
                        continue
                    spend = _d(row.get("spend"))
                    ad_spend += spend
                    impressions += int(row.get("impressions") or 0)
                    clicks += int(row.get("clicks") or 0)
                    purchases = parse_meta_purchases(row.get("actions"))
                    purchase_val = _d(parse_meta_purchase_value(row.get("action_values")))
                    funnel = parse_meta_funnel(row.get("actions"))
                    meta_purchases += purchases
                    meta_purchase_value += purchase_val
                    meta_add_to_cart += funnel["add_to_cart"]
                    meta_initiate_checkout += funnel["initiate_checkout"]
                    meta_view_content += funnel["view_content"]
                    meta_landing_page_views += funnel["landing_page_view"]
                    meta_link_clicks += funnel["link_click"]
                    daily_meta[day]["spend"] += spend
                    daily_meta[day]["purchases"] += int(purchases)
                    daily_meta[day]["purchase_value"] += purchase_val

                if period == "all" and not settings_row.analytics_start_date:
                    campaign_rows = await meta_client.get_campaign_insights(date_preset="maximum")
                else:
                    campaign_rows = await meta_client.get_campaign_insights(since=since, until=until)
                for row in campaign_rows:
                    spend = _d(row.get("spend"))
                    purchases = parse_meta_purchases(row.get("actions"))
                    purchase_val = _d(parse_meta_purchase_value(row.get("action_values")))
                    reported_roas = parse_meta_purchase_roas(row.get("purchase_roas"))
                    campaign_roas = (
                        _money(purchase_val / spend)
                        if spend > 0 and purchase_val > 0
                        else _money(_d(reported_roas))
                    )
                    funnel = parse_meta_funnel(row.get("actions"))
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
                            "roas": campaign_roas,
                            "cpa": _money(spend / _d(purchases)) if purchases > 0 else 0,
                            "add_to_cart": int(funnel["add_to_cart"]),
                            "initiate_checkout": int(funnel["initiate_checkout"]),
                        }
                    )
                campaigns.sort(key=lambda c: c["spend"], reverse=True)
            except Exception as e:
                meta_error = str(e)
        elif meta_configured:
            meta_error = "Could not decrypt Meta credentials — re-save your access token."

        # --- Revenue approximation (Meta purchase value) ---
        shopify_revenue = revenue
        # Prefer Shopify when available; fall back to Meta purchase value as approx revenue.
        if shopify_revenue > 0:
            approx_revenue = shopify_revenue
            revenue_source = "shopify"
        elif meta_purchase_value > 0:
            approx_revenue = meta_purchase_value
            revenue_source = "meta_approx"
            revenue = meta_purchase_value
        else:
            approx_revenue = Decimal("0")
            revenue_source = "none"

        # When Shopify has revenue, still expose Meta purchase value as attributed approx.
        meta_approx_revenue = meta_purchase_value

        # Estimate variable cost rate from Shopify when possible; else assume 40% cost + fees.
        if shopify_revenue > 0 and (cogs + shipping_costs + transaction_fees) > 0:
            variable_cost_rate = (cogs + shipping_costs + transaction_fees) / shopify_revenue
        else:
            variable_cost_rate = Decimal("0.45")

        # Meta-attributed P&L estimate using purchase value × observed cost rate.
        meta_est_variable_costs = meta_purchase_value * variable_cost_rate
        meta_est_gross_profit = meta_purchase_value - meta_est_variable_costs
        meta_est_net_profit = meta_est_gross_profit - ad_spend

        # --- Blended metrics (Shopify P&L − Meta spend; Meta-attributed ROAS separate) ---
        # Add prior-site Stripe revenue on All-time so pre-Shopify sales balance the books
        applied_prior_revenue = prior_revenue if include_prior else Decimal("0")
        applied_prior_costs = prior_costs if include_prior else Decimal("0")

        gross_profit = shopify_revenue - cogs - shipping_costs - transaction_fees
        # If we only have Meta approx revenue (no Shopify), estimate gross from cost rate.
        if revenue_source == "meta_approx":
            gross_profit = meta_est_gross_profit
            # Keep cogs/shipping/fees as estimates for breakdown clarity
            if cogs == 0 and shipping_costs == 0 and transaction_fees == 0:
                cogs = meta_purchase_value * Decimal("0.30")
                shipping_costs = meta_purchase_value * Decimal("0.08")
                transaction_fees = meta_purchase_value * Decimal("0.07")

        if include_prior:
            gross_profit = gross_profit + applied_prior_revenue - applied_prior_costs

        net_profit = gross_profit - ad_spend
        display_revenue = (
            (shopify_revenue if shopify_revenue > 0 else approx_revenue) + applied_prior_revenue
        )
        mer = _money(display_revenue / ad_spend) if ad_spend > 0 and display_revenue > 0 else 0
        meta_roas = _money(meta_purchase_value / ad_spend) if ad_spend > 0 else 0
        roas = mer  # blended MER (store revenue / spend)
        cpa = _money(ad_spend / _d(order_count)) if order_count > 0 and ad_spend > 0 else 0
        meta_cpa = _money(ad_spend / _d(meta_purchases)) if meta_purchases > 0 and ad_spend > 0 else 0
        aov = _money(shopify_revenue / _d(order_count)) if order_count > 0 else 0
        meta_aov = (
            _money(meta_purchase_value / _d(meta_purchases)) if meta_purchases > 0 else 0
        )
        margin_before_ads = _pct(gross_profit, display_revenue)
        net_margin = _pct(net_profit, display_revenue)
        break_even_roas = (
            _money(display_revenue / gross_profit) if gross_profit > 0 else 0
        )

        attribution_gap = shopify_revenue - meta_purchase_value
        attribution_coverage_pct = (
            _pct(meta_purchase_value, shopify_revenue) if shopify_revenue > 0 else 0.0
        )

        # Funnel conversion rates (Meta)
        click_to_atc = _pct(_d(meta_add_to_cart), _d(clicks)) if clicks > 0 else 0.0
        atc_to_checkout = (
            _pct(_d(meta_initiate_checkout), _d(meta_add_to_cart)) if meta_add_to_cart > 0 else 0.0
        )
        checkout_to_purchase = (
            _pct(_d(meta_purchases), _d(meta_initiate_checkout)) if meta_initiate_checkout > 0 else 0.0
        )

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
                m = {"spend": Decimal("0"), "purchases": 0, "purchase_value": Decimal("0")}
                month_prefix = key[:7]
                for day, vals in daily_shopify.items():
                    if day.startswith(month_prefix):
                        s["revenue"] += vals["revenue"]
                        s["orders"] += vals["orders"]
                for day, vals in daily_meta.items():
                    if day.startswith(month_prefix):
                        m["spend"] += vals["spend"]
                        m["purchases"] += vals["purchases"]
                        m["purchase_value"] += vals["purchase_value"]
            else:
                s = daily_shopify.get(key, {"revenue": Decimal("0"), "orders": 0})
                m = daily_meta.get(
                    key, {"spend": Decimal("0"), "purchases": 0, "purchase_value": Decimal("0")}
                )
            day_shopify_rev = s["revenue"]
            day_meta_rev = m["purchase_value"]
            # Prefer Shopify revenue for charts; fall back to Meta purchase value.
            day_rev = day_shopify_rev if day_shopify_rev > 0 else day_meta_rev
            day_spend = m["spend"]
            day_orders = s["orders"] if s["orders"] > 0 else m["purchases"]
            day_gross = day_rev - (day_rev * fee_pct) - shipping_per_order * _d(day_orders)
            if day_shopify_rev <= 0 and day_meta_rev > 0:
                day_gross = day_meta_rev * (Decimal("1") - variable_cost_rate)
            daily_chart.append(
                {
                    "date": key,
                    "revenue": _money(day_rev),
                    "shopify_revenue": _money(day_shopify_rev),
                    "meta_purchase_value": _money(day_meta_rev),
                    "ad_spend": _money(day_spend),
                    "orders": int(day_orders),
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

        insights = self._build_insights(
            currency=currency,
            shopify_connected=shopify_connected,
            meta_configured=meta_configured,
            missing_cost_items=missing_cost_items,
            shopify_revenue=shopify_revenue,
            approx_revenue=approx_revenue,
            revenue_source=revenue_source,
            meta_purchase_value=meta_purchase_value,
            meta_purchases=meta_purchases,
            meta_add_to_cart=meta_add_to_cart,
            meta_initiate_checkout=meta_initiate_checkout,
            clicks=clicks,
            ad_spend=ad_spend,
            net_profit=net_profit,
            mer=mer,
            meta_roas=meta_roas,
            break_even_roas=break_even_roas,
            cpa=cpa,
            meta_cpa=meta_cpa,
            aov=aov,
            meta_aov=meta_aov,
            margin_before_ads=margin_before_ads,
            attribution_coverage_pct=attribution_coverage_pct,
            click_to_atc=click_to_atc,
            atc_to_checkout=atc_to_checkout,
            checkout_to_purchase=checkout_to_purchase,
            campaigns=campaigns,
            top_products=top_products,
            cogs=cogs,
            shipping_costs=shipping_costs,
            transaction_fees=transaction_fees,
            order_count=order_count,
        )

        mrr_block = self._mrr_block(db, store_id, settings_row)
        if mrr_block:
            if mrr_block["mrr"] > 0 and ad_spend > 0:
                months_to_recover = float(ad_spend) / mrr_block["mrr"] if mrr_block["mrr"] else 0
                insights.append(
                    {
                        "level": "info",
                        "title": "MRR vs ad spend this period",
                        "message": (
                            f"MRR is {currency} {mrr_block['mrr']:,.2f} "
                            f"({mrr_block['subscribers']} subscribers). "
                            f"This period's ad spend equals ~{months_to_recover:.1f} months of MRR."
                        ),
                        "action": (
                            "Keep CAC under ~1–3 months of ARPU so subscription LTV stays profitable."
                        ),
                    }
                )
            if mrr_block["churn_pct"] >= 8:
                insights.append(
                    {
                        "level": "warning",
                        "title": "High monthly churn",
                        "message": f"Churn is {mrr_block['churn_pct']}% — MRR growth will stall.",
                        "action": "Improve dunning/retries in Phoenix and add a win-back offer before cancel.",
                    }
                )
            elif mrr_block["mrr_delta"] > 0:
                insights.append(
                    {
                        "level": "success",
                        "title": "MRR growing",
                        "message": (
                            f"MRR up {currency} {mrr_block['mrr_delta']:,.2f} vs last snapshot "
                            f"(ARR {currency} {mrr_block['arr']:,.2f})."
                        ),
                        "action": "Scale acquisition into offers that renew — protect approval rates on rebills.",
                    }
                )
            insights.sort(
                key=lambda i: {"danger": 0, "warning": 1, "success": 2, "info": 3}.get(i["level"], 9)
            )
            insights = insights[:8]

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
                "revenue": _money(display_revenue),
                "shopify_revenue": _money(shopify_revenue),
                "approx_revenue": _money(approx_revenue),
                "meta_approx_revenue": _money(meta_approx_revenue),
                "revenue_source": revenue_source,
                "prior_external_revenue": _money(applied_prior_revenue),
                "prior_external_costs": _money(applied_prior_costs),
                "prior_external_label": prior_label,
                "analytics_start_date": settings_row.analytics_start_date,
                "refunds": _money(refunds),
                "orders": order_count,
                "aov": aov,
                "meta_aov": meta_aov,
                "cogs": _money(cogs),
                "shipping_costs": _money(shipping_costs),
                "transaction_fees": _money(transaction_fees),
                "gross_profit": _money(gross_profit),
                "ad_spend": _money(ad_spend),
                "net_profit": _money(net_profit),
                "meta_est_gross_profit": _money(meta_est_gross_profit),
                "meta_est_net_profit": _money(meta_est_net_profit),
                "variable_cost_rate_pct": float(
                    (variable_cost_rate * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
                ),
                "mer": mer,
                "roas": roas,
                "meta_roas": meta_roas,
                "cpa": cpa,
                "meta_cpa": meta_cpa,
                "ctr": _pct(_d(clicks), _d(impressions)),
                "cpc": _money(ad_spend / _d(clicks)) if clicks > 0 else 0,
                "impressions": impressions,
                "clicks": clicks,
                "meta_purchases": int(meta_purchases),
                "meta_purchase_value": _money(meta_purchase_value),
                "meta_add_to_cart": int(meta_add_to_cart),
                "meta_initiate_checkout": int(meta_initiate_checkout),
                "meta_view_content": int(meta_view_content),
                "meta_landing_page_views": int(meta_landing_page_views),
                "meta_link_clicks": int(meta_link_clicks),
                "click_to_atc_pct": click_to_atc,
                "atc_to_checkout_pct": atc_to_checkout,
                "checkout_to_purchase_pct": checkout_to_purchase,
                "attribution_gap": _money(attribution_gap),
                "attribution_coverage_pct": attribution_coverage_pct,
                "margin_before_ads_pct": margin_before_ads,
                "net_margin_pct": net_margin,
                "break_even_roas": break_even_roas,
            },
            "daily_chart": daily_chart,
            "campaigns": campaigns[:15],
            "top_products": top_products,
            "recent_orders": sorted(orders_data, key=lambda o: o["created_at"] or "", reverse=True)[:8],
            "insights": insights,
            "mrr": mrr_block,
        }

    def _build_insights(
        self,
        *,
        currency: str,
        shopify_connected: bool,
        meta_configured: bool,
        missing_cost_items: int,
        shopify_revenue: Decimal,
        approx_revenue: Decimal,
        revenue_source: str,
        meta_purchase_value: Decimal,
        meta_purchases: float,
        meta_add_to_cart: float,
        meta_initiate_checkout: float,
        clicks: int,
        ad_spend: Decimal,
        net_profit: Decimal,
        mer: float,
        meta_roas: float,
        break_even_roas: float,
        cpa: float,
        meta_cpa: float,
        aov: float,
        meta_aov: float,
        margin_before_ads: float,
        attribution_coverage_pct: float,
        click_to_atc: float,
        atc_to_checkout: float,
        checkout_to_purchase: float,
        campaigns: list[dict],
        top_products: list[dict],
        cogs: Decimal,
        shipping_costs: Decimal,
        transaction_fees: Decimal,
        order_count: int,
    ) -> list[dict]:
        """Actionable next-step insights for higher profit."""
        insights: list[dict] = []
        money = lambda v: f"{currency} {_money(_d(v))}"

        if not shopify_connected:
            insights.append(
                {
                    "level": "warning",
                    "title": "Connect Shopify",
                    "message": "Link your store to see real revenue, orders, and product profitability.",
                    "action": "Go to Settings → Stores and connect Shopify.",
                }
            )
        if not meta_configured:
            insights.append(
                {
                    "level": "info",
                    "title": "Add Meta Ads credentials",
                    "message": "Connect Meta to track ad spend, attributed purchases, and blended profit.",
                    "action": "Open the Analytics Settings tab and paste your Meta token + ad account ID.",
                }
            )

        if revenue_source == "meta_approx" and meta_purchase_value > 0:
            insights.append(
                {
                    "level": "info",
                    "title": "Using Meta purchase value as revenue approx",
                    "message": (
                        f"No Shopify orders in this range — estimating revenue at "
                        f"{money(meta_purchase_value)} from Meta tracked purchases."
                    ),
                    "action": "Confirm pixel purchase events match real checkouts, then connect Shopify for exact P&L.",
                }
            )

        if missing_cost_items > 0:
            insights.append(
                {
                    "level": "warning",
                    "title": f"{missing_cost_items} items missing product cost",
                    "message": "Profit is overstated until COGS are set for every sold variant.",
                    "action": "Open Product Costs and enter cost per unit for variants with $0 cost.",
                }
            )

        # Break-even / ROAS
        if ad_spend > 0 and break_even_roas > 0:
            effective_roas = meta_roas if meta_roas > 0 else mer
            if effective_roas < break_even_roas:
                gap = round(break_even_roas - effective_roas, 2)
                insights.append(
                    {
                        "level": "danger",
                        "title": "Ads are below break-even",
                        "message": (
                            f"ROAS is {effective_roas}x vs break-even {break_even_roas}x "
                            f"(need +{gap}x). You are losing money on ad-driven sales."
                        ),
                        "action": (
                            "Pause campaigns under break-even ROAS, raise offer AOV "
                            "(bundles/upsells), or cut COGS/shipping to lower break-even."
                        ),
                    }
                )
            elif net_profit > 0:
                insights.append(
                    {
                        "level": "success",
                        "title": "Profitable after ads",
                        "message": (
                            f"Net profit {money(net_profit)} this period "
                            f"(MER {mer}x, Meta ROAS {meta_roas}x)."
                        ),
                        "action": "Scale the highest-ROAS campaigns 10–20% while watching CPA vs AOV.",
                    }
                )

        # Attribution gap between Shopify and Meta
        if shopify_revenue > 0 and meta_purchase_value > 0:
            if attribution_coverage_pct < 50:
                insights.append(
                    {
                        "level": "warning",
                        "title": "Low Meta attribution coverage",
                        "message": (
                            f"Meta tracks {attribution_coverage_pct}% of Shopify revenue "
                            f"({money(meta_purchase_value)} of {money(shopify_revenue)})."
                        ),
                        "action": (
                            "Verify the Meta pixel + CAPI purchase events, and check if "
                            "organic/other channels drive most sales."
                        ),
                    }
                )
            elif attribution_coverage_pct > 120:
                insights.append(
                    {
                        "level": "info",
                        "title": "Meta purchase value exceeds Shopify revenue",
                        "message": (
                            f"Meta reports {money(meta_purchase_value)} vs Shopify "
                            f"{money(shopify_revenue)} — likely view-through or delayed attribution."
                        ),
                        "action": "Use Meta ROAS for campaign decisions, but Shopify net profit for cash reality.",
                    }
                )

        # AOV comparison
        if aov > 0 and meta_aov > 0 and meta_aov < aov * 0.75:
            insights.append(
                {
                    "level": "info",
                    "title": "Meta-attributed AOV is lower than store AOV",
                    "message": (
                        f"Meta AOV {money(meta_aov)} vs store AOV {money(aov)} — "
                        "paid traffic may buy smaller carts."
                    ),
                    "action": "Test order bumps, bundles, or free-shipping thresholds on Meta landing pages.",
                }
            )

        # CPA vs AOV / margin
        if meta_cpa > 0 and aov > 0 and margin_before_ads > 0:
            max_cpa = aov * (margin_before_ads / 100)
            if meta_cpa > max_cpa:
                insights.append(
                    {
                        "level": "danger",
                        "title": "Meta CPA above max profitable CPA",
                        "message": (
                            f"Meta CPA is {money(meta_cpa)} but max CPA at current margin "
                            f"is ~{money(max_cpa)} (AOV {money(aov)} × {margin_before_ads}% margin)."
                        ),
                        "action": "Tighten targeting, improve creative CTR, or raise AOV before increasing spend.",
                    }
                )
            elif meta_cpa > 0 and cpa > 0 and meta_cpa < cpa * 0.7:
                insights.append(
                    {
                        "level": "success",
                        "title": "Meta acquisition is efficient vs store CPA",
                        "message": (
                            f"Meta CPA {money(meta_cpa)} vs blended store CPA {money(cpa)}."
                        ),
                        "action": "Shift more budget toward Meta campaigns that stay under max CPA.",
                    }
                )

        # Funnel leak diagnostics
        if meta_add_to_cart > 10 and checkout_to_purchase < 30 and atc_to_checkout > 0:
            insights.append(
                {
                    "level": "warning",
                    "title": "Checkout → purchase leak",
                    "message": (
                        f"Only {checkout_to_purchase}% of initiated checkouts convert to purchase "
                        f"({int(meta_initiate_checkout)} checkouts → {int(meta_purchases)} purchases)."
                    ),
                    "action": "Fix checkout friction, payment options, shipping clarity, and abandoned-cart recovery.",
                }
            )
        elif clicks > 50 and click_to_atc < 2:
            insights.append(
                {
                    "level": "warning",
                    "title": "Weak click → add-to-cart rate",
                    "message": (
                        f"Only {click_to_atc}% of clicks add to cart. Landing page or offer may not match ads."
                    ),
                    "action": "Align creative with PDP, speed up page load, and test a stronger hero offer.",
                }
            )
        elif meta_add_to_cart > 10 and atc_to_checkout < 20:
            insights.append(
                {
                    "level": "warning",
                    "title": "Add-to-cart → checkout drop-off",
                    "message": f"Only {atc_to_checkout}% of ATCs reach checkout.",
                    "action": "Simplify cart UX, surface shipping cost earlier, and add urgency or social proof.",
                }
            )

        # Cost structure
        rev_for_costs = shopify_revenue if shopify_revenue > 0 else approx_revenue
        if rev_for_costs > 0:
            cogs_pct = _pct(cogs, rev_for_costs)
            ship_pct = _pct(shipping_costs, rev_for_costs)
            fee_pct_val = _pct(transaction_fees, rev_for_costs)
            if cogs_pct >= 45:
                insights.append(
                    {
                        "level": "warning",
                        "title": "High product cost ratio",
                        "message": f"COGS are {cogs_pct}% of revenue — squeezing ad profitability.",
                        "action": "Negotiate supplier pricing, prefer higher-margin SKUs in ads, or raise prices.",
                    }
                )
            if ship_pct >= 15:
                insights.append(
                    {
                        "level": "info",
                        "title": "Shipping eats margin",
                        "message": f"Shipping is {ship_pct}% of revenue.",
                        "action": "Test free-shipping thresholds, regional carriers, or bake shipping into price.",
                    }
                )
            if fee_pct_val >= 5:
                insights.append(
                    {
                        "level": "info",
                        "title": "Payment fees are material",
                        "message": f"Fees are {fee_pct_val}% of revenue.",
                        "action": "Review processor rates and avoid unnecessary partial-capture retries.",
                    }
                )

        # Campaign-level next steps
        if campaigns:
            scalable = [
                c for c in campaigns if c["spend"] >= 20 and c["roas"] >= max(break_even_roas, 1.5)
            ]
            wasteful = [
                c for c in campaigns if c["spend"] >= 30 and (c["roas"] < 1 or c["purchases"] == 0)
            ]
            if scalable:
                best = max(scalable, key=lambda c: c["roas"])
                insights.append(
                    {
                        "level": "success",
                        "title": f"Scale '{best['campaign_name']}'",
                        "message": (
                            f"{best['roas']}x Meta ROAS on {money(best['spend'])} spend "
                            f"({best['purchases']} purchases)."
                        ),
                        "action": "Increase daily budget 15–25% and duplicate winning creatives into new ad sets.",
                    }
                )
            if wasteful:
                worst = min(wasteful, key=lambda c: c["roas"])
                insights.append(
                    {
                        "level": "danger",
                        "title": f"Cut or rebuild '{worst['campaign_name']}'",
                        "message": (
                            f"{money(worst['spend'])} spent at {worst['roas']}x ROAS "
                            f"({worst['purchases']} purchases)."
                        ),
                        "action": "Pause this campaign, refresh creative/audience, or reallocate budget to winners.",
                    }
                )

        # Product focus
        if top_products:
            best_p = max(top_products, key=lambda p: p["margin_pct"])
            worst_p = min(top_products, key=lambda p: p["margin_pct"])
            if best_p["margin_pct"] >= 40 and best_p["revenue"] > 0:
                insights.append(
                    {
                        "level": "success",
                        "title": f"Push '{best_p['title']}' harder",
                        "message": (
                            f"{best_p['margin_pct']}% margin on {money(best_p['revenue'])} revenue."
                        ),
                        "action": "Prioritize this SKU in Meta creatives and landing pages for higher profit per click.",
                    }
                )
            if (
                worst_p["margin_pct"] < 20
                and worst_p["revenue"] > 0
                and worst_p["title"] != best_p["title"]
            ):
                insights.append(
                    {
                        "level": "info",
                        "title": f"Low-margin SKU: '{worst_p['title']}'",
                        "message": f"Only {worst_p['margin_pct']}% margin — ads may not pay off.",
                        "action": "Stop paid ads on this SKU or raise price/bundle it with higher-margin products.",
                    }
                )

        # Empty-state nudge
        if not insights and order_count == 0 and ad_spend == 0:
            insights.append(
                {
                    "level": "info",
                    "title": "No activity in this period",
                    "message": "There are no Shopify orders or Meta spend for the selected range.",
                    "action": "Widen the date range or confirm both Shopify and Meta are connected.",
                }
            )

        # Cap to keep UI scannable — prioritize danger > warning > success > info
        priority = {"danger": 0, "warning": 1, "success": 2, "info": 3}
        insights.sort(key=lambda i: priority.get(i["level"], 9))
        return insights[:8]
