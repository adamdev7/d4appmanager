"""Persist order tracking from Shopify webhooks."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import OrderTracking
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

        if shipment_status or tracking_number:
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
