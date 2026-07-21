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
    ) -> dict:
        """Query a carrier API and return ok/message plus the fetched payload for the UI."""
        config = resolve_carrier_config(self._db, store_id)
        sample = (tracking_number or "").strip()

        empty = {
            "ok": False,
            "message": "",
            "status": None,
            "tracking_number": sample or None,
            "carrier": None,
            "source": None,
            "carrier_status_raw": None,
            "carrier_sub_status_raw": None,
            "timeline": [],
            "last_updated_at": None,
        }

        if provider == "yunexpress":
            if not config.has_yunexpress:
                return {**empty, "message": "Add your YunExpress API key first."}
            if not sample:
                return {**empty, "message": "Enter a tracking number to test YunExpress."}
            result = await fetch_yunexpress(config, sample)
            if not result:
                return {
                    **empty,
                    "message": "YunExpress did not return tracking data. Check URL, key, and number.",
                }
            return self._test_result_payload(
                ok=True,
                message="YunExpress returned tracking data.",
                tracking_number=sample,
                result=result,
            )

        if provider == "17track":
            if not config.has_track17:
                return {**empty, "message": "Add your 17TRACK API key first."}
            if not sample:
                return {**empty, "message": "Enter a tracking number to test 17TRACK."}
            result = await fetch_17track(config, sample, None)
            if not result:
                return {
                    **empty,
                    "message": (
                        "17TRACK did not return data yet (new numbers may need a minute after "
                        "register). Try again, or use a number already tracked in 17TRACK."
                    ),
                }
            raw = result.get("carrier_status_raw") or ""
            sub = result.get("carrier_sub_status_raw") or ""
            detail = f"17TRACK status: {raw}" + (f" / {sub}" if sub and sub != raw else "")
            return self._test_result_payload(
                ok=True,
                message=f"17TRACK OK — app status: {result.get('status')} ({detail})",
                tracking_number=sample,
                result=result,
            )

        return {**empty, "message": "Unknown provider."}

    @staticmethod
    def _test_result_payload(
        *,
        ok: bool,
        message: str,
        tracking_number: str,
        result: dict,
    ) -> dict:
        events = []
        for event in result.get("events") or []:
            if not isinstance(event, dict):
                continue
            at = event.get("at")
            events.append(
                {
                    "status": str(event.get("status") or ""),
                    "description": str(event.get("description") or ""),
                    "location": str(event.get("location") or ""),
                    "at": at.isoformat() if hasattr(at, "isoformat") else str(at or ""),
                }
            )
        return {
            "ok": ok,
            "message": message,
            "status": result.get("status"),
            "tracking_number": tracking_number,
            "carrier": result.get("carrier") or None,
            "source": result.get("source") or None,
            "carrier_status_raw": result.get("carrier_status_raw") or None,
            "carrier_sub_status_raw": result.get("carrier_sub_status_raw") or None,
            "timeline": events,
            "last_updated_at": result.get("last_updated_at"),
        }

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
