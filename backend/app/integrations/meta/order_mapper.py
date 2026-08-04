"""Map Shopify order webhook payloads to Meta CAPI Purchase events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from app.integrations.meta.hashing import hash_email, hash_location, hash_name, hash_phone


def _parse_event_time(order: dict[str, Any]) -> int:
    """Unix timestamp from paid/processed/created time."""
    for key in ("processed_at", "created_at", "updated_at"):
        raw = order.get(key)
        if not raw:
            continue
        try:
            # Shopify ISO8601 e.g. 2024-01-15T12:00:00-05:00
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (TypeError, ValueError):
            continue
    return int(datetime.now(UTC).timestamp())


def resolve_event_id(order: dict[str, Any], scheme: str) -> str:
    """Shared event_id for browser Pixel + CAPI deduplication."""
    scheme = (scheme or "order_id").strip().lower()
    if scheme == "checkout_token":
        token = order.get("checkout_token") or order.get("cart_token")
        if token:
            return str(token)
    if scheme == "order_name":
        name = str(order.get("name") or "").lstrip("#").strip()
        if name:
            return name
    # Default: Shopify order id (numeric string)
    return str(order.get("id") or "")


def _address_block(order: dict[str, Any]) -> dict[str, Any]:
    return order.get("shipping_address") or order.get("billing_address") or {}


def _extract_fbp_fbc(order: dict[str, Any]) -> tuple[str | None, str | None]:
    """Best-effort: note attributes / metafields if storefront captured cookies."""
    fbp = None
    fbc = None

    for attr in order.get("note_attributes") or []:
        if not isinstance(attr, dict):
            continue
        key = str(attr.get("name") or attr.get("key") or "").strip().lower()
        val = str(attr.get("value") or "").strip()
        if not val:
            continue
        if key in ("_fbp", "fbp", "fb_fbp"):
            fbp = val
        elif key in ("_fbc", "fbc", "fb_fbc"):
            fbc = val

    # Metafields sometimes appear as list on order (Admin API); webhooks rarely include them
    for mf in order.get("metafields") or []:
        if not isinstance(mf, dict):
            continue
        key = str(mf.get("key") or "").strip().lower()
        val = str(mf.get("value") or "").strip()
        if key == "fbp" and val:
            fbp = val
        elif key == "fbc" and val:
            fbc = val

    return fbp, fbc


def _event_source_url(order: dict[str, Any], shop_domain: str) -> str | None:
    for key in ("order_status_url", "landing_site"):
        url = order.get(key)
        if url and str(url).startswith("http"):
            return str(url)
    domain = (shop_domain or "").strip()
    if domain:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain
    return None


def build_purchase_event(
    order: dict[str, Any],
    *,
    shop_domain: str = "",
    event_id_scheme: str = "order_id",
) -> dict[str, Any]:
    """Build a single Meta CAPI Purchase event dict (ready for `data` array)."""
    customer = order.get("customer") or {}
    addr = _address_block(order)
    email = order.get("email") or customer.get("email")
    phone = order.get("phone") or customer.get("phone") or addr.get("phone")
    fn = customer.get("first_name") or addr.get("first_name")
    ln = customer.get("last_name") or addr.get("last_name")

    user_data: dict[str, Any] = {}
    em = hash_email(email)
    if em:
        user_data["em"] = [em]
    ph = hash_phone(phone)
    if ph:
        user_data["ph"] = [ph]
    h_fn = hash_name(fn)
    if h_fn:
        user_data["fn"] = [h_fn]
    h_ln = hash_name(ln)
    if h_ln:
        user_data["ln"] = [h_ln]

    for field, raw in (
        ("ct", addr.get("city")),
        ("st", addr.get("province_code") or addr.get("province")),
        ("zp", addr.get("zip")),
        ("country", addr.get("country_code") or addr.get("country")),
    ):
        hashed = hash_location(raw)
        if hashed:
            user_data[field] = [hashed]

    # Unhashed — improves Event Match Quality
    browser_ip = order.get("browser_ip")
    if browser_ip:
        user_data["client_ip_address"] = str(browser_ip)
    client_details = order.get("client_details") or {}
    ua = client_details.get("user_agent")
    if ua:
        user_data["client_user_agent"] = str(ua)

    fbp, fbc = _extract_fbp_fbc(order)
    if fbp:
        user_data["fbp"] = fbp
    if fbc:
        user_data["fbc"] = fbc

    contents: list[dict[str, Any]] = []
    content_ids: list[str] = []
    for item in order.get("line_items") or []:
        if not isinstance(item, dict):
            continue
        sku = item.get("sku") or item.get("variant_id") or item.get("product_id")
        cid = str(sku) if sku is not None else None
        if not cid:
            continue
        content_ids.append(cid)
        try:
            qty = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        try:
            price = float(item.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        contents.append({"id": cid, "quantity": qty, "item_price": price})

    try:
        value = float(order.get("total_price") or order.get("current_total_price") or 0)
    except (TypeError, ValueError):
        value = 0.0

    currency = str(order.get("currency") or order.get("presentment_currency") or "USD")
    order_id = str(order.get("id") or "")
    event_id = resolve_event_id(order, event_id_scheme)

    event: dict[str, Any] = {
        "event_name": "Purchase",
        "event_time": _parse_event_time(order),
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": {
            "currency": currency,
            "value": value,
            "content_ids": content_ids,
            "content_type": "product",
            "contents": contents,
            "order_id": order_id,
        },
    }

    source_url = _event_source_url(order, shop_domain)
    if source_url:
        # Prefer storefront origin without query junk when possible
        try:
            parsed = urlparse(source_url)
            if parsed.scheme and parsed.netloc:
                event["event_source_url"] = f"{parsed.scheme}://{parsed.netloc}/"
            else:
                event["event_source_url"] = source_url
        except Exception:
            event["event_source_url"] = source_url

    return event
