"""Shopify order + shipment facts the assistant can use when answering a customer.

Both the inbox "related orders" panel and the AI reply prompt read from here so the
draft never contradicts what the Tracking module shows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_email_assistant.order_link import extract_order_numbers
from app.db.models import OrderTracking, Store
from app.tracking.payload_parser import (
    normalize_email,
    normalize_order_number,
    order_number_variants,
)
from app.tracking.track_service import TrackOrderService

logger = logging.getLogger(__name__)

MAX_ORDERS_IN_PROMPT = 4
MAX_TIMELINE_EVENTS = 4


@dataclass
class MatchedOrder:
    row: OrderTracking
    match_reason: str


@dataclass
class TrackingLink:
    """Everything needed to render a prefilled "Track my order" button."""

    url: str
    order_number: str
    tracking_number: str
    carrier: str


def public_order_number(raw: str | None) -> str:
    """Order number as the customer types it on the storefront (no leading #)."""
    return (raw or "").strip().lstrip("#").strip()


def build_tracking_page_url(page_url: str | None, order_number: str, email: str) -> str | None:
    """Prefill the storefront track-your-order page for this order."""
    base = (page_url or "").strip()
    number = public_order_number(order_number)
    address = (email or "").strip()
    if not base or not number or not address:
        return None

    parsed = urlparse(base if "://" in base else f"https://{base}")
    if not parsed.netloc:
        return None

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    # `order_number`/`email` match the public /api/track-order contract; `order` is
    # included because storefront themes commonly read the shorter name.
    query.update({"order_number": number, "order": number, "email": address})
    return urlunparse(parsed._replace(query=urlencode(query)))


def is_shipped(row: OrderTracking) -> bool:
    return bool((row.tracking_number or "").strip())


def shipment_status_label(row: OrderTracking) -> str:
    if not is_shipped(row):
        return "Not shipped yet"
    if (row.status or "").strip().lower() == "delivered":
        return "Delivered"
    return "On the way"


def _json_list(raw: str | None) -> list:
    try:
        data = json.loads(raw or "[]")
    except (json.JSONDecodeError, TypeError):
        return []
    return data if isinstance(data, list) else []


async def find_customer_orders(
    db: Session,
    store: Store,
    *,
    customer_email: str,
    subject: str = "",
    body: str = "",
    limit: int = 12,
    live_lookup: bool = True,
) -> list[MatchedOrder]:
    """Orders belonging to this customer, plus any order number quoted in the email."""
    address = normalize_email(customer_email)
    mentioned = extract_order_numbers(subject, body)
    by_id: dict[str, MatchedOrder] = {}

    if address:
        rows = db.scalars(
            select(OrderTracking)
            .where(
                OrderTracking.store_id == store.id,
                OrderTracking.customer_email == address,
            )
            .order_by(OrderTracking.order_placed_at.desc().nullslast())
            .limit(limit)
        ).all()
        for row in rows:
            by_id[row.id] = MatchedOrder(row=row, match_reason="customer_email")

    for number in mentioned:
        variants = {normalize_order_number(v) for v in order_number_variants(number)}
        variants.discard("")
        if not variants:
            continue
        row = db.scalar(
            select(OrderTracking)
            .where(
                OrderTracking.store_id == store.id,
                OrderTracking.order_number_normalized.in_(variants),
            )
            .order_by(OrderTracking.order_placed_at.desc().nullslast())
            .limit(1)
        )
        if row and row.id not in by_id:
            reason = (
                "customer_email"
                if address and row.customer_email == address
                else "order_number_in_email"
            )
            by_id[row.id] = MatchedOrder(row=row, match_reason=reason)

    if live_lookup and address:
        missing = [
            number
            for number in mentioned
            if not any(
                normalize_order_number(m.row.order_number_display) == number
                for m in by_id.values()
            )
        ]
        tracker = TrackOrderService(db)
        for number in missing[:5]:
            try:
                row = await tracker._fetch_from_shopify(store, number, address)
            except Exception:
                logger.exception("Shopify order lookup failed for %s", number)
                continue
            if row and row.id not in by_id:
                by_id[row.id] = MatchedOrder(row=row, match_reason="order_number_in_email")

    return sorted(
        by_id.values(),
        key=lambda m: (
            m.row.order_placed_at.isoformat() if m.row.order_placed_at else "",
            m.row.last_updated_at.isoformat() if m.row.last_updated_at else "",
        ),
        reverse=True,
    )[:limit]


async def refresh_shipment_tracking(
    db: Session,
    store: Store,
    matched: list[MatchedOrder],
    *,
    limit: int = 2,
) -> None:
    """Pull fresh carrier status for the orders we are about to quote.

    TrackOrderService throttles carrier calls internally, so this is safe to run on
    every reply. Objects are refreshed by the commit inside track().
    """
    tracker = TrackOrderService(db)
    refreshed = 0
    for item in matched:
        if refreshed >= limit:
            return
        if not is_shipped(item.row):
            continue
        try:
            await tracker.track(
                store_id=store.id,
                order_number=item.row.order_number_display,
                email=item.row.customer_email,
            )
        except Exception:
            logger.exception(
                "Tracking refresh failed for order %s", item.row.order_number_display
            )
            continue
        refreshed += 1


def pick_tracking_link(
    matched: list[MatchedOrder],
    *,
    page_url: str | None,
    customer_email: str,
) -> TrackingLink | None:
    """Best order to offer a tracking button for, if any is actually trackable."""
    if not page_url:
        return None

    shipped = [m for m in matched if is_shipped(m.row)]
    if not shipped:
        return None

    # An order the customer explicitly quoted wins over their newest order.
    quoted = [m for m in shipped if m.match_reason == "order_number_in_email"]
    chosen = (quoted or shipped)[0].row

    # The storefront page verifies order number + email, so use the address on the
    # order rather than the sender when they differ (forwarded mail, alias, etc).
    address = (chosen.customer_email or customer_email or "").strip()
    url = build_tracking_page_url(page_url, chosen.order_number_display, address)
    if not url:
        return None

    return TrackingLink(
        url=url,
        order_number=public_order_number(chosen.order_number_display),
        tracking_number=(chosen.tracking_number or "").strip(),
        carrier=(chosen.carrier or "").strip(),
    )


def _has_button(row: OrderTracking, tracking_link: TrackingLink | None) -> bool:
    return (
        tracking_link is not None
        and public_order_number(row.order_number_display) == tracking_link.order_number
    )


def _format_order(matched: MatchedOrder, *, tracking_link: TrackingLink | None) -> str:
    row = matched.row
    lines = [f"Order {row.order_number_display or '(unknown number)'}"]

    if row.order_placed_at:
        lines.append(f"- Placed: {row.order_placed_at.date().isoformat()}")
    if row.order_total_display:
        currency = f" {row.order_currency}" if row.order_currency else ""
        lines.append(f"- Total: {row.order_total_display}{currency}")
    if row.customer_name:
        lines.append(f"- Customer: {row.customer_name}")
    if row.shopify_financial_status:
        lines.append(f"- Payment status: {row.shopify_financial_status}")
    if row.shopify_fulfillment_status:
        lines.append(f"- Fulfillment status: {row.shopify_fulfillment_status}")

    lines.append(f"- Shipment: {shipment_status_label(row)}")
    if is_shipped(row):
        carrier = row.carrier or "carrier not specified"
        lines.append(f"- Tracking number: {row.tracking_number} ({carrier})")
        if _has_button(row, tracking_link):
            lines.append(
                "- A prefilled tracking link for this order is attached to your reply as a "
                '"Track my order" button. Refer to the button; never paste a raw URL.'
            )

    items = _json_list(row.line_items_json)
    if items:
        names = []
        for item in items[:5]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue
            qty = item.get("quantity")
            names.append(f"{title} x{qty}" if qty else title)
        if names:
            lines.append(f"- Items: {', '.join(names)}")

    timeline = [e for e in _json_list(row.timeline_json) if isinstance(e, dict)]
    if timeline:
        lines.append("- Latest shipment updates (newest first):")
        for event in timeline[:MAX_TIMELINE_EVENTS]:
            description = str(
                event.get("description") or event.get("message") or event.get("status") or ""
            ).strip()
            if not description:
                continue
            when = str(event.get("at") or event.get("date") or "").strip()
            location = str(event.get("location") or "").strip()
            suffix = " — ".join(part for part in (when, location) if part)
            lines.append(f"  · {description}{f' ({suffix})' if suffix else ''}")

    if matched.match_reason == "order_number_in_email":
        lines.append("- This is the order number the customer quoted in their email.")

    return "\n".join(lines)


def format_orders_for_prompt(
    matched: list[MatchedOrder],
    *,
    tracking_link: TrackingLink | None = None,
) -> str:
    """Order facts block injected into the reply prompt. Empty string when nothing matched."""
    if not matched:
        return ""

    blocks = [
        _format_order(m, tracking_link=tracking_link)
        for m in matched[:MAX_ORDERS_IN_PROMPT]
    ]
    header = (
        "Verified Shopify order data for this customer (from the store, not the email). "
        "Treat these as facts and use them instead of asking the customer to repeat details."
    )
    return f"{header}\n\n" + "\n\n".join(blocks)
