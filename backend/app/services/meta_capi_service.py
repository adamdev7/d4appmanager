"""Shopify order webhooks → Meta Conversions API Purchase events."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import (
    MetaCapiEventLog,
    MetaCapiEventStatus,
    Store,
    StoreAnalyticsSettings,
    StoreMetaCapiSettings,
    User,
)
from app.db.session import SessionLocal
from app.integrations.meta.capi_client import DEFAULT_API_VERSION, MetaCapiClient
from app.integrations.meta.hashing import hash_email
from app.integrations.meta.order_mapper import build_purchase_event
from app.integrations.shopify.client import ShopifyClient
from app.tracking.credentials import mask_api_key_hint

logger = logging.getLogger(__name__)

_VALID_EVENT_ID_SCHEMES = frozenset({"order_id", "checkout_token", "order_name"})
_VALID_TRIGGER_TOPICS = frozenset({"orders/paid", "orders/create"})


class MetaCapiService:
    def get_or_create_settings(self, db: Session, store_id: str) -> StoreMetaCapiSettings:
        row = db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store_id)
        )
        if row:
            return row
        row = StoreMetaCapiSettings(store_id=store_id)
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def _masked_hint(self, hint: str | None, has_secret: bool) -> str | None:
        if hint:
            return hint
        return "••••" if has_secret else None

    def _settings_dict(self, row: StoreMetaCapiSettings) -> dict[str, Any]:
        configured = bool(row.meta_pixel_id) and (
            bool(row.meta_access_token_encrypted) or bool(row.use_analytics_token)
        )
        return {
            "enabled": bool(row.enabled),
            "meta_pixel_id": row.meta_pixel_id,
            "meta_token_masked": self._masked_hint(
                row.meta_access_token_hint, bool(row.meta_access_token_encrypted)
            ),
            "has_access_token": bool(row.meta_access_token_encrypted),
            "use_analytics_token": bool(row.use_analytics_token),
            "test_event_code": row.test_event_code,
            "event_id_scheme": row.event_id_scheme or "order_id",
            "trigger_topic": row.trigger_topic or "orders/paid",
            "api_version": row.api_version or DEFAULT_API_VERSION,
            "configured": configured,
            "ready": bool(row.enabled and configured and row.meta_pixel_id),
        }

    def get_settings(self, db: Session, user: User, store_id: str) -> dict[str, Any]:
        self._ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, store_id)
        return self._settings_dict(row)

    def update_settings(
        self, db: Session, user: User, store_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, store_id)

        if body.get("enabled") is not None:
            row.enabled = bool(body["enabled"])

        if body.get("meta_pixel_id") is not None:
            pixel = str(body["meta_pixel_id"]).strip()
            row.meta_pixel_id = pixel or None

        if body.get("clear_access_token"):
            row.meta_access_token_encrypted = None
            row.meta_access_token_hint = None
        elif body.get("meta_access_token") is not None:
            token = str(body["meta_access_token"]).strip()
            if token:
                row.meta_access_token_encrypted = encrypt_value(token)
                row.meta_access_token_hint = mask_api_key_hint(token)

        if body.get("clear_test_event_code"):
            row.test_event_code = None
        elif body.get("test_event_code") is not None:
            code = str(body["test_event_code"]).strip()
            row.test_event_code = code or None

        if body.get("event_id_scheme") is not None:
            scheme = str(body["event_id_scheme"]).strip().lower()
            if scheme not in _VALID_EVENT_ID_SCHEMES:
                raise HTTPException(
                    status_code=400,
                    detail=f"event_id_scheme must be one of: {', '.join(sorted(_VALID_EVENT_ID_SCHEMES))}",
                )
            row.event_id_scheme = scheme

        if body.get("trigger_topic") is not None:
            topic = str(body["trigger_topic"]).strip().lower()
            if topic not in _VALID_TRIGGER_TOPICS:
                raise HTTPException(
                    status_code=400,
                    detail=f"trigger_topic must be one of: {', '.join(sorted(_VALID_TRIGGER_TOPICS))}",
                )
            row.trigger_topic = topic

        if body.get("api_version") is not None:
            version = str(body["api_version"]).strip() or DEFAULT_API_VERSION
            if not version.startswith("v"):
                version = f"v{version}"
            row.api_version = version

        if body.get("use_analytics_token") is not None:
            row.use_analytics_token = bool(body["use_analytics_token"])

        db.commit()
        db.refresh(row)
        return self._settings_dict(row)

    def _resolve_access_token(self, db: Session, row: StoreMetaCapiSettings) -> str | None:
        if row.meta_access_token_encrypted:
            try:
                return decrypt_value(row.meta_access_token_encrypted)
            except Exception:
                logger.exception("Failed to decrypt Meta CAPI token for store %s", row.store_id)
                return None
        if row.use_analytics_token:
            analytics = db.scalar(
                select(StoreAnalyticsSettings).where(
                    StoreAnalyticsSettings.store_id == row.store_id
                )
            )
            if analytics and analytics.meta_access_token_encrypted:
                try:
                    return decrypt_value(analytics.meta_access_token_encrypted)
                except Exception:
                    logger.exception(
                        "Failed to decrypt Analytics Meta token for store %s", row.store_id
                    )
        return None

    async def test_connection(
        self, db: Session, user: User, store_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        self._ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, store_id)

        pixel_id = str(body.get("meta_pixel_id") or row.meta_pixel_id or "").strip()
        token = str(body.get("meta_access_token") or "").strip()
        if not token:
            token = self._resolve_access_token(db, row) or ""
        test_code = str(body.get("test_event_code") or row.test_event_code or "").strip() or None

        if not pixel_id or not token:
            return {
                "ok": False,
                "message": "Pixel ID and access token are required.",
            }

        # Minimal validation event — Meta Test Events if code set
        test_em = hash_email("test@example.com")
        event = {
            "event_name": "Purchase",
            "event_time": int(datetime.now(UTC).timestamp()),
            "event_id": f"capi_test_{store_id[:8]}_{int(datetime.now(UTC).timestamp())}",
            "action_source": "website",
            "user_data": {"em": [test_em]} if test_em else {},
            "custom_data": {
                "currency": "USD",
                "value": 0.01,
                "content_type": "product",
                "order_id": "capi_connection_test",
            },
        }

        client = MetaCapiClient(
            pixel_id=pixel_id,
            access_token=token,
            api_version=row.api_version or DEFAULT_API_VERSION,
            test_event_code=test_code,
        )
        try:
            result = await client.send_events([event])
            return {
                "ok": True,
                "message": (
                    f"Meta accepted test event (events_received="
                    f"{result.get('events_received')})."
                    + (" Check Test Events in Events Manager." if test_code else "")
                ),
                "events_received": result.get("events_received"),
                "fbtrace_id": result.get("fbtrace_id"),
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)[:500]}

    def get_stats(self, db: Session, user: User, store_id: str) -> dict[str, Any]:
        self._ensure_store(db, user, store_id)
        settings = self._settings_dict(self.get_or_create_settings(db, store_id))

        now = datetime.now(UTC)
        start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        sent_today = (
            db.scalar(
                select(func.count())
                .select_from(MetaCapiEventLog)
                .where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
                    MetaCapiEventLog.sent_at >= start_today,
                )
            )
            or 0
        )
        failed_today = (
            db.scalar(
                select(func.count())
                .select_from(MetaCapiEventLog)
                .where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.status == MetaCapiEventStatus.FAILED.value,
                    MetaCapiEventLog.created_at >= start_today,
                )
            )
            or 0
        )
        skipped_today = (
            db.scalar(
                select(func.count())
                .select_from(MetaCapiEventLog)
                .where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.status == MetaCapiEventStatus.SKIPPED.value,
                    MetaCapiEventLog.created_at >= start_today,
                )
            )
            or 0
        )
        last_sent = db.scalar(
            select(MetaCapiEventLog)
            .where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
            )
            .order_by(MetaCapiEventLog.sent_at.desc())
            .limit(1)
        )
        total_sent = (
            db.scalar(
                select(func.count())
                .select_from(MetaCapiEventLog)
                .where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
                )
            )
            or 0
        )

        return {
            "settings": settings,
            "sent_today": sent_today,
            "failed_today": failed_today,
            "skipped_today": skipped_today,
            "total_sent": total_sent,
            "last_successful_send_at": last_sent.sent_at.isoformat() if last_sent and last_sent.sent_at else None,
            "last_event_id": last_sent.event_id if last_sent else None,
            "last_order_id": last_sent.shopify_order_id if last_sent else None,
        }

    def list_events(
        self, db: Session, user: User, store_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        self._ensure_store(db, user, store_id)
        limit = max(1, min(limit, 200))
        rows = db.scalars(
            select(MetaCapiEventLog)
            .where(MetaCapiEventLog.store_id == store_id)
            .order_by(MetaCapiEventLog.created_at.desc())
            .limit(limit)
        ).all()
        return [
            {
                "id": r.id,
                "shopify_order_id": r.shopify_order_id,
                "topic": r.topic,
                "event_id": r.event_id,
                "status": r.status,
                "attempts": r.attempts,
                "meta_events_received": r.meta_events_received,
                "meta_fbtrace_id": r.meta_fbtrace_id,
                "error_message": r.error_message,
                "order_value": r.order_value,
                "currency": r.currency,
                "sent_at": r.sent_at.isoformat() if r.sent_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def should_handle_topic(self, settings: StoreMetaCapiSettings, topic: str) -> bool:
        if not settings.enabled:
            return False
        expected = (settings.trigger_topic or "orders/paid").strip().lower()
        return topic.strip().lower() == expected

    def try_claim_event(
        self,
        db: Session,
        *,
        store_id: str,
        webhook_id: str | None,
        shopify_order_id: str,
        topic: str,
        event_id: str,
        order_value: str | None,
        currency: str | None,
    ) -> MetaCapiEventLog | None:
        """Insert pending log row. Returns None if already processed (idempotent skip)."""
        # Already sent or in-flight for this order?
        existing = db.scalar(
            select(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.shopify_order_id == shopify_order_id,
                MetaCapiEventLog.event_name == "Purchase",
                MetaCapiEventLog.status.in_(
                    [
                        MetaCapiEventStatus.SENT.value,
                        MetaCapiEventStatus.PENDING.value,
                    ]
                ),
            )
        )
        if existing:
            logger.info(
                "meta_capi skip duplicate order store=%s order=%s status=%s",
                store_id,
                shopify_order_id,
                existing.status,
            )
            return None

        if webhook_id:
            by_webhook = db.scalar(
                select(MetaCapiEventLog).where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.webhook_id == webhook_id,
                )
            )
            if by_webhook:
                logger.info(
                    "meta_capi skip duplicate webhook store=%s webhook_id=%s",
                    store_id,
                    webhook_id,
                )
                return None

        row = MetaCapiEventLog(
            store_id=store_id,
            webhook_id=webhook_id or None,
            shopify_order_id=shopify_order_id,
            topic=topic,
            event_name="Purchase",
            event_id=event_id,
            status=MetaCapiEventStatus.PENDING.value,
            order_value=order_value,
            currency=currency,
        )
        db.add(row)
        try:
            db.commit()
            db.refresh(row)
            return row
        except IntegrityError:
            db.rollback()
            logger.info(
                "meta_capi claim race skip store=%s order=%s",
                store_id,
                shopify_order_id,
            )
            return None

    def enqueue_from_webhook(
        self,
        db: Session,
        *,
        store: Store,
        topic: str,
        payload: dict[str, Any],
        webhook_id: str | None,
    ) -> dict[str, Any]:
        """Synchronous claim + schedule async Meta send. Safe to call from webhook handler."""
        settings = db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store.id)
        )
        if not settings or not self.should_handle_topic(settings, topic):
            return {"queued": False, "reason": "disabled_or_topic"}

        if not settings.meta_pixel_id:
            return {"queued": False, "reason": "missing_pixel"}

        order_id = str(payload.get("id") or "")
        if not order_id:
            return {"queued": False, "reason": "missing_order_id"}

        # Stale events (>7 days) are rejected by Meta
        event = build_purchase_event(
            payload,
            shop_domain=store.shop_domain or "",
            event_id_scheme=settings.event_id_scheme or "order_id",
        )
        age_sec = int(datetime.now(UTC).timestamp()) - int(event.get("event_time") or 0)
        if age_sec > 7 * 24 * 3600:
            logger.warning(
                "meta_capi skip stale order store=%s order=%s age_days=%.1f",
                store.id,
                order_id,
                age_sec / 86400,
            )
            return {"queued": False, "reason": "stale_event"}

        custom = event.get("custom_data") or {}
        log_row = self.try_claim_event(
            db,
            store_id=store.id,
            webhook_id=webhook_id,
            shopify_order_id=order_id,
            topic=topic,
            event_id=str(event.get("event_id") or order_id),
            order_value=str(custom.get("value") if custom.get("value") is not None else ""),
            currency=str(custom.get("currency") or "") or None,
        )
        if not log_row:
            return {"queued": False, "reason": "duplicate"}

        # Capture IDs before session closes in background task
        log_id = log_row.id
        store_id = store.id
        asyncio.create_task(
            _send_capi_event_background(store_id=store_id, log_id=log_id, order_payload=payload)
        )
        return {"queued": True, "log_id": log_id, "event_id": event.get("event_id")}

    def _shopify_client(self, store: Store) -> ShopifyClient:
        if not store.access_token_encrypted:
            raise HTTPException(status_code=400, detail="Store is not connected to Shopify")
        try:
            token = decrypt_value(store.access_token_encrypted)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not decrypt store token") from exc
        return ShopifyClient(store.shop_domain, token)

    async def _resolve_order_payload(
        self, client: ShopifyClient, order_ref: str
    ) -> dict[str, Any]:
        ref = order_ref.strip()
        if not ref:
            raise HTTPException(status_code=400, detail="order_ref is required")

        # Numeric Shopify order id
        if ref.isdigit():
            try:
                return await client.get_order(ref)
            except Exception as exc:
                raise HTTPException(
                    status_code=404, detail=f"Order {ref} not found in Shopify"
                ) from exc

        # Order name: #1042 or 1042
        name = ref if ref.startswith("#") else f"#{ref}"
        try:
            matches = await client.list_orders(limit=5, status="any", name=name)
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Shopify order lookup failed: {exc}"
            ) from exc
        if not matches:
            # Retry without # — some stores search bare number
            bare = ref.lstrip("#")
            matches = await client.list_orders(limit=5, status="any", name=bare)
        if not matches:
            raise HTTPException(status_code=404, detail=f"No Shopify order matching {name}")
        return matches[0]

    async def _send_order_now(
        self,
        db: Session,
        *,
        store: Store,
        settings: StoreMetaCapiSettings,
        order: dict[str, Any],
        topic: str = "manual/backfill",
        force: bool = False,
    ) -> dict[str, Any]:
        """Fetch-ready order dict → Meta CAPI Purchase (synchronous)."""
        if not settings.meta_pixel_id:
            raise HTTPException(status_code=400, detail="Meta Pixel ID is not configured")

        token = self._resolve_access_token(db, settings)
        if not token:
            raise HTTPException(status_code=400, detail="Meta access token is not configured")

        order_id = str(order.get("id") or "")
        if not order_id:
            raise HTTPException(status_code=400, detail="Order payload missing id")

        event = build_purchase_event(
            order,
            shop_domain=store.shop_domain or "",
            event_id_scheme=settings.event_id_scheme or "order_id",
        )
        age_sec = int(datetime.now(UTC).timestamp()) - int(event.get("event_time") or 0)
        if age_sec > 7 * 24 * 3600:
            raise HTTPException(
                status_code=400,
                detail="Order is older than 7 days — Meta will reject it",
            )

        existing = db.scalar(
            select(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store.id,
                MetaCapiEventLog.shopify_order_id == order_id,
                MetaCapiEventLog.event_name == "Purchase",
                MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
            )
        )
        if existing and not force:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_sent",
                "shopify_order_id": order_id,
                "event_id": existing.event_id,
                "log_id": existing.id,
            }

        custom = event.get("custom_data") or {}
        webhook_id = f"backfill:{order_id}:{int(datetime.now(UTC).timestamp())}"
        log_row = MetaCapiEventLog(
            store_id=store.id,
            webhook_id=webhook_id,
            shopify_order_id=order_id,
            topic=topic,
            event_name="Purchase",
            event_id=str(event.get("event_id") or order_id),
            status=MetaCapiEventStatus.PENDING.value,
            order_value=str(custom.get("value") if custom.get("value") is not None else ""),
            currency=str(custom.get("currency") or "") or None,
        )
        db.add(log_row)
        db.commit()
        db.refresh(log_row)

        client = MetaCapiClient(
            pixel_id=settings.meta_pixel_id,
            access_token=token,
            api_version=settings.api_version or DEFAULT_API_VERSION,
            test_event_code=settings.test_event_code,
        )
        log_row.attempts = (log_row.attempts or 0) + 1
        db.commit()

        try:
            result = await client.send_events([event])
            log_row.status = MetaCapiEventStatus.SENT.value
            log_row.sent_at = datetime.now(UTC)
            log_row.meta_events_received = int(result.get("events_received") or 0)
            log_row.meta_fbtrace_id = str(result.get("fbtrace_id") or "") or None
            log_row.error_message = None
            log_row.event_id = str(event.get("event_id") or log_row.event_id)
            db.commit()
            return {
                "ok": True,
                "skipped": False,
                "shopify_order_id": order_id,
                "order_name": order.get("name"),
                "event_id": log_row.event_id,
                "events_received": log_row.meta_events_received,
                "fbtrace_id": log_row.meta_fbtrace_id,
                "log_id": log_row.id,
                "value": custom.get("value"),
                "currency": custom.get("currency"),
            }
        except Exception as exc:
            msg = str(exc)
            if token in msg:
                msg = msg.replace(token, "[redacted]")
            log_row.status = MetaCapiEventStatus.FAILED.value
            log_row.error_message = msg[:2000]
            db.commit()
            return {
                "ok": False,
                "skipped": False,
                "shopify_order_id": order_id,
                "order_name": order.get("name"),
                "event_id": log_row.event_id,
                "error": msg[:500],
                "log_id": log_row.id,
            }

    async def backfill_order(
        self, db: Session, user: User, store_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        store = self._ensure_store(db, user, store_id)
        settings = self.get_or_create_settings(db, store_id)
        if not settings.meta_pixel_id or not self._resolve_access_token(db, settings):
            raise HTTPException(
                status_code=400,
                detail="Configure Pixel ID and access token before backfilling",
            )

        client = self._shopify_client(store)
        order_ref = str(body.get("order_ref") or "")
        force = bool(body.get("force"))
        order = await self._resolve_order_payload(client, order_ref)
        return await self._send_order_now(
            db, store=store, settings=settings, order=order, force=force
        )

    async def backfill_recent(
        self, db: Session, user: User, store_id: str, body: dict[str, Any]
    ) -> dict[str, Any]:
        store = self._ensure_store(db, user, store_id)
        settings = self.get_or_create_settings(db, store_id)
        if not settings.meta_pixel_id or not self._resolve_access_token(db, settings):
            raise HTTPException(
                status_code=400,
                detail="Configure Pixel ID and access token before backfilling",
            )

        hours = int(body.get("hours") or 24)
        limit = int(body.get("limit") or 50)
        hours = max(1, min(hours, 168))
        limit = max(1, min(limit, 100))

        since = datetime.now(UTC) - timedelta(hours=hours)
        client = self._shopify_client(store)
        try:
            orders = await client.list_orders(
                limit=limit,
                status="any",
                financial_status="paid",
                created_at_min=since.isoformat(),
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"Shopify list orders failed: {exc}"
            ) from exc

        results: list[dict[str, Any]] = []
        sent = 0
        skipped = 0
        failed = 0
        for order in orders:
            row = await self._send_order_now(
                db,
                store=store,
                settings=settings,
                order=order,
                topic="manual/backfill_recent",
                force=False,
            )
            results.append(row)
            if row.get("skipped"):
                skipped += 1
            elif row.get("ok"):
                sent += 1
            else:
                failed += 1

        return {
            "ok": failed == 0,
            "hours": hours,
            "examined": len(orders),
            "sent": sent,
            "skipped": skipped,
            "failed": failed,
            "results": results,
        }


async def _send_capi_event_background(
    *, store_id: str, log_id: str, order_payload: dict[str, Any]
) -> None:
    """Open a fresh DB session and send to Meta (does not block Shopify webhook response)."""
    db = SessionLocal()
    try:
        service = MetaCapiService()
        settings = db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store_id)
        )
        log_row = db.get(MetaCapiEventLog, log_id)
        store = db.get(Store, store_id)
        if not settings or not log_row or not store:
            return

        token = service._resolve_access_token(db, settings)
        if not token or not settings.meta_pixel_id:
            log_row.status = MetaCapiEventStatus.FAILED.value
            log_row.error_message = "Missing pixel ID or access token"
            log_row.attempts = (log_row.attempts or 0) + 1
            db.commit()
            return

        event = build_purchase_event(
            order_payload,
            shop_domain=store.shop_domain or "",
            event_id_scheme=settings.event_id_scheme or "order_id",
        )
        client = MetaCapiClient(
            pixel_id=settings.meta_pixel_id,
            access_token=token,
            api_version=settings.api_version or DEFAULT_API_VERSION,
            test_event_code=settings.test_event_code,
        )

        log_row.attempts = (log_row.attempts or 0) + 1
        db.commit()

        try:
            result = await client.send_events([event])
            log_row.status = MetaCapiEventStatus.SENT.value
            log_row.sent_at = datetime.now(UTC)
            log_row.meta_events_received = int(result.get("events_received") or 0)
            log_row.meta_fbtrace_id = str(result.get("fbtrace_id") or "") or None
            log_row.error_message = None
            log_row.event_id = str(event.get("event_id") or log_row.event_id)
            db.commit()
            logger.info(
                "meta_capi sent store=%s order=%s event_id=%s events_received=%s fbtrace_id=%s",
                store_id,
                log_row.shopify_order_id,
                log_row.event_id,
                log_row.meta_events_received,
                log_row.meta_fbtrace_id,
            )
        except Exception as exc:
            log_row.status = MetaCapiEventStatus.FAILED.value
            # Never log tokens; truncate error text
            msg = str(exc)
            for secret in (token,):
                if secret and secret in msg:
                    msg = msg.replace(secret, "[redacted]")
            log_row.error_message = msg[:2000]
            db.commit()
            logger.exception(
                "meta_capi failed store=%s order=%s event_id=%s",
                store_id,
                log_row.shopify_order_id,
                log_row.event_id,
            )
    except Exception:
        logger.exception("meta_capi background task crashed store=%s log=%s", store_id, log_id)
    finally:
        db.close()
