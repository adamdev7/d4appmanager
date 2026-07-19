from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import encrypt_value
from app.db.models import OrderTracking, Store, User
from app.tracking.credentials import (
    get_or_create_tracking_settings,
    mask_api_key_hint,
    resolve_carrier_config,
)


class TrackingService:
    def _ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        return store

    def get_settings(self, db: Session, user: User, store_id: str) -> dict:
        self._ensure_store(db, user, store_id)
        row = get_or_create_tracking_settings(db, store_id)
        config = resolve_carrier_config(db, store_id)

        return {
            "store_id": store_id,
            "carrier_mode": row.carrier_mode,
            "auto_enrich_enabled": row.auto_enrich_enabled,
            "yunexpress_api_url": row.yunexpress_api_url,
            "yunexpress_customer_code": row.yunexpress_customer_code,
            "yunexpress_carrier_keywords": row.yunexpress_carrier_keywords,
            "track17_configured": config.has_track17,
            "track17_key_masked": self._masked_hint(row.track17_api_key_hint, config.has_track17),
            "yunexpress_configured": config.has_yunexpress,
            "yunexpress_key_masked": self._masked_hint(row.yunexpress_api_key_hint, config.has_yunexpress),
            "uses_server_track17_fallback": bool(
                settings.track17_api_key and not row.track17_api_key_encrypted
            ),
            "uses_server_yunexpress_fallback": bool(
                settings.yunexpress_api_key and not row.yunexpress_api_key_encrypted
            ),
        }

    def update_settings(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self._ensure_store(db, user, store_id)
        row = get_or_create_tracking_settings(db, store_id)

        if body.get("carrier_mode") is not None:
            mode = str(body["carrier_mode"]).strip().lower()
            if mode not in ("auto", "17track", "yunexpress", "shopify_only"):
                raise HTTPException(status_code=400, detail="Invalid carrier_mode")
            row.carrier_mode = mode

        if body.get("auto_enrich_enabled") is not None:
            row.auto_enrich_enabled = bool(body["auto_enrich_enabled"])

        if body.get("yunexpress_api_url") is not None:
            row.yunexpress_api_url = str(body["yunexpress_api_url"]).strip() or "https://api.yunexpress.com"

        if body.get("yunexpress_customer_code") is not None:
            code = str(body["yunexpress_customer_code"]).strip()
            row.yunexpress_customer_code = code or None

        if body.get("yunexpress_carrier_keywords") is not None:
            row.yunexpress_carrier_keywords = str(body["yunexpress_carrier_keywords"]).strip()

        if body.get("track17_api_key") is not None:
            key = str(body["track17_api_key"]).strip()
            if key:
                row.track17_api_key_encrypted = encrypt_value(key)
                row.track17_api_key_hint = mask_api_key_hint(key)
            else:
                row.track17_api_key_encrypted = None
                row.track17_api_key_hint = None

        if body.get("yunexpress_api_key") is not None:
            key = str(body["yunexpress_api_key"]).strip()
            if key:
                row.yunexpress_api_key_encrypted = encrypt_value(key)
                row.yunexpress_api_key_hint = mask_api_key_hint(key)
            else:
                row.yunexpress_api_key_encrypted = None
                row.yunexpress_api_key_hint = None

        db.commit()
        return self.get_settings(db, user, store_id)

    def get_overview(self, db: Session, user: User, store_id: str) -> dict:
        store = self._ensure_store(db, user, store_id)
        settings_data = self.get_settings(db, user, store_id)

        total = (
            db.scalar(
                select(func.count())
                .select_from(OrderTracking)
                .where(OrderTracking.store_id == store_id)
            )
            or 0
        )
        with_tracking = (
            db.scalar(
                select(func.count())
                .select_from(OrderTracking)
                .where(
                    OrderTracking.store_id == store_id,
                    OrderTracking.tracking_number.isnot(None),
                    OrderTracking.tracking_number != "",
                )
            )
            or 0
        )

        rows = db.scalars(
            select(OrderTracking)
            .where(OrderTracking.store_id == store_id)
            .order_by(OrderTracking.last_updated_at.desc().nullslast(), OrderTracking.updated_at.desc())
            .limit(25)
        ).all()

        base = settings.app_url.rstrip("/")
        return {
            "store_id": store.id,
            "store_name": store.name,
            "shop_domain": store.shop_domain,
            "store_status": store.status,
            "track_endpoint": f"{base}/api/track-order",
            "settings": settings_data,
            "carrier_enrichment": {
                "track17": settings_data["track17_configured"],
                "yunexpress": settings_data["yunexpress_configured"],
                "auto_enrich": settings_data["auto_enrich_enabled"],
                "mode": settings_data["carrier_mode"],
            },
            "stats": {
                "orders_synced": total,
                "with_tracking": with_tracking,
            },
            "recent_orders": [self._serialize_order(row) for row in rows],
        }

    @staticmethod
    def _masked_hint(hint: str | None, configured: bool) -> str | None:
        if not configured:
            return None
        if hint:
            return f"••••{hint}"
        return "••••configured"

    @staticmethod
    def _serialize_order(row: OrderTracking) -> dict:
        return {
            "id": row.id,
            "order_number": row.order_number_display,
            "customer_email": row.customer_email,
            "tracking_number": row.tracking_number,
            "carrier": row.carrier,
            "status": row.status,
            "last_updated_at": row.last_updated_at.isoformat() if row.last_updated_at else None,
        }
