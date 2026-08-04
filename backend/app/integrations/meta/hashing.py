"""Normalize and SHA-256 hash PII for Meta Conversions API user_data fields."""

from __future__ import annotations

import hashlib
import re


def sha256_normalize(value: str | None) -> str | None:
    """Lowercase, trim, then SHA-256 hex digest. Returns None if empty after normalize."""
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()


def normalize_phone(phone: str | None) -> str | None:
    """Strip to digits for Meta hashing (include country code when available)."""
    if not phone:
        return None
    raw = str(phone).strip()
    if not raw:
        return None
    digits_only = re.sub(r"\D", "", raw)
    return digits_only or None


def hash_phone(phone: str | None) -> str | None:
    normalized = normalize_phone(phone)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def hash_email(email: str | None) -> str | None:
    return sha256_normalize(email)


def hash_name(name: str | None) -> str | None:
    return sha256_normalize(name)


def hash_location(value: str | None) -> str | None:
    """City / state / zip / country — lowercase, trim, remove spaces."""
    if value is None:
        return None
    cleaned = str(value).strip().lower().replace(" ", "")
    if not cleaned:
        return None
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
