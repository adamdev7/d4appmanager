import pytest

from app.core.openai_models import (
    DEFAULT_TEXT_MODEL,
    effective_text_model,
    normalize_stored_model,
    use_text_model,
)
from app.config import settings


def test_default_is_the_value_model():
    assert DEFAULT_TEXT_MODEL == "gpt-6.1-sol"


def test_blank_model_uses_fallback():
    assert effective_text_model(None, fallback="gpt-6-luna") == "gpt-6-luna"
    assert effective_text_model("  ") == DEFAULT_TEXT_MODEL


def test_catalog_choice_is_kept():
    assert normalize_stored_model("gpt-6-luna") == "gpt-6-luna"
    assert normalize_stored_model("") is None


def test_unknown_model_rejected_unless_it_is_already_saved():
    with pytest.raises(ValueError):
        normalize_stored_model("gpt-4o-mini")
    assert normalize_stored_model("gpt-4o-mini", current="gpt-4o-mini") == "gpt-4o-mini"


def test_store_model_overrides_server_default_inside_the_block():
    before = settings.resolved_ai_strategy_model
    with use_text_model("gpt-6-luna"):
        assert settings.resolved_ai_strategy_model == "gpt-6-luna"
        assert settings.resolved_ai_creative_model == "gpt-6-luna"
    assert settings.resolved_ai_strategy_model == before
