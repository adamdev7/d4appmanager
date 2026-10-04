"""Text models each AI option can pick. One default: the best result per token."""

from __future__ import annotations

import re
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Iterator

DEFAULT_TEXT_MODEL = "gpt-6.1-sol"

# Prices are USD per 1M tokens (short context), from the OpenAI pricing page.
TEXT_MODELS: tuple[dict[str, str | float], ...] = (
    {
        "id": "gpt-6.1-sol",
        "name": "Sol",
        "tag": "Best value",
        "blurb": "Near flagship quality at about one fifth of the price. Default for replies, reports, and ad copy.",
        "input_per_mtok": 2.0,
        "output_per_mtok": 10.0,
    },
    {
        "id": "gpt-6-luna",
        "name": "Luna",
        "tag": "Lowest spend",
        "blurb": "The cheap model for short, high-volume replies. Use it when volume matters more than nuance.",
        "input_per_mtok": 0.10,
        "output_per_mtok": 0.50,
    },
    {
        "id": "gpt-6-astra",
        "name": "Astra",
        "tag": "Highest quality",
        "blurb": "Flagship. Worth it for long reports and creative briefs, and the bill is much higher.",
        "input_per_mtok": 10.0,
        "output_per_mtok": 50.0,
    },
)

_MODEL_IDS = {str(row["id"]) for row in TEXT_MODELS}
_SAFE_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_override: ContextVar[str | None] = ContextVar("openai_text_model", default=None)


def model_catalog() -> dict:
    return {
        "default_model": DEFAULT_TEXT_MODEL,
        "models": [
            {
                "id": row["id"],
                "name": row["name"],
                "tag": row["tag"],
                "blurb": row["blurb"],
                "input_per_mtok": row["input_per_mtok"],
                "output_per_mtok": row["output_per_mtok"],
                "recommended": row["id"] == DEFAULT_TEXT_MODEL,
            }
            for row in TEXT_MODELS
        ],
    }


def peek_text_model() -> str | None:
    return _override.get()


def normalize_stored_model(value: str | None, *, current: str | None = None) -> str | None:
    """Persist a catalog id. Blank means 'use the recommended default'."""
    raw = (value or "").strip()
    if not raw:
        return None
    if raw in _MODEL_IDS:
        return raw
    if current and raw == current.strip():
        return current.strip()
    raise ValueError("Choose a model from the list")


def server_text_fallback() -> str:
    """Env strategy model when set, otherwise the recommended default."""
    from app.config import settings

    return (settings.ai_strategy_model or settings.openai_model or DEFAULT_TEXT_MODEL).strip() or DEFAULT_TEXT_MODEL


def effective_text_model(chosen: str | None, *, fallback: str | None = None) -> str:
    raw = (chosen or "").strip()
    if raw and (_SAFE_MODEL.fullmatch(raw) or raw in _MODEL_IDS):
        return raw
    base = (fallback or DEFAULT_TEXT_MODEL).strip()
    return base or DEFAULT_TEXT_MODEL


@contextmanager
def use_text_model(chosen: str | None, *, fallback: str | None = None) -> Iterator[str]:
    model = effective_text_model(chosen, fallback=fallback)
    token: Token[str | None] = _override.set(model)
    try:
        yield model
    finally:
        _override.reset(token)
