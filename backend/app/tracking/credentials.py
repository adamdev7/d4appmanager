"""Resolve per-store carrier API credentials (store settings + optional server fallback)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value
from app.db.models import StoreTrackingSettings


@dataclass
class CarrierConfig:
    mode: str
    track17_api_key: str | None
    yunexpress_api_key: str | None
    yunexpress_api_url: str
    yunexpress_customer_code: str | None
    yunexpress_keywords: list[str]

    @property
    def has_track17(self) -> bool:
        return bool(self.track17_api_key)

    @property
    def has_yunexpress(self) -> bool:
        return bool(self.yunexpress_api_key)

    def should_use_yunexpress(self, carrier: str | None, tracking_number: str | None) -> bool:
        if self.mode == "yunexpress":
            return self.has_yunexpress
        if self.mode == "17track":
            return False
        if self.mode == "shopify_only":
            return False
        blob = f"{carrier or ''} {tracking_number or ''}".lower()
        return self.has_yunexpress and any(k in blob for k in self.yunexpress_keywords if k)


def mask_api_key_hint(api_key: str) -> str:
    key = api_key.strip()
    if len(key) <= 4:
        return "••••"
    return key[-4:]


def get_or_create_tracking_settings(db: Session, store_id: str) -> StoreTrackingSettings:
    row = db.scalar(select(StoreTrackingSettings).where(StoreTrackingSettings.store_id == store_id))
    if row:
        return row
    row = StoreTrackingSettings(store_id=store_id)
    db.add(row)
    db.flush()
    return row


def _decrypt_key(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        return decrypt_value(encrypted)
    except ValueError:
        return None


def resolve_carrier_config(db: Session, store_id: str) -> CarrierConfig:
    row = get_or_create_tracking_settings(db, store_id)
    track17 = _decrypt_key(row.track17_api_key_encrypted) or settings.track17_api_key or None
    yunexpress = _decrypt_key(row.yunexpress_api_key_encrypted) or settings.yunexpress_api_key or None
    keywords = [
        k.strip().lower()
        for k in (row.yunexpress_carrier_keywords or "yun,yunexpress").split(",")
        if k.strip()
    ]
    return CarrierConfig(
        mode=row.carrier_mode or "auto",
        track17_api_key=track17,
        yunexpress_api_key=yunexpress,
        yunexpress_api_url=(row.yunexpress_api_url or settings.yunexpress_api_url).rstrip("/"),
        yunexpress_customer_code=row.yunexpress_customer_code,
        yunexpress_keywords=keywords or ["yun", "yunexpress"],
    )
