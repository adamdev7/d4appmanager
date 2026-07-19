import pytest

from app.ai_email_assistant.email_filter import check_automated_heuristic, parse_classification_json
from app.core.openai_credentials import mask_openai_api_key, validate_openai_api_key_format
from app.ai_email_assistant.prompt_builder import BusinessContext, build_reply_prompt


def test_build_reply_prompt_includes_business_context():
    ctx = BusinessContext(
        business_name="Acme Shop",
        business_type="e-commerce",
        tone_of_voice="friendly",
        rules="Never promise refunds without approval.",
        policies="Shipping: 3-5 days.",
        faq="Returns within 14 days.",
    )
    prompt = build_reply_prompt(
        context=ctx,
        sender="customer@example.com",
        subject="Where is my order?",
        email_body="I ordered last week and have not received tracking.",
    )
    assert "Acme Shop" in prompt.system_message
    assert "friendly" in prompt.system_message
    assert "Never promise refunds" in prompt.system_message
    assert "Shipping: 3-5 days" in prompt.system_message
    assert "Where is my order?" in prompt.user_message
    assert "customer@example.com" in prompt.user_message


def test_automated_heuristic_detects_noreply():
    reason = check_automated_heuristic("noreply@shopify.com", "Order update", "Short body")
    assert reason is not None


def test_mask_openai_api_key():
    assert mask_openai_api_key("sk-abcdefghijklmnop") == "sk-abcd••••mnop"


def test_validate_openai_key_format():
    validate_openai_api_key_format("sk-" + "a" * 24)
    with pytest.raises(ValueError):
        validate_openai_api_key_format("not-a-key")


def test_classification_json_skip():
    result = parse_classification_json(
        '{"should_reply": false, "reason": "Newsletter", "category": "newsletter"}'
    )
    assert result.should_reply is False
    assert result.category == "newsletter"
