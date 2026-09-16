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


def test_shopify_merchant_order_alert_is_platform_mail():
    from app.ai_email_assistant.email_filter import is_platform_sender

    sender = "store+82921259256@t.shopifyemail.com"
    assert is_platform_sender(sender)
    reason = check_automated_heuristic(
        sender,
        "[LUXORY] Order #1139 placed by Pierrette Duguay",
        "Order #1139 was placed by Pierrette Duguay.",
    )
    assert reason is not None
    assert "not from the customer" in reason.lower()


def test_real_customer_gmail_is_not_treated_as_automated():
    from app.ai_email_assistant.email_filter import is_platform_sender

    sender = "janesox41@gmail.com"
    assert not is_platform_sender(sender)
    # Quoted receipt language must not skip a person writing in.
    assert (
        check_automated_heuristic(
            sender,
            "Where is my order?",
            "Hi, any update on order #1139?\n\nUnsubscribe\nYou are receiving this email because you bought from Luxory.",
        )
        is None
    )


def test_known_customer_is_not_skipped_as_personal():
    from app.ai_email_assistant.email_filter import EmailFilterResult, apply_known_customer_guard

    skipped = EmailFilterResult(
        should_reply=False, reason="Looks like a personal chat", category="personal"
    )
    guarded = apply_known_customer_guard(
        skipped, known_customer=True, platform_sender=False
    )
    assert guarded.should_reply is True
    assert guarded.category == "customer"


def test_known_customer_guard_does_not_force_reply_to_shopify():
    from app.ai_email_assistant.email_filter import EmailFilterResult, apply_known_customer_guard

    skipped = EmailFilterResult(
        should_reply=False, reason="platform", category="automated"
    )
    guarded = apply_known_customer_guard(
        skipped, known_customer=True, platform_sender=True
    )
    assert guarded.should_reply is False


def test_known_customer_guard_respects_already_resolved():
    from app.ai_email_assistant.email_filter import EmailFilterResult, apply_known_customer_guard

    skipped = EmailFilterResult(
        should_reply=False, reason="Already answered", category="already_resolved"
    )
    guarded = apply_known_customer_guard(
        skipped, known_customer=True, platform_sender=False
    )
    assert guarded.should_reply is False


def test_known_customer_guard_does_not_auto_reply_manual_review():
    from app.ai_email_assistant.email_filter import EmailFilterResult, apply_known_customer_guard

    held = EmailFilterResult(
        should_reply=False,
        reason="Subscription cancellation",
        category="manual_review",
        needs_manual_review=True,
    )
    guarded = apply_known_customer_guard(
        held, known_customer=True, platform_sender=False
    )
    assert guarded.should_reply is False
    assert guarded.needs_manual_review is True
    assert guarded.category == "manual_review"


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


def test_classification_already_resolved():
    result = parse_classification_json(
        '{"should_reply": false, "reason": "Already answered their shipping question", "category": "already_resolved"}'
    )
    assert result.should_reply is False
    assert result.category == "already_resolved"


def test_build_reply_prompt_includes_thread_history_guidance():
    ctx = BusinessContext(
        business_name="Acme Shop",
        business_type="e-commerce",
        tone_of_voice="friendly",
        rules="",
        policies="",
        faq="",
    )
    prompt = build_reply_prompt(
        context=ctx,
        sender="customer@example.com",
        subject="Re: order",
        email_body="Thanks!",
        thread_context="--- Customer ---\nWhere is my order?\n\n--- Your business ---\nIt ships tomorrow.",
    )
    assert "full conversation thread" in prompt.system_message.lower() or "already answered" in prompt.system_message.lower()
    assert "Where is my order?" in prompt.user_message
    assert "It ships tomorrow." in prompt.user_message
