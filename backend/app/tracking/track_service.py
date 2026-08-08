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
    emails_match,
    normalize_email,
    normalize_order_number,
    order_name_matches,
    order_number_variants,
    recipient_email,
)

logger = logging.getLogger(__name__)

_CARRIER_REFRESH_MINUTES = 30
_NOT_SHIPPED_MESSAGE = (
    "Your order has been placed and is being prepared. It has not shipped yet."
)


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

        if not emails_match(row.customer_email, normalized_email):
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
                    await CarrierEnrichmentService(self._db).apply_enrichment_and_sync(
                        store_id, row, enriched
                    )
                    status = row.status
                    carrier = row.carrier or carrier
                    events = self._load_timeline(row.timeline_json, shipment_status=status)
                    last_updated = row.last_updated_at
                    self._db.commit()

        return self._row_to_response(row, tracking_number, carrier, status, events, last_updated)

    @staticmethod
    def _customer_facing_fields(
        *,
        tracking_number: str,
        status: str,
    ) -> dict[str, Any]:
        """Labels/messages for the Shopify track page (including unshipped orders)."""
        shipped = bool((tracking_number or "").strip())
        if not shipped:
            return {
                "shipped": False,
                "status": "pending",
                "status_label": "Not shipped yet",
                "message": _NOT_SHIPPED_MESSAGE,
            }
        if status == "delivered":
            return {
                "shipped": True,
                "status": "delivered",
                "status_label": "Delivered",
                "message": "Your order has been delivered.",
            }
        return {
            "shipped": True,
            "status": status if status in ("in_transit", "delivered") else "in_transit",
            "status_label": "On the way",
            "message": "Your order has shipped and is on the way.",
        }

    @staticmethod
    def _ensure_not_shipped_timeline(
        events: list[dict[str, str]],
        *,
        shipped: bool,
        order_placed_at: datetime | None,
        last_updated: datetime | None,
        updated_at: datetime | None,
    ) -> list[dict[str, str]]:
        if shipped or events:
            return events
        at = order_placed_at or last_updated or updated_at or datetime.now(UTC)
        return [
            {
                "status": "pending",
                "description": "Order placed — not shipped yet",
                "location": "",
                "at": at.isoformat(),
            }
        ]

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
        facing = TrackOrderService._customer_facing_fields(
            tracking_number=tracking_number,
            status=status,
        )
        timeline = TrackOrderService._ensure_not_shipped_timeline(
            events,
            shipped=bool(facing["shipped"]),
            order_placed_at=row.order_placed_at,
            last_updated=last_updated,
            updated_at=row.updated_at,
        )
        return {
            "order_number": row.order_number_display,
            "order_placed_at": row.order_placed_at.isoformat() if row.order_placed_at else None,
            "order_total": row.order_total_display,
            "currency": row.order_currency,
            "line_items": line_items,
            "tracking_number": tracking_number or None,
            "carrier": carrier or None,
            "status": facing["status"],
            "shipped": facing["shipped"],
            "status_label": facing["status_label"],
            "message": facing["message"],
            "timeline": timeline,
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

        try:
            client = ShopifyClient(store.shop_domain, token)
            orders = await client.find_orders_by_name(order_number, limit=5)
        except Exception:
            logger.exception("Shopify order summary refresh failed for store %s", store.id)
            return None

        for order in orders:
            if not emails_match(recipient_email(order), normalized_email):
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
        variants |= {v.casefold() for v in list(variants) if v}
        variants.discard("")
        if not variants or not normalized_email:
            return None

        # Prefer exact normalized + cleaned email match.
        rows = self._db.scalars(
            select(OrderTracking).where(
                OrderTracking.store_id == store_id,
                or_(
                    OrderTracking.order_number_normalized.in_(variants),
                    OrderTracking.order_number_display.in_(
                        {v for v in order_number_variants(normalized_number) if v}
                    ),
                ),
            )
        ).all()

        for row in rows:
            if emails_match(row.customer_email, normalized_email) and (
                normalize_order_number(row.order_number_normalized) in variants
                or order_name_matches(row.order_number_display, normalized_number)
                or order_name_matches(row.order_number_normalized, normalized_number)
            ):
                return row

        # Fallback: same email, match order name flexibly among recent rows.
        email_rows = self._db.scalars(
            select(OrderTracking)
            .where(OrderTracking.store_id == store_id)
            .order_by(OrderTracking.updated_at.desc())
            .limit(300)
        ).all()
        for row in email_rows:
            if not emails_match(row.customer_email, normalized_email):
                continue
            if order_name_matches(row.order_number_display, normalized_number):
                return row
            if order_name_matches(row.order_number_normalized, normalized_number):
                return row
        return None

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
        # Search with cleaned number (with and without # handled inside client).
        search_value = normalize_order_number(order_number) or order_number
        try:
            orders = await client.find_orders_by_name(search_value, limit=10)
            if not orders and search_value != order_number.strip():
                orders = await client.find_orders_by_name(order_number, limit=10)
        except Exception:
            logger.exception("Shopify order lookup failed for store %s", store.id)
            return None

        if not orders:
            logger.info(
                "No Shopify order matched name %r for store %s",
                order_number,
                store.id,
            )
            return None

        for order in orders:
            if not emails_match(recipient_email(order), normalized_email):
                continue
            self._sync.upsert_from_shopify_order(store.id, order)
            self._db.commit()
            return self._find_row(
                store.id,
                normalize_order_number(order_number),
                normalized_email,
            )

        logger.info(
            "Shopify order(s) matched name %r for store %s but email did not match",
            order_number,
            store.id,
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
    def _timeline_needs_carrier_enrichment(row: OrderTracking) -> bool:
        """True when we only have Shopify placeholder events (not 17TRACK/YunExpress yet)."""
        try:
            events = json.loads(row.timeline_json or "[]")
        except json.JSONDecodeError:
            return True
        if not isinstance(events, list) or not events:
            return True
        if len(events) == 1:
            desc = str((events[0] or {}).get("description") or "").lower()
            if "shipper added tracking" in desc or "tracking added" in desc:
                return True
        return False

    @staticmethod
    def _should_refresh_carrier(row: OrderTracking) -> bool:
        if not row.tracking_number:
            return False
        # Always enrich once after Shopify sync — don't wait 30m on placeholder timelines.
        if TrackOrderService._timeline_needs_carrier_enrichment(row):
            return True
        if not row.last_updated_at:
            return True
        age = datetime.now(UTC) - row.last_updated_at.replace(tzinfo=UTC)
        return age > timedelta(minutes=_CARRIER_REFRESH_MINUTES)
