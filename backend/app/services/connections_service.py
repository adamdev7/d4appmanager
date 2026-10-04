"""Account-level connections shared by more than one option."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value, encrypt_value
from app.core.openai_models import model_catalog
from app.db.models import Store, StoreAnalyticsSettings, StoreMetaCapiSettings, User
from app.services.analytics_service import AnalyticsService, get_or_create_analytics_settings
from app.services.meta_capi_service import MetaCapiService
from app.tracking.credentials import mask_api_key_hint

_analytics = AnalyticsService()
_capi = MetaCapiService()


class ConnectionsService:
    def text_models(self) -> dict:
        return model_catalog()

    def _store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def get_meta(self, db: Session, user: User, store_id: str) -> dict:
        self._store(db, user, store_id)
        analytics = get_or_create_analytics_settings(db, store_id)
        capi = _capi.get_or_create_settings(db, store_id)
        has_token = bool(analytics.meta_access_token_encrypted)
        return {
            "store_id": store_id,
            "meta_configured": bool(has_token and analytics.meta_ad_account_id),
            "meta_token_masked": (
                (analytics.meta_access_token_hint or "••••") if has_token else None
            ),
            "meta_ad_account_id": analytics.meta_ad_account_id,
            "meta_pixel_id": capi.meta_pixel_id,
            "pixel_configured": bool(capi.meta_pixel_id),
            "capi_has_override_token": bool(capi.meta_access_token_encrypted),
        }

    def update_meta(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self._store(db, user, store_id)
        analytics = get_or_create_analytics_settings(db, store_id)
        capi = _capi.get_or_create_settings(db, store_id)

        if body.get("clear_access_token"):
            analytics.meta_access_token_encrypted = None
            analytics.meta_access_token_hint = None
        elif body.get("meta_access_token") is not None:
            token = str(body["meta_access_token"]).strip()
            if token:
                analytics.meta_access_token_encrypted = encrypt_value(token)
                analytics.meta_access_token_hint = mask_api_key_hint(token)

        if body.get("meta_ad_account_id") is not None:
            account = str(body["meta_ad_account_id"]).strip().replace("act_", "")
            analytics.meta_ad_account_id = account or None

        if body.get("meta_pixel_id") is not None:
            pixel = str(body["meta_pixel_id"]).strip()
            capi.meta_pixel_id = pixel or None

        db.commit()
        return self.get_meta(db, user, store_id)

    async def test_meta(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self._store(db, user, store_id)
        return await _analytics.test_meta_connection(db, user, store_id, body)

    def account_token(self, db: Session, store_id: str) -> str | None:
        analytics = db.scalar(
            select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == store_id)
        )
        if not analytics or not analytics.meta_access_token_encrypted:
            return None
        try:
            return decrypt_value(analytics.meta_access_token_encrypted)
        except Exception:
            return None

    def capi_row(self, db: Session, store_id: str) -> StoreMetaCapiSettings | None:
        return db.scalar(
            select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store_id)
        )
