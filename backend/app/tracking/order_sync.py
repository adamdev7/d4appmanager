"""Persist order tracking from Shopify webhooks and Admin API sync."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value
from app.db.models import OrderTracking, Store, StoreStatus
from app.integrations.shopify.client import ShopifyClient
from app.tracking.payload_parser import (
    map_shipment_status_to_tracking_status,
    normalize_email,
    normalize_order_number,
    order_number_from_payload,
    order_summary_from_payload,
    recipient_email,
    shipment_status_from_payload,
    timeline_event,
    tracking_from_payload,
)

logger = logging.getLogger(__name__)

_TRACKING_TOPICS = frozenset(
    {
        "orders/create",
        "orders/paid",
        "orders/fulfilled",
        "fulfillments/create",
        "fulfillments/update",
    }
)

# How many recent Shopify orders to pull on a manual / auto sync.
_DEFAULT_SYNC_LIMIT = 100


class OrderTrackingSyncService:
    def __init__(self, db: Session) -> None:
        self._db = db

    def upsert_from_webhook(self, store_id: str, topic: str, payload: dict[str, Any]) -> OrderTracking | None:
        if topic not in _TRACKING_TOPICS:
            return None

        email = recipient_email(payload)
        order_number = order_number_from_payload(payload)
        shopify_order_id = str(payload.get("order_id") or payload.get("id") or "")

        if not order_number and shopify_order_id:
            existing = self._db.scalar(
                select(OrderTracking).where(
                    OrderTracking.store_id == store_id,
                    OrderTracking.shopify_order_id == shopify_order_id,
                )
            )
            if existing:
                order_number = existing.order_number_display
                if not email:
                    email = existing.customer_email

        if not order_number:
            return None

        tracking_number, carrier = tracking_from_payload(payload)
        shipment_status = shipment_status_from_payload(payload)
        status = map_shipment_status_to_tracking_status(shipment_status, bool(tracking_number))

        shopify_order = payload if payload.get("line_items") is not None or payload.get("created_at") else None

        return self._upsert(
            store_id=store_id,
            shopify_order_id=shopify_order_id,
            order_number=order_number,
            customer_email=email,
            tracking_number=tracking_number,
            carrier=carrier,
            status=status,
            shipment_status=shipment_status,
            shopify_order=shopify_order,
        )

    def upsert_from_shopify_order(self, store_id: str, order: dict[str, Any]) -> OrderTracking | None:
        """Upsert a full Shopify Admin order object into order_tracking."""
        email = recipient_email(order)
        order_number = order_number_from_payload(order)
        if not order_number or not email:
            return None

        tracking_number, carrier = tracking_from_payload(order)
        shipment_status = shipment_status_from_payload(order)
        status = map_shipment_status_to_tracking_status(shipment_status, bool(tracking_number))

        return self._upsert(
            store_id=store_id,
            shopify_order_id=str(order.get("id") or ""),
            order_number=order_number,
            customer_email=email,
            tracking_number=tracking_number,
            carrier=carrier,
            status=status,
            shipment_status=shipment_status,
            shopify_order=order,
        )

    async def sync_store_orders(
        self,
        store: Store,
        *,
        limit: int = _DEFAULT_SYNC_LIMIT,
    ) -> dict[str, int]:
        """
        Pull recent orders from the connected Shopify store and upsert them.
        Only syncs Shopify Admin orders for this store — no other sources.
        """
        if store.status != StoreStatus.CONNECTED.value:
            raise ValueError("Store is not connected to Shopify")
        if not store.access_token_encrypted:
            raise ValueError("Shopify access token is missing — reconnect the store")

        try:
            token = decrypt_value(store.access_token_encrypted)
        except ValueError as exc:
            raise ValueError("Could not read Shopify credentials — reconnect the store") from exc

        client = ShopifyClient(store.shop_domain, token)
        try:
            orders = await client.list_orders(limit=limit, status="any")
        except Exception:
            logger.exception("Shopify order list failed for store %s", store.id)
            raise ValueError("Could not fetch orders from Shopify. Try again in a moment.") from None

        created = 0
        updated = 0
        skipped = 0

        for order in orders:
            email = recipient_email(order)
            order_number = order_number_from_payload(order)
            if not order_number or not email:
                skipped += 1
                continue

            normalized_number = normalize_order_number(order_number)
            normalized_email = normalize_email(email)
            existed = self._db.scalar(
                select(OrderTracking).where(
                    OrderTracking.store_id == store.id,
                    OrderTracking.order_number_normalized == normalized_number,
                    OrderTracking.customer_email == normalized_email,
                )
            )
            row = self.upsert_from_shopify_order(store.id, order)
            if not row:
                skipped += 1
                continue
            if existed:
                updated += 1
            else:
                created += 1

        self._db.commit()
        return {
            "fetched": len(orders),
            "created": created,
            "updated": updated,
            "skipped": skipped,
        }

    def _upsert(
        self,
        *,
        store_id: str,
        shopify_order_id: str,
        order_number: str,
        customer_email: str,
        tracking_number: str,
        carrier: str,
        status: str,
        shipment_status: str,
        shopify_order: dict[str, Any] | None = None,
    ) -> OrderTracking | None:
        normalized_number = normalize_order_number(order_number)
        normalized_email = normalize_email(customer_email)

        row = self._db.scalar(
            select(OrderTracking).where(
                OrderTracking.store_id == store_id,
                OrderTracking.order_number_normalized == normalized_number,
                OrderTracking.customer_email == normalized_email,
            )
        )

        now = datetime.now(UTC)
        events = self._load_timeline(row.timeline_json if row else "[]")

        tracking_changed = bool(
            tracking_number and (not row or (row.tracking_number or "") != tracking_number)
        )
        status_changed = bool(not row or (row.status or "") != status)
        should_log = bool(shipment_status or tracking_number) and (
            not row or tracking_changed or status_changed
        )

        if should_log:
            desc_parts = []
            if tracking_number:
                desc_parts.append(f"Tracking: {tracking_number}")
            if shipment_status:
                desc_parts.append(f"Status: {shipment_status.replace('_', ' ')}")
            elif tracking_number:
                desc_parts.append("Tracking added")
            events.append(
                timeline_event(
                    status,
                    " — ".join(desc_parts) if desc_parts else "Shipment update",
                    at=now,
                )
            )
            events = events[-50:]

        if row:
            row.order_number_display = order_number
            if shopify_order_id:
                row.shopify_order_id = shopify_order_id
            if tracking_number:
                row.tracking_number = tracking_number
            if carrier:
                row.carrier = carrier
            row.status = status
            row.timeline_json = json.dumps(events)
            if should_log or shopify_order:
                row.last_updated_at = now
        else:
            row = OrderTracking(
                store_id=store_id,
                shopify_order_id=shopify_order_id or None,
                order_number_display=order_number,
                order_number_normalized=normalized_number,
                customer_email=normalized_email,
                tracking_number=tracking_number or None,
                carrier=carrier or None,
                status=status,
                timeline_json=json.dumps(events),
                last_updated_at=now,
            )
            self._db.add(row)

        if shopify_order:
            self._apply_order_summary(row, shopify_order)

        self._db.flush()
        return row

    @staticmethod
    def _apply_order_summary(row: OrderTracking, shopify_order: dict[str, Any]) -> None:
        summary = order_summary_from_payload(shopify_order)
        placed_at = summary.get("placed_at")
        if placed_at:
            row.order_placed_at = placed_at
        total_display = summary.get("total_display")
        if total_display:
            row.order_total_display = str(total_display)
        currency = summary.get("currency")
        if currency:
            row.order_currency = str(currency)
        line_items = summary.get("line_items")
        if isinstance(line_items, list) and line_items:
            row.line_items_json = json.dumps(line_items)

    @staticmethod
    def _load_timeline(raw: str) -> list[dict[str, str]]:
        try:
            data = json.loads(raw or "[]")
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            logger.warning("Invalid timeline JSON in order_tracking row")
        return []
