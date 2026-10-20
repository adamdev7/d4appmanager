"""Shopify mandatory compliance webhooks (customers/data_request, customers/redact, shop/redact)."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    EmailSendLog,
    InboxEmail,
    MetaCapiEventLog,
    OrderTracking,
    ShopifyPendingInstall,
    Store,
    WebhookLog,
)

logger = logging.getLogger(__name__)

COMPLIANCE_TOPICS = frozenset({"customers/data_request", "customers/redact", "shop/redact"})


def handle_compliance_webhook(db: Session, topic: str, shop_domain: str, payload: dict[str, Any]) -> dict:
    store = db.scalar(select(Store).where(Store.shop_domain == shop_domain)) if shop_domain else None

    if topic == "customers/data_request":
        # Customer data SkyScale Manager holds comes from the merchant's own Shopify orders and inbox;
        # the merchant fulfils the request from Shopify and SkyScale Manager's Tracking / Inbox views.
        logger.info(
            "Shopify customer data request for %s (request %s)",
            shop_domain,
            (payload.get("data_request") or {}).get("id"),
        )
        return {"topic": topic, "store_found": bool(store)}

    if topic == "customers/redact":
        removed = redact_customer(db, store, shop_domain, payload) if store else {}
        return {"topic": topic, "store_found": bool(store), "removed": removed}

    if topic == "shop/redact":
        redact_shop(db, shop_domain)
        return {"topic": topic, "store_found": bool(store)}

    return {"topic": topic, "ignored": True}


def redact_customer(
    db: Session, store: Store, shop_domain: str, payload: dict[str, Any]
) -> dict[str, int]:
    customer = payload.get("customer") or {}
    email = str(customer.get("email") or "").strip().lower()
    order_ids = [str(i) for i in payload.get("orders_to_redact") or [] if i is not None]

    removed: dict[str, int] = {}

    tracking_match = []
    if email:
        tracking_match.append(func.lower(OrderTracking.customer_email) == email)
    if order_ids:
        tracking_match.append(OrderTracking.shopify_order_id.in_(order_ids))
    if tracking_match:
        removed["order_tracking"] = db.execute(
            delete(OrderTracking).where(OrderTracking.store_id == store.id, or_(*tracking_match))
        ).rowcount or 0

    if order_ids:
        removed["meta_capi_events"] = db.execute(
            delete(MetaCapiEventLog).where(
                MetaCapiEventLog.store_id == store.id,
                MetaCapiEventLog.shopify_order_id.in_(order_ids),
            )
        ).rowcount or 0

    if email:
        removed["email_sends"] = db.execute(
            delete(EmailSendLog).where(
                EmailSendLog.store_id == store.id,
                func.lower(EmailSendLog.recipient) == email,
            )
        ).rowcount or 0
        removed["inbox_emails"] = db.execute(
            delete(InboxEmail).where(
                InboxEmail.store_id == store.id,
                func.lower(InboxEmail.sender_email) == email,
            )
        ).rowcount or 0
        removed["webhook_logs"] = db.execute(
            delete(WebhookLog).where(
                WebhookLog.shop_domain == shop_domain,
                func.lower(WebhookLog.payload_preview).contains(email),
            )
        ).rowcount or 0

    db.commit()
    return removed


def redact_shop(db: Session, shop_domain: str) -> None:
    """Remove everything SkyScale Manager stores for a shop (sent 48h after uninstall)."""
    if not shop_domain:
        return
    # Core DELETE so ON DELETE CASCADE removes the store's tracking, automation, analytics, etc.
    db.execute(delete(Store).where(Store.shop_domain == shop_domain))
    db.execute(delete(ShopifyPendingInstall).where(ShopifyPendingInstall.shop_domain == shop_domain))
    db.execute(delete(WebhookLog).where(WebhookLog.shop_domain == shop_domain))
    db.commit()
