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
    name = payload.get("name")
    if name is not None and str(name).strip():
        return str(name).strip()
    # Fulfillment webhooks have order_id but not a customer-facing order name.
    if payload.get("order_id") is not None:
        return ""
    order_number = payload.get("order_number")
    if order_number is not None:
        return str(order_number).strip()
    return ""


def customer_name_from_payload(payload: dict[str, Any]) -> str:
    customer = payload.get("customer") or {}
    if isinstance(customer, dict):
        first = str(customer.get("first_name") or "").strip()
        last = str(customer.get("last_name") or "").strip()
        full = f"{first} {last}".strip()
        if full:
            return full
    shipping = payload.get("shipping_address") or {}
    if isinstance(shipping, dict):
        name = str(shipping.get("name") or "").strip()
        if name:
            return name
        first = str(shipping.get("first_name") or "").strip()
        last = str(shipping.get("last_name") or "").strip()
        full = f"{first} {last}".strip()
        if full:
            return full
    return ""


def shopify_financial_status(payload: dict[str, Any]) -> str:
    return str(payload.get("financial_status") or "").strip().lower()


def shopify_fulfillment_status(payload: dict[str, Any]) -> str:
    raw = payload.get("fulfillment_status")
    if raw is None or raw == "":
        # Fulfillment webhook payloads use "status" (success, cancelled, …)
        if payload.get("tracking_number") is not None or payload.get("order_id") is not None:
            return ""
        return "unfulfilled"
    return str(raw).strip().lower()


def _normalize_fulfillment(raw: dict[str, Any]) -> dict[str, Any] | None:
    fulfillment_id = str(raw.get("id") or "").strip()
    tracking_number = ""
    if raw.get("tracking_number"):
        tracking_number = str(raw["tracking_number"]).strip()
    elif isinstance(raw.get("tracking_numbers"), list) and raw["tracking_numbers"]:
        tracking_number = str(raw["tracking_numbers"][0]).strip()

    carrier = str(raw.get("tracking_company") or "").strip()
    shipment_status = str(raw.get("shipment_status") or "").strip().lower()
    tracking_url = str(raw.get("tracking_url") or "").strip()
    if not tracking_url and isinstance(raw.get("tracking_urls"), list) and raw["tracking_urls"]:
        tracking_url = str(raw["tracking_urls"][0]).strip()

    status = str(raw.get("status") or "").strip().lower()
    created_at = str(raw.get("created_at") or "").strip() or None
    updated_at = str(raw.get("updated_at") or "").strip() or None

    item_titles: list[str] = []
    for item in raw.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        qty = int(item.get("quantity") or 1)
        if title:
            item_titles.append(f"{title} × {qty}" if qty > 1 else title)

    if not fulfillment_id and not tracking_number and not status:
        return None

    return {
        "id": fulfillment_id or tracking_number or created_at or "fulfillment",
        "status": status or "success",
        "shipment_status": shipment_status,
        "tracking_number": tracking_number,
        "carrier": carrier,
        "tracking_url": tracking_url,
        "created_at": created_at,
        "updated_at": updated_at,
        "items": item_titles,
    }


def fulfillments_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract Shopify fulfillments (order payload or single fulfillment webhook)."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    raw_list = payload.get("fulfillments")
    if isinstance(raw_list, list):
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_fulfillment(raw)
            if not normalized:
                continue
            key = str(normalized["id"])
            if key in seen:
                continue
            seen.add(key)
            results.append(normalized)
        return results

    # fulfillments/create or fulfillments/update webhook body
    is_fulfillment_event = payload.get("order_id") is not None and payload.get("name") is None
    if is_fulfillment_event:
        normalized = _normalize_fulfillment(payload)
        if normalized:
            results.append(normalized)

    return results


def merge_fulfillments(
    existing: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for item in existing:
        key = str(item.get("id") or item.get("tracking_number") or "")
        if key:
            by_id[key] = item
    for item in incoming:
        key = str(item.get("id") or item.get("tracking_number") or "")
        if not key:
            continue
        prev = by_id.get(key) or {}
        merged = dict(prev)
        for k, v in item.items():
            if v not in (None, "", []):
                merged[k] = v
        by_id[key] = merged
    return list(by_id.values())


def tracking_from_payload(payload: dict[str, Any]) -> tuple[str, str]:
    """Return (tracking_number, carrier) — prefers latest fulfillment with tracking."""
    fulfillments = fulfillments_from_payload(payload)
    for fulfillment in reversed(fulfillments):
        number = str(fulfillment.get("tracking_number") or "").strip()
        if number:
            return number, str(fulfillment.get("carrier") or "").strip()

    number = ""
    if payload.get("tracking_number"):
        number = str(payload["tracking_number"]).strip()
    elif isinstance(payload.get("tracking_numbers"), list) and payload["tracking_numbers"]:
        number = str(payload["tracking_numbers"][0]).strip()

    carrier = str(payload.get("tracking_company") or payload.get("carrier") or "").strip()
    return number, carrier


def shipment_status_from_payload(payload: dict[str, Any]) -> str:
    status = (payload.get("shipment_status") or "").strip().lower()
    if status:
        return status
    for fulfillment in fulfillments_from_payload(payload):
        fs = str(fulfillment.get("shipment_status") or "").strip().lower()
        if fs:
            return fs
    return ""


def map_shipment_status_to_tracking_status(
    shipment_status: str,
    has_tracking: bool,
    *,
    shopify_fulfillment_status: str = "",
) -> str:
    if shipment_status == "delivered":
        return "delivered"
    if shipment_status in ("in_transit", "out_for_delivery", "confirmed"):
        return "in_transit"
    if has_tracking:
        return "in_transit"
    if shopify_fulfillment_status in ("fulfilled", "partial"):
        return "in_transit" if has_tracking else "pending"
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
