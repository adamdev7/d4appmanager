"""Apply carrier API enrichment to stored order tracking rows."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import OrderTracking, StoreTrackingSettings
from app.integrations.tracking.carrier_api import (
    enrich_from_carrier_apis,
    fetch_17track,
    fetch_yunexpress,
)
from app.tracking.credentials import get_or_create_tracking_settings, resolve_carrier_config
from app.tracking.timeline_normalize import normalize_timeline

logger = logging.getLogger(__name__)


class CarrierEnrichmentService:
    def __init__(self, db: Session) -> None:
        self._db = db

    async def enrich_if_enabled(self, store_id: str, order_tracking_id: str) -> bool:
        settings = get_or_create_tracking_settings(self._db, store_id)
        if not settings.auto_enrich_enabled:
            return False
        return await self.enrich_order(store_id, order_tracking_id)

    async def enrich_order(self, store_id: str, order_tracking_id: str) -> bool:
        row = self._db.get(OrderTracking, order_tracking_id)
        if not row or row.store_id != store_id or not row.tracking_number:
            return False

        config = resolve_carrier_config(self._db, store_id)
        if config.mode == "shopify_only":
            return False
        if not config.has_track17 and not config.has_yunexpress:
            return False

        enriched = await enrich_from_carrier_apis(
            config,
            row.tracking_number,
            row.carrier,
        )
        if not enriched:
            return False

        self._apply_enrichment(row, enriched)
        self._db.flush()
        return True

    async def test_provider(
        self,
        store_id: str,
        provider: str,
        tracking_number: str | None,
    ) -> tuple[bool, str, str | None]:
        config = resolve_carrier_config(self._db, store_id)
        sample = (tracking_number or "").strip() or "TEST123456789"

        if provider == "yunexpress":
            if not config.has_yunexpress:
                return False, "Add your YunExpress API key first.", None
            result = await fetch_yunexpress(config, sample)
            if result:
                return True, "YunExpress API responded successfully.", result.get("status")
            return False, "YunExpress did not return tracking data. Check URL, key, and sample number.", None

        if provider == "17track":
            if not config.has_track17:
                return False, "Add your 17TRACK API key first.", None
            result = await fetch_17track(config, sample, None)
            if result:
                raw = result.get("carrier_status_raw") or ""
                sub = result.get("carrier_sub_status_raw") or ""
                detail = f" (17TRACK: {raw}" + (f" / {sub}" if sub and sub != raw else "") + ")"
                return True, f"17TRACK OK — App status: {result.get('status')}{detail}", result.get("status")
            return (
                False,
                "17TRACK did not return data yet (new numbers may need time after register). "
                "Try a real tracking number from your store.",
                None,
            )

        return False, "Unknown provider.", None

    @staticmethod
    def _apply_enrichment(row: OrderTracking, enriched: dict) -> None:
        row.status = enriched.get("status") or row.status
        if enriched.get("carrier"):
            row.carrier = enriched["carrier"]

        carrier_events = list(enriched.get("events") or [])
        row.timeline_json = json.dumps(
            normalize_timeline(carrier_events, shipment_status=row.status or "pending")
        )
        row.last_updated_at = datetime.now(UTC)
