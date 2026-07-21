"""Push carrier "delivered" status back to Shopify as a fulfillment event."""

from __future__ import annotations

import json
import logging
import re

from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value
from app.db.models import OrderTracking, Store, StoreStatus
from app.integrations.shopify.client import ShopifyClient
from app.tracking.credentials import get_or_create_tracking_settings

logger = logging.getLogger(__name__)

_NUMERIC_ID = re.compile(r"^\d+$")


def _load_fulfillments(row: OrderTracking) -> list[dict]:
    try:
        raw = json.loads(row.fulfillments_json or "[]")
    except json.JSONDecodeError:
        return []
    return [f for f in raw if isinstance(f, dict)]


def _fulfillment_targets(row: OrderTracking) -> list[dict]:
    """Fulfillments that should receive a delivered event."""
    tracking = (row.tracking_number or "").strip().lower()
    targets: list[dict] = []
    for fulfillment in _load_fulfillments(row):
        fid = str(fulfillment.get("id") or "").strip()
        if not fid or not _NUMERIC_ID.match(fid):
            continue
        if (fulfillment.get("shipment_status") or "").strip().lower() == "delivered":
            continue
        f_track = (fulfillment.get("tracking_number") or "").strip().lower()
        if tracking and f_track and f_track != tracking:
            continue
        targets.append(fulfillment)
    return targets


def _mark_local_delivered(row: OrderTracking, fulfillment_ids: set[str]) -> None:
    fulfillments = _load_fulfillments(row)
    changed = False
    for fulfillment in fulfillments:
        fid = str(fulfillment.get("id") or "").strip()
        if fid in fulfillment_ids:
            fulfillment["shipment_status"] = "delivered"
            changed = True
    if changed:
        row.fulfillments_json = json.dumps(fulfillments)


async def sync_delivered_to_shopify(
    db: Session,
    store_id: str,
    row: OrderTracking,
    previous_status: str | None,
) -> bool:
    """When carrier enrichment reaches delivered, mark matching Shopify fulfillments delivered.

    Idempotent: skips fulfillments already marked delivered locally, and no-ops when
    the row was already delivered before this enrichment (unless Shopify still lags).
    """
    new_status = (row.status or "").strip().lower()
    if new_status != "delivered":
        return False

    settings = get_or_create_tracking_settings(db, store_id)
    if not getattr(settings, "sync_delivered_to_shopify", True):
        return False

    targets = _fulfillment_targets(row)
    if not targets:
        if (previous_status or "").strip().lower() == "delivered":
            return False
        logger.info(
            "Carrier delivered for order %s but no Shopify fulfillment id to update",
            row.order_number_display,
        )
        return False

    store = db.get(Store, store_id)
    if not store or store.status != StoreStatus.CONNECTED.value:
        return False
    if not store.access_token_encrypted:
        logger.warning("Store %s has no access token; cannot mark delivered on Shopify", store_id)
        return False

    try:
        token = decrypt_value(store.access_token_encrypted)
    except Exception:
        logger.exception("Failed to decrypt access token for store %s", store_id)
        return False

    client = ShopifyClient(store.shop_domain, token)
    order_id = (row.shopify_order_id or "").strip() or None
    synced_ids: set[str] = set()

    for fulfillment in targets:
        fid = str(fulfillment.get("id")).strip()
        try:
            await client.create_fulfillment_event(
                fid,
                status="delivered",
                message="Delivered (synced from carrier tracking via App Manager)",
                order_id=order_id,
            )
            synced_ids.add(fid)
            logger.info(
                "Marked Shopify fulfillment %s delivered for order %s",
                fid,
                row.order_number_display,
            )
        except PermissionError:
            logger.exception(
                "Shopify denied writing fulfillment event for store %s "
                "(re-install app with write_fulfillments scope)",
                store_id,
            )
            return False
        except Exception:
            logger.exception(
                "Failed to mark Shopify fulfillment %s delivered for order %s",
                fid,
                row.order_number_display,
            )

    if synced_ids:
        _mark_local_delivered(row, synced_ids)
        return True
    return False
