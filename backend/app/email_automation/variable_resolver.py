import re
from typing import Any

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}", re.IGNORECASE)

_VARIABLE_KEYS = (
    "customer_name",
    "order_number",
    "tracking_number",
    "product_name",
    "store_name",
)


def _customer_name(payload: dict) -> str:
    customer = payload.get("customer") or {}
    first = (customer.get("first_name") or "").strip()
    last = (customer.get("last_name") or "").strip()
    name = f"{first} {last}".strip()
    if name:
        return name
    return customer.get("email") or payload.get("email") or "Customer"


def _order_number(payload: dict) -> str:
    return str(payload.get("name") or payload.get("order_number") or payload.get("id") or "")


def _tracking_number(payload: dict) -> str:
    if payload.get("tracking_number"):
        return str(payload["tracking_number"])
    numbers = payload.get("tracking_numbers")
    if isinstance(numbers, list) and numbers:
        return str(numbers[0])
    fulfillments = payload.get("fulfillments") or []
    for f in fulfillments:
        if f.get("tracking_number"):
            return str(f["tracking_number"])
    return ""


def _product_name(payload: dict) -> str:
    items = payload.get("line_items") or []
    if not items:
        return ""
    names = [str(i.get("name") or i.get("title") or "") for i in items if i]
    names = [n for n in names if n]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{names[0]} (+{len(names) - 1} more)"


def build_template_context(payload: dict, store_name: str) -> dict[str, str]:
    return {
        "customer_name": _customer_name(payload),
        "order_number": _order_number(payload),
        "tracking_number": _tracking_number(payload),
        "product_name": _product_name(payload),
        "store_name": store_name or "Your Store",
    }


def resolve_template_text(text: str, context: dict[str, str]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1).lower()
        return context.get(key, "")

    return _PLACEHOLDER_RE.sub(repl, text)


def list_supported_variables() -> list[str]:
    return list(_VARIABLE_KEYS)
