"""Clean, sort, and dedupe carrier timeline events for the storefront."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

_INTERNAL_PATTERNS = (
    re.compile(r"^tracking:\s*\S+\s*[—–-]\s*tracking added", re.I),
    re.compile(r"^updated from\s+", re.I),
    re.compile(r"^status:\s*", re.I),
)

_CARRIER_SUFFIX = re.compile(
    r"\s*[—–-]\s*(yunexpress|17track|ups|usps|fedex|dhl|amazon|royal mail)\s*$",
    re.I,
)


def _parse_at(raw: str | None) -> datetime:
    if not raw:
        return datetime.min.replace(tzinfo=UTC)
    text = str(raw).strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return datetime.min.replace(tzinfo=UTC)


def _is_internal(description: str) -> bool:
    text = description.strip()
    if not text:
        return True
    return any(pattern.search(text) for pattern in _INTERNAL_PATTERNS)


def _split_description(raw: str) -> tuple[str, str]:
    text = (raw or "").strip()
    text = _CARRIER_SUFFIX.sub("", text).strip()
    location = ""
    match = re.search(r"\(([^)]+)\)\s*$", text)
    if match:
        location = match.group(1).strip()
        text = text[: match.start()].strip()
    return text, location


def _normalize_key(description: str, at: datetime) -> str:
    base = re.sub(r"\s+", " ", description.lower())
    return f"{at.date().isoformat()}|{base[:120]}"


def event_status_from_description(description: str, fallback: str) -> str:
    text = description.lower()
    if any(
        phrase in text
        for phrase in (
            "this parcel has been delivered",
            "parcel has been delivered",
            "package has been delivered",
            "successfully delivered",
            "delivery completed",
        )
    ):
        return "delivered"
    if "delivered to local carrier" in text or "handed over to" in text:
        return "in_transit"
    if any(
        phrase in text
        for phrase in (
            "shipment information received",
            "shipping label created",
            "label created",
            "information received",
        )
    ):
        return "label_created"
    if "exception" in text or "failed" in text or "returned" in text:
        return "exception"
    if fallback in ("delivered", "in_transit", "label_created", "exception", "pending"):
        return fallback
    return "in_transit"


def normalize_timeline(
    events: list[dict[str, Any]],
    *,
    shipment_status: str = "pending",
) -> list[dict[str, str]]:
    """Return newest-first timeline suitable for the Shopify track-order page."""
    cleaned: list[dict[str, Any]] = []

    for item in events:
        if not isinstance(item, dict):
            continue
        description, location = _split_description(str(item.get("description") or ""))
        if not description or _is_internal(description):
            continue
        at = _parse_at(item.get("at"))
        if not location and item.get("location"):
            location = str(item.get("location")).strip()
        status = event_status_from_description(
            description,
            str(item.get("status") or shipment_status),
        )
        cleaned.append(
            {
                "status": status,
                "description": description,
                "location": location,
                "at": at,
            }
        )

    cleaned.sort(key=lambda row: row["at"], reverse=True)

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in cleaned:
        key = _normalize_key(row["description"], row["at"])
        if key in seen:
            continue
        # Drop near-duplicate: same description within 3 hours (17TRACK latest_event overlap)
        duplicate = False
        for existing in deduped:
            if existing["description"].lower() != row["description"].lower():
                continue
            delta = abs((existing["at"] - row["at"]).total_seconds())
            if delta < 3 * 3600:
                duplicate = True
                break
        if duplicate:
            continue
        seen.add(key)
        deduped.append(row)

    # Only the newest true delivery should read as "delivered" when multiple mention delivery
    delivered_indexes = [i for i, row in enumerate(deduped) if row["status"] == "delivered"]
    if len(delivered_indexes) > 1:
        for i in delivered_indexes[1:]:
            deduped[i]["status"] = "in_transit"

    result: list[dict[str, str]] = []
    for row in deduped[:50]:
        at: datetime = row["at"]
        if at == datetime.min.replace(tzinfo=UTC):
            at_iso = datetime.now(UTC).isoformat()
        else:
            at_iso = at.isoformat()
        result.append(
            {
                "status": str(row["status"]),
                "description": str(row["description"]),
                "location": str(row.get("location") or ""),
                "at": at_iso,
            }
        )
    return result
