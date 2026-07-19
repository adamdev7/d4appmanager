"""Extract order / tracking fields from Shopify webhook payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_order_number(value: str | None) -> str:
    raw = (value or "").strip()
    if raw.startswith("#"):
        raw = raw[1:].strip()
    return raw


def order_number_variants(value: str | None) -> list[str]:
    """Return comparable forms (e.g. 1001 and #1001)."""
    normalized = normalize_order_number(value)
    if not normalized:
        return []
    variants = {normalized, f"#{normalized}"}
    return list(variants)


def recipient_email(payload: dict[str, Any]) -> str:
    customer = payload.get("customer") or {}
    email = customer.get("email") or payload.get("email") or payload.get("contact_email")
    if email and isinstance(email, str):
        return normalize_email(email)
    return ""


def order_number_from_payload(payload: dict[str, Any]) -> str:
    name = payload.get("name") or payload.get("order_number")
    if name is not None:
        return str(name).strip()
    order_id = payload.get("order_id")
    if order_id is not None:
        return str(order_id)
    return str(payload.get("id") or "").strip()


def tracking_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (tracking_number, carrier)."""
    number = ""
    if payload.get("tracking_number"):
        number = str(payload["tracking_number"]).strip()
    elif isinstance(payload.get("tracking_numbers"), list) and payload["tracking_numbers"]:
        number = str(payload["tracking_numbers"][0]).strip()

    carrier = str(payload.get("tracking_company") or payload.get("carrier") or "").strip()

    if not number:
        for fulfillment in payload.get("fulfillments") or []:
            if fulfillment.get("tracking_number"):
                number = str(fulfillment["tracking_number"]).strip()
                carrier = carrier or str(fulfillment.get("tracking_company") or "").strip()
                break

    return number, carrier


def shipment_status_from_payload(payload: dict[str, Any]) -> str:
    status = (payload.get("shipment_status") or "").strip().lower()
    if status:
        return status
    for fulfillment in payload.get("fulfillments") or []:
        fs = (fulfillment.get("shipment_status") or "").strip().lower()
        if fs:
            return fs
    return ""


def map_shipment_status_to_tracking_status(shipment_status: str, has_tracking: bool) -> str:
    if shipment_status == "delivered":
        return "delivered"
    if shipment_status in ("in_transit", "out_for_delivery", "confirmed"):
        return "in_transit"
    if has_tracking:
        return "in_transit"
    return "pending"


def timeline_event(
    status: str,
    description: str,
    *,
    at: datetime | None = None,
) -> dict[str, str]:
    ts = at or datetime.now(UTC)
    return {
        "status": status,
        "description": description,
        "at": ts.isoformat(),
    }


def format_money(amount: str | float | int | None, currency: str | None) -> str:
    """Format Shopify money for storefront display."""
    code = (currency or "USD").upper()
    try:
        value = float(amount or 0)
    except (TypeError, ValueError):
        return str(amount or "")
    if code == "USD":
        return f"${value:,.2f}"
    if code == "EUR":
        return f"€{value:,.2f}"
    if code == "GBP":
        return f"£{value:,.2f}"
    return f"{value:,.2f} {code}"


def _parse_placed_at(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _line_item_image_url(item: dict[str, Any]) -> str:
    image = item.get("image")
    if isinstance(image, dict) and image.get("src"):
        return str(image["src"]).strip()
    if isinstance(image, dict) and image.get("url"):
        return str(image["url"]).strip()
    return ""


def order_summary_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Extract order summary fields from a Shopify order (or webhook) payload."""
    currency = str(payload.get("currency") or payload.get("presentment_currency") or "USD")
    placed_at = _parse_placed_at(
        str(payload.get("created_at") or payload.get("processed_at") or "")
    )

    total_raw = payload.get("total_price") or payload.get("current_total_price")
    total_display = format_money(total_raw, currency)

    line_items: list[dict[str, Any]] = []
    for item in payload.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        qty = int(item.get("quantity") or 1)
        unit_price = item.get("price") or item.get("original_unit_price")
        line_items.append(
            {
                "title": str(item.get("title") or item.get("name") or "Item"),
                "variant": str(item.get("variant_title") or "").strip(),
                "quantity": qty,
                "image_url": _line_item_image_url(item),
                "price": format_money(
                    float(unit_price or 0) * qty if unit_price is not None else item.get("price"),
                    currency,
                ),
            }
        )

    return {
        "placed_at": placed_at,
        "total_display": total_display,
        "currency": currency,
        "line_items": line_items,
    }
