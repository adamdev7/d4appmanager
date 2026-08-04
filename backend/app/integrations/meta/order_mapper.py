"""Map Shopify order/checkout payloads to Meta CAPI events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qs, urlparse

from app.integrations.meta.hashing import hash_email, hash_location, hash_name, hash_phone, sha256_normalize


def _parse_event_time(payload: dict[str, Any]) -> int:
    """Unix timestamp from paid/processed/created time."""
    for key in ("processed_at", "created_at", "updated_at", "completed_at"):
        raw = payload.get(key)
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return int(dt.timestamp())
        except (TypeError, ValueError):
            continue
    return int(datetime.now(UTC).timestamp())


def resolve_event_id(order: dict[str, Any], scheme: str) -> str:
    """Shared event_id for browser Pixel + CAPI deduplication."""
    scheme = (scheme or "order_id").strip().lower()
    if scheme == "checkout_token":
        token = order.get("checkout_token") or order.get("cart_token") or order.get("token")
        if token:
            return str(token)
    if scheme == "order_name":
        name = str(order.get("name") or "").lstrip("#").strip()
        if name:
            return name
    return str(order.get("id") or "")


def _address_block(payload: dict[str, Any]) -> dict[str, Any]:
    return (
        payload.get("shipping_address")
        or payload.get("billing_address")
        or payload.get("default_address")
        or {}
    )


def _note_attr_map(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for attr in payload.get("note_attributes") or []:
        if not isinstance(attr, dict):
            continue
        key = str(attr.get("name") or attr.get("key") or "").strip()
        val = str(attr.get("value") or "").strip()
        if key and val:
            out[key] = val
            out[key.lower()] = val
    # Cart/checkout attributes sometimes appear as `attributes` dict
    attrs = payload.get("attributes")
    if isinstance(attrs, dict):
        for key, val in attrs.items():
            if key and val is not None and str(val).strip():
                out[str(key)] = str(val).strip()
                out[str(key).lower()] = str(val).strip()
    return out


def _cookie_from_notes(notes: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        val = notes.get(key) or notes.get(key.lower())
        if val:
            return val
    return None


def _fbclid_from_url(url: str | None) -> str | None:
    if not url:
        return None
    try:
        qs = parse_qs(urlparse(str(url)).query)
        vals = qs.get("fbclid") or []
        return vals[0] if vals else None
    except Exception:
        return None


def _build_fbc(fbclid: str, event_time: int | None = None) -> str:
    """Meta fbc format: fb.1.{creation_time_ms}.{fbclid}."""
    ts_ms = int((event_time or int(datetime.now(UTC).timestamp())) * 1000)
    return f"fb.1.{ts_ms}.{fbclid.strip()}"


def _extract_fbp_fbc(
    payload: dict[str, Any], *, event_time: int | None = None
) -> tuple[str | None, str | None, str | None]:
    """Return (fbp, fbc, fbclid) from notes/metafields/landing URL."""
    notes = _note_attr_map(payload)
    fbp = _cookie_from_notes(notes, "_fbp", "fbp", "fb_fbp")
    fbc = _cookie_from_notes(notes, "_fbc", "fbc", "fb_fbc")
    fbclid = _cookie_from_notes(notes, "fbclid", "_fbclid")

    for mf in payload.get("metafields") or []:
        if not isinstance(mf, dict):
            continue
        key = str(mf.get("key") or "").strip().lower()
        val = str(mf.get("value") or "").strip()
        if not val:
            continue
        if key == "fbp":
            fbp = val
        elif key == "fbc":
            fbc = val
        elif key == "fbclid":
            fbclid = val

    if not fbclid:
        for url_key in ("landing_site", "order_status_url", "abandoned_checkout_url", "web_url"):
            fbclid = _fbclid_from_url(payload.get(url_key))
            if fbclid:
                break

    # Synthesize fbc from fbclid when cookie missing (valid Meta pattern)
    if not fbc and fbclid:
        fbc = _build_fbc(fbclid, event_time)

    return fbp, fbc, fbclid


def _utm_from_landing(landing: str | None, notes: dict[str, str]) -> dict[str, str]:
    utm: dict[str, str] = {}
    for key in (
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
    ):
        val = notes.get(key) or notes.get(key.lower())
        if val:
            utm[key] = val
    if landing:
        try:
            qs = parse_qs(urlparse(landing).query)
            for key in utm.keys() if False else (
                "utm_source",
                "utm_medium",
                "utm_campaign",
                "utm_content",
                "utm_term",
            ):
                if key in utm:
                    continue
                vals = qs.get(key) or []
                if vals:
                    utm[key] = vals[0]
        except Exception:
            pass
    return utm


def _event_source_url(payload: dict[str, Any], shop_domain: str) -> str | None:
    """Prefer full landing_site (keeps fbclid / UTMs)."""
    notes = _note_attr_map(payload)
    note_landing = notes.get("meta_landing") or notes.get("landing_site")
    candidates = [
        note_landing,
        payload.get("landing_site"),
        payload.get("abandoned_checkout_url"),
        payload.get("order_status_url"),
        payload.get("web_url"),
    ]
    for url in candidates:
        if not url:
            continue
        raw = str(url).strip()
        if raw.startswith("/"):
            domain = (shop_domain or "").strip()
            if domain and not domain.startswith("http"):
                domain = f"https://{domain}"
            return f"{domain.rstrip('/')}{raw}"
        if raw.startswith("http"):
            return raw
    domain = (shop_domain or "").strip()
    if domain:
        if not domain.startswith("http"):
            domain = f"https://{domain}"
        return domain
    return None


def _line_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items = payload.get("line_items")
    if items:
        return [i for i in items if isinstance(i, dict)]
    # Checkout webhook uses line_items too; some payloads nest under checkout
    return []


def _build_contents(items: list[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]], int]:
    contents: list[dict[str, Any]] = []
    content_ids: list[str] = []
    num_items = 0
    for item in items:
        sku = item.get("sku") or item.get("variant_id") or item.get("product_id")
        cid = str(sku) if sku is not None else None
        if not cid:
            continue
        content_ids.append(cid)
        try:
            qty = int(item.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1
        num_items += qty
        try:
            price = float(item.get("price") or 0)
        except (TypeError, ValueError):
            price = 0.0
        contents.append({"id": cid, "quantity": qty, "item_price": price})
    return content_ids, contents, num_items


def _user_data_from_payload(
    payload: dict[str, Any], *, event_time: int | None = None
) -> dict[str, Any]:
    customer = payload.get("customer") or {}
    addr = _address_block(payload)
    email = payload.get("email") or customer.get("email")
    phone = payload.get("phone") or customer.get("phone") or addr.get("phone")
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

    # Stable shopper id (hashed) — strong EMQ signal
    external = customer.get("id") or payload.get("user_id")
    if external is not None and str(external).strip():
        ext_hash = sha256_normalize(str(external).strip())
        if ext_hash:
            user_data["external_id"] = [ext_hash]

    browser_ip = payload.get("browser_ip")
    if browser_ip:
        user_data["client_ip_address"] = str(browser_ip)
    client_details = payload.get("client_details") or {}
    ua = client_details.get("user_agent")
    if ua:
        user_data["client_user_agent"] = str(ua)

    fbp, fbc, _fbclid = _extract_fbp_fbc(payload, event_time=event_time)
    if fbp:
        user_data["fbp"] = fbp
    if fbc:
        user_data["fbc"] = fbc

    return user_data


def build_purchase_event(
    order: dict[str, Any],
    *,
    shop_domain: str = "",
    event_id_scheme: str = "order_id",
) -> dict[str, Any]:
    """Build a Meta CAPI Purchase event dict."""
    event_time = _parse_event_time(order)
    user_data = _user_data_from_payload(order, event_time=event_time)
    content_ids, contents, num_items = _build_contents(_line_items(order))

    try:
        value = float(order.get("total_price") or order.get("current_total_price") or 0)
    except (TypeError, ValueError):
        value = 0.0

    currency = str(order.get("currency") or order.get("presentment_currency") or "USD")
    order_id = str(order.get("id") or "")
    event_id = resolve_event_id(order, event_id_scheme)
    notes = _note_attr_map(order)
    landing = _event_source_url(order, shop_domain)
    utm = _utm_from_landing(
        order.get("landing_site") if order.get("landing_site") else landing,
        notes,
    )

    custom_data: dict[str, Any] = {
        "currency": currency,
        "value": value,
        "content_ids": content_ids,
        "content_type": "product",
        "contents": contents,
        "order_id": order_id,
        "num_items": num_items,
    }
    if order.get("name"):
        custom_data["order_name"] = str(order.get("name"))
    if order.get("referring_site"):
        custom_data["referring_site"] = str(order.get("referring_site"))[:500]
    custom_data.update(utm)

    event: dict[str, Any] = {
        "event_name": "Purchase",
        "event_time": event_time,
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": custom_data,
    }
    if landing:
        event["event_source_url"] = landing
    return event


def build_initiate_checkout_event(
    checkout: dict[str, Any],
    *,
    shop_domain: str = "",
) -> dict[str, Any]:
    """Build Meta CAPI InitiateCheckout from a Shopify checkout webhook payload."""
    event_time = _parse_event_time(checkout)
    user_data = _user_data_from_payload(checkout, event_time=event_time)
    content_ids, contents, num_items = _build_contents(_line_items(checkout))

    try:
        value = float(
            checkout.get("total_price")
            or checkout.get("subtotal_price")
            or 0
        )
    except (TypeError, ValueError):
        value = 0.0

    currency = str(checkout.get("currency") or checkout.get("presentment_currency") or "USD")
    checkout_id = str(checkout.get("id") or checkout.get("token") or "")
    event_id = str(checkout.get("token") or checkout_id)
    notes = _note_attr_map(checkout)
    landing = _event_source_url(checkout, shop_domain)
    utm = _utm_from_landing(checkout.get("landing_site") or landing, notes)

    custom_data: dict[str, Any] = {
        "currency": currency,
        "value": value,
        "content_ids": content_ids,
        "content_type": "product",
        "contents": contents,
        "num_items": num_items,
    }
    custom_data.update(utm)

    event: dict[str, Any] = {
        "event_name": "InitiateCheckout",
        "event_time": event_time,
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": custom_data,
    }
    if landing:
        event["event_source_url"] = landing
    return event


def build_browser_funnel_event(
    *,
    event_name: str,
    event_id: str,
    shop_domain: str = "",
    event_source_url: str | None = None,
    value: float | None = None,
    currency: str = "USD",
    content_ids: list[str] | None = None,
    contents: list[dict[str, Any]] | None = None,
    num_items: int | None = None,
    email: str | None = None,
    phone: str | None = None,
    fbp: str | None = None,
    fbc: str | None = None,
    fbclid: str | None = None,
    client_ip_address: str | None = None,
    client_user_agent: str | None = None,
    external_id: str | None = None,
) -> dict[str, Any]:
    """Build ViewContent / AddToCart (or similar) from browser beacon payload."""
    allowed = {"ViewContent", "AddToCart", "InitiateCheckout", "Purchase"}
    if event_name not in allowed:
        raise ValueError(f"Unsupported event_name: {event_name}")

    event_time = int(datetime.now(UTC).timestamp())
    user_data: dict[str, Any] = {}
    em = hash_email(email)
    if em:
        user_data["em"] = [em]
    ph = hash_phone(phone)
    if ph:
        user_data["ph"] = [ph]
    if external_id:
        ext = sha256_normalize(str(external_id))
        if ext:
            user_data["external_id"] = [ext]
    if client_ip_address:
        user_data["client_ip_address"] = str(client_ip_address)
    if client_user_agent:
        user_data["client_user_agent"] = str(client_user_agent)
    if fbp:
        user_data["fbp"] = fbp
    resolved_fbc = fbc
    if not resolved_fbc and fbclid:
        resolved_fbc = _build_fbc(fbclid, event_time)
    if resolved_fbc:
        user_data["fbc"] = resolved_fbc

    custom_data: dict[str, Any] = {
        "currency": currency or "USD",
        "content_type": "product",
    }
    if value is not None:
        custom_data["value"] = float(value)
    if content_ids:
        custom_data["content_ids"] = content_ids
    if contents:
        custom_data["contents"] = contents
    if num_items is not None:
        custom_data["num_items"] = num_items

    source = event_source_url or _event_source_url({}, shop_domain)
    event: dict[str, Any] = {
        "event_name": event_name,
        "event_time": event_time,
        "event_id": event_id,
        "action_source": "website",
        "user_data": user_data,
        "custom_data": custom_data,
    }
    if source:
        event["event_source_url"] = source
    return event
