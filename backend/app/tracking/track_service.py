"""Look up order tracking for the public track-order page."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value
from app.db.models import OrderTracking, Store, StoreStatus
from app.integrations.shopify.client import ShopifyClient
from app.integrations.tracking.carrier_api import enrich_from_carrier_apis
from app.tracking.credentials import resolve_carrier_config
from app.tracking.enrichment_service import CarrierEnrichmentService
from app.tracking.order_sync import OrderTrackingSyncService
from app.tracking.timeline_normalize import normalize_timeline
from app.tracking.payload_parser import (
    normalize_email,
    normalize_order_number,
    order_number_variants,
    recipient_email,
    tracking_from_payload,
)

logger = logging.getLogger(__name__)

_CARRIER_REFRESH_MINUTES = 30


class TrackOrderService:
    def __init__(self, db: Session) -> None:
        self._db = db
        self._sync = OrderTrackingSyncService(db)

    async def track(
        self,
        *,
        store_id: str,
        order_number: str,
        email: str,
    ) -> dict[str, Any] | None:
        store = self._db.get(Store, store_id)
        if not store or store.status != StoreStatus.CONNECTED.value:
            return None

        normalized_number = normalize_order_number(order_number)
        normalized_email = normalize_email(email)
        if not normalized_number or not normalized_email:
            return None

        row = self._find_row(store_id, normalized_number, normalized_email)
        if not row:
            row = await self._fetch_from_shopify(store, order_number, normalized_email)

        if not row:
            return None

        if not row.customer_email or row.customer_email != normalized_email:
            return None

        if not row.order_placed_at or not row.order_total_display:
            refreshed = await self._refresh_order_summary_from_shopify(
                store, row, order_number, normalized_email
            )
            if refreshed:
                row = refreshed

        tracking_number = row.tracking_number or ""
        carrier = row.carrier or ""
        status = row.status or "pending"
        events = self._load_timeline(row.timeline_json, shipment_status=status)
        last_updated = row.last_updated_at

        if tracking_number and self._should_refresh_carrier(row):
            config = resolve_carrier_config(self._db, store_id)
            if config.mode != "shopify_only" and (config.has_track17 or config.has_yunexpress):
                enriched = await enrich_from_carrier_apis(config, tracking_number, carrier)
                if enriched:
                    CarrierEnrichmentService(self._db)._apply_enrichment(row, enriched)
                    status = row.status
                    carrier = row.carrier or carrier
                    events = self._load_timeline(row.timeline_json, shipment_status=status)
                    last_updated = row.last_updated_at
                    self._db.commit()

        return self._row_to_response(row, tracking_number, carrier, status, events, last_updated)

    @staticmethod
    def _row_to_response(
        row: OrderTracking,
        tracking_number: str,
        carrier: str,
        status: str,
        events: list[dict[str, str]],
        last_updated: datetime | None,
    ) -> dict[str, Any]:
        line_items = TrackOrderService._load_line_items(row.line_items_json)
        return {
            "order_number": row.order_number_display,
            "order_placed_at": row.order_placed_at.isoformat() if row.order_placed_at else None,
            "order_total": row.order_total_display,
            "currency": row.order_currency,
            "line_items": line_items,
            "tracking_number": tracking_number or None,
            "carrier": carrier or None,
            "status": status,
            "timeline": events,
            "last_updated_at": (last_updated or row.updated_at).isoformat()
            if last_updated or row.updated_at
            else None,
        }

    async def _refresh_order_summary_from_shopify(
        self,
        store: Store,
        row: OrderTracking,
        order_number: str,
        normalized_email: str,
    ) -> OrderTracking | None:
        """Backfill order summary for rows synced before summary fields existed."""
        if not store.access_token_encrypted:
            return None
        try:
            token = decrypt_value(store.access_token_encrypted)
        except ValueError:
            return None

        display_number = order_number.strip()
        if not display_number.startswith("#"):
            search_name = f"#{normalize_order_number(display_number)}"
        else:
            search_name = display_number

        try:
            import httpx

            from app.integrations.shopify.client import ShopifyClient

            client = ShopifyClient(store.shop_domain, token)
            async with httpx.AsyncClient(timeout=30) as http:
                resp = await http.get(
                    f"{client.admin_api_base}/orders.json",
                    params={"name": search_name, "status": "any", "limit": 5},
                    headers={"X-Shopify-Access-Token": token},
                )
                resp.raise_for_status()
                orders = resp.json().get("orders") or []
        except Exception:
            logger.exception("Shopify order summary refresh failed for store %s", store.id)
            return None

        for order in orders:
            if normalize_email(recipient_email(order)) != normalized_email:
                continue
            self._sync._apply_order_summary(row, order)
            self._db.commit()
            return row
        return None

    def _find_row(
        self,
        store_id: str,
        normalized_number: str,
        normalized_email: str,
    ) -> OrderTracking | None:
        variants = {normalize_order_number(v) for v in order_number_variants(normalized_number)}
        variants.discard("")
        if not variants:
            return None

        return self._db.scalar(
            select(OrderTracking).where(
                OrderTracking.store_id == store_id,
                OrderTracking.customer_email == normalized_email,
                OrderTracking.order_number_normalized.in_(variants),
            )
        )

    async def _fetch_from_shopify(
        self,
        store: Store,
        order_number: str,
        normalized_email: str,
    ) -> OrderTracking | None:
        if not store.access_token_encrypted:
            return None
        try:
            token = decrypt_value(store.access_token_encrypted)
        except ValueError:
            logger.warning("Could not decrypt Shopify token for store %s", store.id)
            return None

        client = ShopifyClient(store.shop_domain, token)
        display_number = order_number.strip()
        if not display_number.startswith("#"):
            search_name = f"#{normalize_order_number(display_number)}"
        else:
            search_name = display_number

        try:
            import httpx

            async with httpx.AsyncClient(timeout=30) as http:
                resp = await http.get(
                    f"{client.admin_api_base}/orders.json",
                    params={"name": search_name, "status": "any", "limit": 5},
                    headers={"X-Shopify-Access-Token": token},
                )
                resp.raise_for_status()
                orders = resp.json().get("orders") or []
        except Exception:
            logger.exception("Shopify order lookup failed for store %s", store.id)
            return None

        for order in orders:
            if normalize_email(recipient_email(order)) != normalized_email:
                continue
            tracking_number, carrier = tracking_from_payload(order)
            shipment_status = ""
            for fulfillment in order.get("fulfillments") or []:
                shipment_status = (fulfillment.get("shipment_status") or "").lower()
                if shipment_status:
                    break

            from app.tracking.payload_parser import (
                map_shipment_status_to_tracking_status,
                order_number_from_payload,
            )

            status = map_shipment_status_to_tracking_status(shipment_status, bool(tracking_number))
            self._sync._upsert(
                store_id=store.id,
                shopify_order_id=str(order.get("id") or ""),
                order_number=order_number_from_payload(order),
                customer_email=normalized_email,
                tracking_number=tracking_number,
                carrier=carrier,
                status=status,
                shipment_status=shipment_status,
                shopify_order=order,
            )
            self._db.commit()
            return self._find_row(
                store.id,
                normalize_order_number(order_number),
                normalized_email,
            )

        return None

    @staticmethod
    def _load_timeline(raw: str, *, shipment_status: str = "pending") -> list[dict[str, str]]:
        try:
            data = json.loads(raw or "[]")
            if isinstance(data, list):
                return normalize_timeline(data, shipment_status=shipment_status)
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    def _load_line_items(raw: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(raw or "[]")
            if isinstance(data, list):
                return [
                    {
                        "title": str(item.get("title") or "Item"),
                        "variant": str(item.get("variant") or ""),
                        "quantity": int(item.get("quantity") or 1),
                        "image_url": str(item.get("image_url") or ""),
                        "price": str(item.get("price") or ""),
                    }
                    for item in data
                    if isinstance(item, dict)
                ]
        except json.JSONDecodeError:
            pass
        return []

    @staticmethod
    def _should_refresh_carrier(row: OrderTracking) -> bool:
        if not row.tracking_number:
            return False
        if not row.last_updated_at:
            return True
        age = datetime.now(UTC) - row.last_updated_at.replace(tzinfo=UTC)
        return age > timedelta(minutes=_CARRIER_REFRESH_MINUTES)
