"""Extract likely Shopify order numbers from email subject/body."""

from __future__ import annotations

import re

from app.tracking.payload_parser import normalize_order_number

# Capture likely order tokens; must contain a digit (checked below).
_ORDER_PATTERNS = (
    re.compile(r"#\s*([A-Z0-9][-A-Z0-9]{1,24})", re.IGNORECASE),
    re.compile(
        r"\border\s*(?:number|no\.?)?\s*(?:is|=|:|#)?\s*#?\s*([A-Z0-9][-A-Z0-9]{1,24})",
        re.IGNORECASE,
    ),
)

# Skip recent years mistaken for order numbers (e.g. "since 2024")
_SKIP = re.compile(r"^(199\d|20[0-2]\d)$")


def extract_order_numbers(*texts: str | None, limit: int = 8) -> list[str]:
    """Return unique normalized order numbers found in text snippets."""
    found: list[str] = []
    seen: set[str] = set()
    blob = "\n".join(t for t in texts if t)

    for pattern in _ORDER_PATTERNS:
        for match in pattern.finditer(blob):
            raw = match.group(1)
            normalized = normalize_order_number(raw)
            if not normalized or normalized in seen:
                continue
            if _SKIP.match(normalized):
                continue
            # Must include a digit — drops words like "is", "the", etc.
            if not any(ch.isdigit() for ch in normalized):
                continue
            if len(normalized) < 2:
                continue
            seen.add(normalized)
            found.append(normalized)
            if len(found) >= limit:
                return found
    return found
