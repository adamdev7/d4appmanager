"""Shopify order webhooks → Meta Conversions API Purchase events."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import (
    MetaCapiAttributionCache,
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
from app.integrations.meta.order_mapper import (
    build_browser_funnel_event,
    build_initiate_checkout_event,
    build_purchase_event,
)
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
            if not row.browser_event_token:
                row.browser_event_token = secrets.token_urlsafe(24)
                db.commit()
                db.refresh(row)
            return row
        row = StoreMetaCapiSettings(
            store_id=store_id,
            browser_event_token=secrets.token_urlsafe(24),
        )
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
            "send_initiate_checkout": bool(getattr(row, "send_initiate_checkout", True)),
            "browser_event_token": row.browser_event_token,
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

        if body.get("send_initiate_checkout") is not None:
            row.send_initiate_checkout = bool(body["send_initiate_checkout"])

        if body.get("rotate_browser_event_token"):
            row.browser_event_token = secrets.token_urlsafe(24)

        if not row.browser_event_token:
            row.browser_event_token = secrets.token_urlsafe(24)

        # Configuring credentials should turn tracking on unless explicitly disabled
        configuring = any(
            k in body
            for k in ("meta_pixel_id", "meta_access_token", "use_analytics_token")
        )
        if configuring and body.get("enabled") is None:
            if row.meta_pixel_id and self._resolve_access_token(db, row):
                row.enabled = True

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

        by_event_rows = db.execute(
            select(MetaCapiEventLog.event_name, func.count())
            .where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.status == MetaCapiEventStatus.SENT.value,
                MetaCapiEventLog.sent_at >= start_today,
            )
            .group_by(MetaCapiEventLog.event_name)
        ).all()
        sent_today_by_event = {
            str(name or "Purchase"): int(cnt or 0) for name, cnt in by_event_rows
        }

        return {
            "settings": settings,
            "sent_today": sent_today,
            "failed_today": failed_today,
            "skipped_today": skipped_today,
            "total_sent": total_sent,
            "sent_today_by_event": sent_today_by_event,
            "last_successful_send_at": last_sent.sent_at.isoformat() if last_sent and last_sent.sent_at else None,
            "last_event_id": last_sent.event_id if last_sent else None,
            "last_order_id": last_sent.shopify_order_id if last_sent else None,
            "last_event_name": last_sent.event_name if last_sent else None,
        }

    def list_events(
        self,
        db: Session,
        user: User,
        store_id: str,
        *,
        limit: int = 100,
        event_name: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_store(db, user, store_id)
        limit = max(1, min(limit, 500))

        filters = [MetaCapiEventLog.store_id == store_id]
        name_filter = (event_name or "").strip()
        if name_filter and name_filter.lower() not in {"all", "*"}:
            filters.append(MetaCapiEventLog.event_name == name_filter)
        status_filter = (status or "").strip().lower()
        if status_filter and status_filter not in {"all", "*"}:
            filters.append(MetaCapiEventLog.status == status_filter)

        rows = db.scalars(
            select(MetaCapiEventLog)
            .where(*filters)
            .order_by(MetaCapiEventLog.created_at.desc())
            .limit(limit)
        ).all()

        type_rows = db.execute(
            select(MetaCapiEventLog.event_name, func.count())
            .where(MetaCapiEventLog.store_id == store_id)
            .group_by(MetaCapiEventLog.event_name)
            .order_by(func.count().desc())
        ).all()
        event_type_counts = {
            str(name or "Purchase"): int(cnt or 0) for name, cnt in type_rows
        }

        events = [
            {
                "id": r.id,
                "shopify_order_id": r.shopify_order_id,
                "topic": r.topic,
                "event_name": r.event_name or "Purchase",
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
        return {
            "events": events,
            "event_type_counts": event_type_counts,
            "limit": limit,
            "event_name": name_filter or "all",
            "status": status_filter or "all",
        }

    _PAID_FINANCIAL = frozenset({"paid", "partially_paid"})

    def should_handle_topic(
        self,
        settings: StoreMetaCapiSettings,
        topic: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        if not settings.enabled:
            return False
        t = topic.strip().lower()
        if t == "checkouts/create" and bool(getattr(settings, "send_initiate_checkout", True)):
            return True

        expected = (settings.trigger_topic or "orders/paid").strip().lower()
        if t == expected:
            return True

        # Never-miss Purchase: catch paid orders on create/update too (COD, delayed capture)
        fin = str((payload or {}).get("financial_status") or "").lower()
        if t == "orders/paid":
            return True
        if t in ("orders/create", "orders/updated") and fin in self._PAID_FINANCIAL:
            return True
        return False

    def try_claim_event(
        self,
        db: Session,
        *,
        store_id: str,
        webhook_id: str | None,
        shopify_order_id: str,
        topic: str,
        event_id: str,
        event_name: str = "Purchase",
        order_value: str | None,
        currency: str | None,
    ) -> MetaCapiEventLog | None:
        """Insert pending log row. Returns None if already processed (idempotent skip)."""
        # Already sent or in-flight for this entity + event?
        existing = db.scalar(
            select(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.shopify_order_id == shopify_order_id,
                MetaCapiEventLog.event_name == event_name,
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
                "meta_capi skip duplicate store=%s entity=%s event=%s status=%s",
                store_id,
                shopify_order_id,
                event_name,
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
            event_name=event_name,
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
        if not settings or not self.should_handle_topic(settings, topic, payload):
            return {"queued": False, "reason": "disabled_or_topic"}

        if not settings.meta_pixel_id:
            return {"queued": False, "reason": "missing_pixel"}

        topic_l = topic.strip().lower()
        if topic_l == "checkouts/create":
            event = build_initiate_checkout_event(
                payload, shop_domain=store.shop_domain or ""
            )
            entity_id = str(payload.get("token") or payload.get("id") or "")
            event_kind = "InitiateCheckout"
            payload_kind = "checkout"
        else:
            entity_id = str(payload.get("id") or "")
            event = build_purchase_event(
                payload,
                shop_domain=store.shop_domain or "",
                event_id_scheme=settings.event_id_scheme or "order_id",
            )
            event_kind = "Purchase"
            payload_kind = "order"

        if not entity_id:
            return {"queued": False, "reason": "missing_entity_id"}

        age_sec = int(datetime.now(UTC).timestamp()) - int(event.get("event_time") or 0)
        if age_sec > 7 * 24 * 3600:
            logger.warning(
                "meta_capi skip stale store=%s entity=%s age_days=%.1f",
                store.id,
                entity_id,
                age_sec / 86400,
            )
            return {"queued": False, "reason": "stale_event"}

        custom = event.get("custom_data") or {}
        log_row = self.try_claim_event(
            db,
            store_id=store.id,
            webhook_id=webhook_id,
            shopify_order_id=entity_id,
            topic=topic,
            event_id=str(event.get("event_id") or entity_id),
            event_name=event_kind,
            order_value=str(custom.get("value") if custom.get("value") is not None else ""),
            currency=str(custom.get("currency") or "") or None,
        )
        if not log_row:
            return {"queued": False, "reason": "duplicate"}

        log_id = log_row.id
        store_id = store.id
        asyncio.create_task(
            _send_capi_event_background(
                store_id=store_id,
                log_id=log_id,
                order_payload=payload,
                payload_kind=payload_kind,
            )
        )
        return {
            "queued": True,
            "log_id": log_id,
            "event_id": event.get("event_id"),
            "event_name": event_kind,
        }

    async def ingest_browser_event(
        self,
        db: Session,
        *,
        store_id: str,
        token: str,
        body: dict[str, Any],
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """Public theme beacon for ViewContent / AddToCart (token-gated)."""
        settings = db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store_id)
        )
        store = db.get(Store, store_id)
        if not settings or not store or not settings.enabled:
            raise HTTPException(status_code=404, detail="Not found")
        provided = (token or "").strip()
        expected = settings.browser_event_token or ""
        try:
            token_ok = bool(expected) and bool(provided) and secrets.compare_digest(
                expected, provided
            )
        except (TypeError, ValueError):
            token_ok = False
        if not token_ok:
            raise HTTPException(status_code=401, detail="Invalid token")
        if not settings.meta_pixel_id or not self._resolve_access_token(db, settings):
            raise HTTPException(status_code=400, detail="CAPI not configured")

        # Always cache IP/UA/fbp for later Purchase enrichment (Phoenix omits Shopify browser fields)
        self.remember_browser_attribution(
            db,
            store_id=store_id,
            body=body,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        event_name = str(body.get("event_name") or "").strip()
        event_id = str(body.get("event_id") or "").strip()
        if not event_name or not event_id:
            raise HTTPException(status_code=400, detail="event_name and event_id required")

        # Attribution-only ping — cache signals, do not spam Meta
        if event_name == "Attribution":
            return {"ok": True, "cached": True, "event_name": event_name}

        try:
            value = body.get("value")
            event = build_browser_funnel_event(
                event_name=event_name,
                event_id=event_id,
                shop_domain=store.shop_domain or "",
                event_source_url=body.get("event_source_url"),
                value=float(value) if value is not None and value != "" else None,
                currency=str(body.get("currency") or "USD"),
                content_ids=list(body.get("content_ids") or []) or None,
                contents=list(body.get("contents") or []) or None,
                num_items=int(body["num_items"]) if body.get("num_items") is not None else None,
                search_string=body.get("search_string"),
                content_name=body.get("content_name"),
                content_category=body.get("content_category"),
                email=body.get("email"),
                phone=body.get("phone"),
                fbp=body.get("fbp"),
                fbc=body.get("fbc"),
                fbclid=body.get("fbclid"),
                client_ip_address=body.get("client_ip_address") or client_ip,
                client_user_agent=body.get("client_user_agent") or user_agent,
                external_id=body.get("external_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        entity_key = f"browser:{event_name}:{event_id}"
        log_row = self.try_claim_event(
            db,
            store_id=store_id,
            webhook_id=f"browser:{event_id}:{event_name}",
            shopify_order_id=entity_key[:64],
            topic="browser/funnel",
            event_id=event_id,
            event_name=event_name,
            order_value=str((event.get("custom_data") or {}).get("value") or ""),
            currency=str((event.get("custom_data") or {}).get("currency") or "") or None,
        )
        if not log_row:
            return {"ok": True, "skipped": True, "reason": "duplicate"}

        access = self._resolve_access_token(db, settings) or ""
        client = MetaCapiClient(
            pixel_id=settings.meta_pixel_id or "",
            access_token=access,
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
            db.commit()
            return {
                "ok": True,
                "skipped": False,
                "event_name": event_name,
                "event_id": event_id,
                "events_received": log_row.meta_events_received,
            }
        except Exception as exc:
            msg = str(exc)[:2000]
            if access and access in msg:
                msg = msg.replace(access, "[redacted]")
            log_row.status = MetaCapiEventStatus.FAILED.value
            log_row.error_message = msg
            db.commit()
            return {"ok": False, "error": msg[:500]}

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

        order = self.enrich_order_payload(db, store_id=store.id, order=order)

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

    def _upsert_attribution(
        self,
        db: Session,
        *,
        store_id: str,
        lookup_key: str,
        fbp: str | None = None,
        fbc: str | None = None,
        fbclid: str | None = None,
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        key = (lookup_key or "").strip()[:191]
        if not key:
            return
        row = db.scalar(
            select(MetaCapiAttributionCache).where(
                MetaCapiAttributionCache.store_id == store_id,
                MetaCapiAttributionCache.lookup_key == key,
            )
        )
        if not row:
            row = MetaCapiAttributionCache(store_id=store_id, lookup_key=key)
            db.add(row)
        if fbp:
            row.fbp = str(fbp)[:255]
        if fbc:
            row.fbc = str(fbc)[:512]
        if fbclid:
            row.fbclid = str(fbclid)[:255]
        if client_ip:
            row.client_ip = str(client_ip)[:64]
        if user_agent:
            row.user_agent = str(user_agent)[:2000]
        row.updated_at = datetime.now(UTC)
        db.commit()

    def remember_browser_attribution(
        self,
        db: Session,
        *,
        store_id: str,
        body: dict[str, Any],
        client_ip: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Cache IP/UA/fbp from theme beacons for Purchase enrichment (Phoenix often omits them)."""
        fbp = str(body.get("fbp") or "").strip() or None
        fbc = str(body.get("fbc") or "").strip() or None
        fbclid = str(body.get("fbclid") or "").strip() or None
        cart_token = str(body.get("cart_token") or body.get("checkout_token") or "").strip() or None
        ua = str(body.get("client_user_agent") or user_agent or "").strip() or None
        ip = str(body.get("client_ip_address") or client_ip or "").strip() or None
        if fbp:
            self._upsert_attribution(
                db,
                store_id=store_id,
                lookup_key=f"fbp:{fbp}",
                fbp=fbp,
                fbc=fbc,
                fbclid=fbclid,
                client_ip=ip,
                user_agent=ua,
            )
        if cart_token:
            self._upsert_attribution(
                db,
                store_id=store_id,
                lookup_key=f"cart:{cart_token}",
                fbp=fbp,
                fbc=fbc,
                fbclid=fbclid,
                client_ip=ip,
                user_agent=ua,
            )

    def enrich_order_payload(
        self, db: Session, *, store_id: str, order: dict[str, Any]
    ) -> dict[str, Any]:
        """Fill missing browser_ip / UA / fbp from attribution cache into a copy of the order."""
        payload = dict(order)
        notes = {
            str(a.get("name") or a.get("key") or "").strip(): str(a.get("value") or "").strip()
            for a in (payload.get("note_attributes") or [])
            if isinstance(a, dict)
        }
        attrs = payload.get("attributes") if isinstance(payload.get("attributes"), dict) else {}
        for k, v in attrs.items():
            if k and v is not None and str(v).strip():
                notes[str(k)] = str(v).strip()

        fbp = notes.get("_fbp") or notes.get("fbp") or ""
        cart_token = (
            str(payload.get("cart_token") or payload.get("checkout_token") or "").strip()
            or notes.get("cart_token")
            or ""
        )

        cache: MetaCapiAttributionCache | None = None
        if cart_token:
            cache = db.scalar(
                select(MetaCapiAttributionCache).where(
                    MetaCapiAttributionCache.store_id == store_id,
                    MetaCapiAttributionCache.lookup_key == f"cart:{cart_token}",
                )
            )
        if not cache and fbp:
            cache = db.scalar(
                select(MetaCapiAttributionCache).where(
                    MetaCapiAttributionCache.store_id == store_id,
                    MetaCapiAttributionCache.lookup_key == f"fbp:{fbp}",
                )
            )
        if not cache:
            return payload

        if not payload.get("browser_ip") and cache.client_ip:
            payload["browser_ip"] = cache.client_ip

        details = dict(payload.get("client_details") or {})
        if not details.get("user_agent") and cache.user_agent:
            details["user_agent"] = cache.user_agent
            payload["client_details"] = details

        # Merge cookie signals into note_attributes when missing
        merged = list(payload.get("note_attributes") or [])
        existing_keys = {
            str(a.get("name") or a.get("key") or "").lower()
            for a in merged
            if isinstance(a, dict)
        }

        def _add_note(name: str, value: str | None) -> None:
            if not value:
                return
            if name.lower() in existing_keys:
                return
            merged.append({"name": name, "value": value})
            existing_keys.add(name.lower())

        _add_note("_fbp", cache.fbp)
        _add_note("_fbc", cache.fbc)
        _add_note("fbclid", cache.fbclid)
        _add_note("user_agent", cache.user_agent)
        _add_note("browser_ip", cache.client_ip)
        payload["note_attributes"] = merged
        return payload

    def _is_configured(self, db: Session, settings: StoreMetaCapiSettings) -> bool:
        return bool(settings.meta_pixel_id) and bool(self._resolve_access_token(db, settings))

    async def _resend_purchase_log(
        self,
        db: Session,
        *,
        store: Store,
        settings: StoreMetaCapiSettings,
        log_row: MetaCapiEventLog,
        order: dict[str, Any],
    ) -> bool:
        """Retry an existing FAILED/PENDING Purchase log using the same event_id."""
        from app.config import settings as app_settings

        max_attempts = int(getattr(app_settings, "meta_capi_max_send_attempts", 15) or 15)
        if (log_row.attempts or 0) >= max_attempts:
            return False

        token = self._resolve_access_token(db, settings)
        if not token or not settings.meta_pixel_id:
            return False

        order = self.enrich_order_payload(db, store_id=store.id, order=order)

        event = build_purchase_event(
            order,
            shop_domain=store.shop_domain or "",
            event_id_scheme=settings.event_id_scheme or "order_id",
        )
        # Keep original event_id for Meta dedupe
        if log_row.event_id:
            event["event_id"] = log_row.event_id

        age_sec = int(datetime.now(UTC).timestamp()) - int(event.get("event_time") or 0)
        if age_sec > 7 * 24 * 3600:
            log_row.status = MetaCapiEventStatus.FAILED.value
            log_row.error_message = "Order older than 7 days — Meta will reject it"
            db.commit()
            return False

        client = MetaCapiClient(
            pixel_id=settings.meta_pixel_id,
            access_token=token,
            api_version=settings.api_version or DEFAULT_API_VERSION,
            test_event_code=settings.test_event_code,
        )
        log_row.status = MetaCapiEventStatus.PENDING.value
        log_row.attempts = (log_row.attempts or 0) + 1
        db.commit()

        try:
            result = await client.send_events([event])
            log_row.status = MetaCapiEventStatus.SENT.value
            log_row.sent_at = datetime.now(UTC)
            log_row.meta_events_received = int(result.get("events_received") or 0)
            log_row.meta_fbtrace_id = str(result.get("fbtrace_id") or "") or None
            log_row.error_message = None
            db.commit()
            return True
        except Exception as exc:
            msg = str(exc)
            if token in msg:
                msg = msg.replace(token, "[redacted]")
            log_row.status = MetaCapiEventStatus.FAILED.value
            log_row.error_message = msg[:2000]
            db.commit()
            return False

    async def reconcile_store(self, db: Session, store_id: str) -> dict[str, Any]:
        """Retry failures + pull recent paid Shopify orders missing a SENT Purchase."""
        from app.config import settings as app_settings

        store = db.get(Store, store_id)
        settings = db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store_id)
        )
        summary: dict[str, Any] = {
            "store_id": store_id,
            "retried": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "examined": 0,
        }
        if not store or not settings or not settings.enabled:
            return summary
        if not self._is_configured(db, settings):
            return summary
        if not store.access_token_encrypted:
            return summary

        max_attempts = int(getattr(app_settings, "meta_capi_max_send_attempts", 15) or 15)
        hours = int(getattr(app_settings, "meta_capi_reconcile_hours", 48) or 48)
        hours = max(1, min(hours, 168))
        pending_timeout = datetime.now(UTC) - timedelta(minutes=15)
        retry_since = datetime.now(UTC) - timedelta(days=7)

        # Stuck PENDING → FAILED so we can resend
        stuck = db.scalars(
            select(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.event_name == "Purchase",
                MetaCapiEventLog.status == MetaCapiEventStatus.PENDING.value,
                MetaCapiEventLog.created_at < pending_timeout,
            )
        ).all()
        for row in stuck:
            row.status = MetaCapiEventStatus.FAILED.value
            row.error_message = row.error_message or "Timed out pending; scheduled for retry"
        if stuck:
            db.commit()

        client = self._shopify_client(store)

        failed_rows = db.scalars(
            select(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store_id,
                MetaCapiEventLog.event_name == "Purchase",
                MetaCapiEventLog.status == MetaCapiEventStatus.FAILED.value,
                MetaCapiEventLog.attempts < max_attempts,
                MetaCapiEventLog.created_at >= retry_since,
            )
        ).all()
        for log_row in failed_rows:
            try:
                order = await client.get_order(log_row.shopify_order_id)
            except Exception as exc:
                logger.warning(
                    "meta_capi retry fetch failed store=%s order=%s err=%s",
                    store_id,
                    log_row.shopify_order_id,
                    exc,
                )
                summary["failed"] += 1
                continue
            ok = await self._resend_purchase_log(
                db, store=store, settings=settings, log_row=log_row, order=order
            )
            if ok:
                summary["retried"] += 1
            else:
                summary["failed"] += 1

        # Pull paid orders and send any without SENT
        since = datetime.now(UTC) - timedelta(hours=hours)
        try:
            orders = await client.list_all_orders_in_range(
                created_at_min=since.isoformat(),
                financial_status="paid",
                max_pages=4,
            )
        except Exception:
            logger.exception("meta_capi reconcile list_orders failed store=%s", store_id)
            return summary

        summary["examined"] = len(orders)
        for order in orders:
            order_id = str(order.get("id") or "")
            if not order_id:
                continue
            fin = str(order.get("financial_status") or "").lower()
            if fin not in self._PAID_FINANCIAL:
                continue
            already = db.scalar(
                select(MetaCapiEventLog).where(
                    MetaCapiEventLog.store_id == store_id,
                    MetaCapiEventLog.shopify_order_id == order_id,
                    MetaCapiEventLog.event_name == "Purchase",
                )
            )
            if already:
                # SENT / PENDING / FAILED (retry path above) — don't create a second log
                summary["skipped"] += 1
                continue
            row = await self._send_order_now(
                db,
                store=store,
                settings=settings,
                order=order,
                topic="reconcile/paid",
                force=False,
            )
            if row.get("skipped"):
                summary["skipped"] += 1
            elif row.get("ok"):
                summary["sent"] += 1
            else:
                summary["failed"] += 1

        return summary

    async def reconcile_all_configured_stores(self, db: Session) -> dict[str, Any]:
        """Background sweep across every store with CAPI enabled + credentials."""
        rows = db.scalars(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.enabled.is_(True))
        ).all()
        totals = {"stores": 0, "retried": 0, "sent": 0, "skipped": 0, "failed": 0, "examined": 0}
        for settings in rows:
            if not self._is_configured(db, settings):
                continue
            totals["stores"] += 1
            part = await self.reconcile_store(db, settings.store_id)
            for key in ("retried", "sent", "skipped", "failed", "examined"):
                totals[key] += int(part.get(key) or 0)
        return totals


async def _send_capi_event_background(
    *,
    store_id: str,
    log_id: str,
    order_payload: dict[str, Any],
    payload_kind: str = "order",
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

        if payload_kind == "checkout":
            order_payload = service.enrich_order_payload(
                db, store_id=store_id, order=order_payload
            )
            event = build_initiate_checkout_event(
                order_payload, shop_domain=store.shop_domain or ""
            )
        else:
            order_payload = service.enrich_order_payload(
                db, store_id=store_id, order=order_payload
            )
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
