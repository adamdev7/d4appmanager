from app.ai_email_assistant.whatsapp_alerts import (
    format_manual_review_alert,
    mask_whatsapp_api_key,
    normalize_whatsapp_phone,
)


def test_normalize_whatsapp_phone_keeps_country_code():
    assert normalize_whatsapp_phone("+1 514 555 0100") == "+15145550100"
    assert normalize_whatsapp_phone("0015145550100") == "+15145550100"
    assert normalize_whatsapp_phone("15145550100") == "+15145550100"


def test_normalize_whatsapp_phone_rejects_short():
    assert normalize_whatsapp_phone("123") == ""
    assert normalize_whatsapp_phone("") == ""
    assert normalize_whatsapp_phone(None) == ""


def test_mask_whatsapp_api_key():
    assert mask_whatsapp_api_key("123123") == "••••3123"
    assert mask_whatsapp_api_key("12") == "••••"
    assert mask_whatsapp_api_key("") is None
    assert mask_whatsapp_api_key(None) is None


def test_normalize_callmebot_api_key_extracts_from_paste():
    from app.notifications.whatsapp import normalize_callmebot_api_key

    assert normalize_callmebot_api_key("123123") == "123123"
    assert (
        normalize_callmebot_api_key("API Activated for your phone number. Your APIKEY is 987654")
        == "987654"
    )
    assert normalize_callmebot_api_key("  55 66 77  ") == "556677"


def test_format_manual_review_alert_is_plain_and_actionable():
    text = format_manual_review_alert(
        business_name="Luxory",
        sender="Jane",
        sender_email="jane@shop.com",
        subject="Cancel my subscription",
        reason="Subscription cancel request",
    )
    assert "*Manual review needed*" in text
    assert "Luxory" in text
    assert "Jane" in text
    assert "Cancel my subscription" in text
    assert "Subscription cancel request" in text
    assert "Manual review" in text


def test_format_weekly_ads_recap_lists_what_was_made():
    from app.notifications.whatsapp import format_weekly_ads_recap

    text = format_weekly_ads_recap(
        store_name="Luxory",
        status="COMPLETED",
        product_title="Silk robe",
        image_count=2,
        video_count=1,
        items=["Still: Morning glow", "Video: See it in motion"],
        failed_count=0,
    )
    assert "This week's ads are ready" in text
    assert "Luxory" in text
    assert "2 stills" in text
    assert "1 video" in text
    assert "Silk robe" in text
    assert "Morning glow" in text
    assert "Nothing was published" in text
    assert "Library" in text


def test_format_connection_test_message():
    from app.notifications.whatsapp import format_connection_test_message

    text = format_connection_test_message()
    assert text.startswith("*App Manager*")
    assert "\n" in text
    assert "AI Email Assistant" in text or "AI Ads" in text


def test_whatsapp_public_payload_never_raises():
    from unittest.mock import patch

    from app.notifications.whatsapp import whatsapp_public_payload

    class BoomDb:
        def rollback(self):
            self.rolled_back = True

    with patch(
        "app.notifications.whatsapp.get_whatsapp_connection",
        side_effect=RuntimeError("no such column: user_whatsapp_settings"),
    ):
        payload = whatsapp_public_payload(BoomDb(), object())  # type: ignore[arg-type]
    assert payload["whatsapp_configured"] is False
    assert payload["whatsapp_phone"] == ""
    assert payload["whatsapp_connected_modules"] == []


def test_callmebot_url_keeps_literal_plus_in_phone():
    """CallMeBot docs / Homey use phone=+34… not phone=%2B34…"""
    from app.notifications.whatsapp import build_callmebot_url

    url = build_callmebot_url(
        phone="+15145550100",
        api_key="123123",
        text="Hello\nthere",
    )
    assert "phone=+15145550100" in url
    assert "apikey=123123" in url
    assert "text=Hello%0Athere" in url
    assert "source=appmanager" in url
    assert "phone=%2B" not in url


def test_callmebot_html_error_is_rejected():
    from app.notifications.whatsapp import callmebot_response_rejected, callmebot_send_succeeded

    assert callmebot_response_rejected(200, "<br>ERROR: Phone number format is incorrect")
    assert callmebot_response_rejected(200, "APIKey is invalid")
    assert callmebot_response_rejected(203, "APIKey is incorrect")
    assert callmebot_response_rejected(503, "Service Unavailable")
    assert not callmebot_response_rejected(200, "Message queued to be sent")
    assert callmebot_send_succeeded(200, "Message queued to be sent")
    assert callmebot_send_succeeded(210, "queued")


def test_format_callmebot_error_prefers_clear_reason():
    from app.notifications.whatsapp import format_callmebot_error

    echo = (
        "Message to: +4382256262 Text to send: *App Manager*%0AHello. "
        "APIKey is invalid"
    )
    msg = format_callmebot_error(200, echo)
    assert "invalid" in msg.lower()
    assert "Message to:" not in msg
    assert format_callmebot_error(203, "") == (
        "API key is incorrect for this phone number."
    )
