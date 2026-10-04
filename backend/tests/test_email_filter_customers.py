import asyncio
import base64

from app.ai_email_assistant.email_filter import EmailFilterConfig, EmailFilterResult, evaluate_email_filter
from app.integrations.gmail.inbox_client import GmailInboxClient


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def test_strip_html_drops_css_and_keeps_visible_copy():
    html = """
    <html><head><style>
    .button__cell { background: #1990C6; }
    @media print { body { color: black !important; } }
    </style></head>
    <body><p>Hi Jane, your order #1139 has shipped.</p></body></html>
    """
    text = GmailInboxClient._strip_html(html)
    assert "background" not in text.lower()
    assert "@media" not in text
    assert "order #1139" in text
    assert "Jane" in text


def test_extract_body_unwraps_quoted_plain_and_prefers_html():
    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    plain = "\n".join(
        [
            ">> Your account is ready. You can browse our latest products, place orders,",
            ">> and track deliveries from your account whenever you need to.",
            ">>",
            ">> If you ever need help, just reply to this email.",
        ]
    )
    html = (
        "<html><body><p>Your account is ready. You can browse our latest products, "
        "place orders, and track deliveries from your account whenever you need to.</p>"
        "<p>If you ever need help, just reply to this email.</p></body></html>"
    )
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/plain", "body": {"data": _b64(plain)}},
            {"mimeType": "text/html", "body": {"data": _b64(html)}},
        ],
    }
    body = client._extract_body(payload)
    assert ">>" not in body
    assert body.startswith("Your account is ready.")
    assert "just reply to this email." in body


def test_extract_body_drops_gmail_quoted_history():
    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    plain = (
        "Why have you tried to take money from my account\n\n"
        "On Thu, 24 Sep 2026 at 09:55, LUXORY <support@luxory.com> wrote:\n"
        "> Your account is ready.\n"
    )
    assert client._extract_body(
        {"mimeType": "text/plain", "body": {"data": _b64(plain)}}
    ) == "Why have you tried to take money from my account"


def test_extract_body_prefers_plain_text_over_html():
    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {
                "mimeType": "text/plain",
                "body": {"data": _b64("Where is my necklace?")},
            },
            {
                "mimeType": "text/html",
                "body": {
                    "data": _b64(
                        "<html><head><style>.x{color:red}</style></head>"
                        "<body>Where is my necklace?</body></html>"
                    )
                },
            },
        ],
    }
    assert client._extract_body(payload) == "Where is my necklace?"


def test_extract_body_walks_nested_multipart_without_returning_css():
    client = GmailInboxClient(db=None)  # type: ignore[arg-type]
    payload = {
        "mimeType": "multipart/mixed",
        "parts": [
            {
                "mimeType": "multipart/alternative",
                "parts": [
                    {
                        "mimeType": "text/html",
                        "body": {
                            "data": _b64(
                                "<style>.button__cell { background: #1990C6; }</style>"
                                "<p>Thanks for order #1139</p>"
                            )
                        },
                    }
                ],
            }
        ],
    }
    body = client._extract_body(payload)
    assert "Thanks for order #1139" in body
    assert "background" not in body.lower()


def test_css_leftovers_are_detected():
    css = ".button__cell { background: #1990C6; } @media print { body { color: black; } }"
    assert GmailInboxClient.body_looks_like_css(css)
    assert not GmailInboxClient.body_looks_like_css("Hi, where is order 1139?")


class _FakeAI:
    def __init__(self, result: EmailFilterResult):
        self.result = result
        self.called_with = None

    async def classify_should_reply(self, **kwargs):
        self.called_with = kwargs
        return self.result


def _config() -> EmailFilterConfig:
    return EmailFilterConfig(
        enabled=True,
        filter_automated=True,
        filter_non_business=True,
        custom_rules="",
        business_name="Luxory",
        business_type="e-commerce",
    )


def test_filter_skips_shopify_alerts_without_calling_ai():
    ai = _FakeAI(EmailFilterResult(should_reply=True, category="customer"))
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="LUXORY <store+1@t.shopifyemail.com>",
            sender_email="store+1@t.shopifyemail.com",
            subject="[LUXORY] Order #1139 placed by Pierrette Duguay",
            body="A new order was placed.",
            ai=ai,
            known_customer=True,
        )
    )
    assert result.should_reply is False
    assert result.category == "automated"
    assert ai.called_with is None


def test_filter_answers_gmail_customer_even_if_ai_says_personal():
    ai = _FakeAI(
        EmailFilterResult(should_reply=False, reason="personal email", category="personal")
    )
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="Jane Jones <janesox41@gmail.com>",
            sender_email="janesox41@gmail.com",
            subject="Where is my order?",
            body="Hi, I still have not received order #1139.",
            ai=ai,
            known_customer=True,
        )
    )
    assert result.should_reply is True
    assert result.category == "customer"
    assert ai.called_with["known_customer"] is True


def test_conversation_looks_like_client_from_gmail_history():
    from app.ai_email_assistant.email_filter import conversation_looks_like_client

    history = (
        "EARLIER EMAILS with janesox41@gmail.com (separate conversations, oldest to newest):\n"
        "--- Customer (Jane Jones <janesox41@gmail.com>) ---\n"
        "Hi, I ordered a necklace last week.\n"
    )
    assert conversation_looks_like_client(
        thread_context=history,
        subject="Re: necklace",
        body="Any news?",
    )


def test_conversation_looks_like_client_from_order_language():
    from app.ai_email_assistant.email_filter import conversation_looks_like_client

    assert conversation_looks_like_client(
        thread_context=None,
        subject="Where is my order?",
        body="Hi, I still have not received order #1139.",
    )
    assert not conversation_looks_like_client(
        thread_context=None,
        subject="Lunch tomorrow?",
        body="Want to grab a coffee?",
    )


def test_subscription_cancel_is_held_for_manual_review_without_ai():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    reason = detect_manual_review_reason(
        subject="Cancel my subscription",
        body="Please cancel my membership starting next month.",
    )
    assert reason is not None
    assert "subscription" in reason.lower() or "admin" in reason.lower()

    ai = _FakeAI(EmailFilterResult(should_reply=True, category="customer"))
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="Jane Jones <janesox41@gmail.com>",
            sender_email="janesox41@gmail.com",
            subject="Cancel my subscription",
            body="Please cancel my membership. I no longer want to be billed.",
            ai=ai,
            known_customer=True,
        )
    )
    assert result.needs_manual_review is True
    assert result.should_reply is True
    assert result.category == "manual_review"
    assert ai.called_with is None


def test_unrecognized_charge_is_held_for_manual_review():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    reason = detect_manual_review_reason(
        subject="Strange charge",
        body="I don't recognize this charge on my card.",
    )
    assert reason is not None
    assert "charge" in reason.lower() or "admin" in reason.lower()


def test_where_is_my_order_is_not_manual_review():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    assert (
        detect_manual_review_reason(
            subject="Where is my order?",
            body="Hi, I still have not received order #1139.",
        )
        is None
    )


def test_send_my_subscription_details_is_not_manual_review():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    assert (
        detect_manual_review_reason(
            subject="Subscription invoice",
            body="Hi, can you please send me my subscription details for order #1139?",
        )
        is None
    )


def test_end_my_subscription_is_still_manual_review():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    reason = detect_manual_review_reason(
        subject="Membership",
        body="I want to end my subscription starting next month.",
    )
    assert reason is not None


def test_unpaid_invoice_is_not_unrecognized_charge():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    assert (
        detect_manual_review_reason(
            subject="Invoice",
            body="I didn't make the payment yet — can you send another invoice?",
        )
        is None
    )


def test_parse_classification_json_manual_review_flag():
    from app.ai_email_assistant.email_filter import parse_classification_json

    result = parse_classification_json(
        '{"should_reply": true, "needs_manual_review": true, "reason": "Escalate", "category": "customer"}'
    )
    assert result.needs_manual_review is True
    assert result.should_reply is True
    assert result.category == "manual_review"


def test_shopify_contact_form_exposes_the_customer():
    from app.ai_email_assistant.email_filter import parse_shopify_contact_form

    parsed = parse_shopify_contact_form(
        "New customer message on September 21, 2026 at 8:30 pm",
        "You received a new message from your online store's contact form. "
        "Country Code: CA Name: Diane Email: dguthrie4922@hotmail.ca Phone: "
        "Body: Where are they made and what currency do you charge?",
    )
    assert parsed is not None
    name, address, message = parsed
    assert name == "Diane"
    assert address == "dguthrie4922@hotmail.ca"
    assert "what currency" in message


def test_information_request_is_answered_even_if_ai_skips():
    ai = _FakeAI(
        EmailFilterResult(
            should_reply=False,
            reason="The message does not contain a specific question",
            category="other",
        )
    )
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="Derek <derekecom7@gmail.com>",
            sender_email="derekecom7@gmail.com",
            subject="Luxory",
            body="Bonjour Luxory?",
            ai=ai,
            known_customer=False,
        )
    )
    assert result.should_reply is True
    assert result.category == "customer"


def test_shopify_customer_message_replies_to_the_customer_not_shopify():
    from app.ai_email_assistant.email_filter import customer_reply_address

    body = (
        "You received a new message from your online store's contact form. "
        "Country Code: CA Id: ContactForm-ANzZ4bDNLVHVmNWU1S__contact_form_UwiCkQ "
        "Name: Francesca Lupo Email: francesluporosa@gmail.com Phone: 4162616064 "
        "Body: I am a cancer survivor and wanted to ask about the bracelet."
    )
    assert (
        customer_reply_address(
            sender_email="mailer@shopify.com",
            subject="New customer message on September 22, 2026 at 3:16 pm",
            body=body,
        )
        == "francesluporosa@gmail.com"
    )


def test_shopify_customer_message_falls_back_to_reply_to_header():
    from app.ai_email_assistant.email_filter import customer_reply_address

    assert (
        customer_reply_address(
            sender_email="mailer@shopify.com",
            subject="New customer message on September 22, 2026",
            body="You received a new message from your online store's contact form.",
            reply_to="Diane <dguthrie4922@hotmail.ca>",
        )
        == "dguthrie4922@hotmail.ca"
    )


def test_order_placed_alert_is_skipped_even_when_the_buyer_is_the_sender():
    """Shopify names the buyer on the alert. That is not the buyer writing in."""
    ai = _FakeAI(EmailFilterResult(should_reply=True, category="customer"))
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="Mélanie Charland <melanie@gmail.com>",
            sender_email="melanie@gmail.com",
            subject="[LUXORY] Order #1213 placed by Mélanie Charland",
            body=(
                "Luxury - Eternal Adjustable Ring\n"
                "2 items from Shopify\n"
                "Order placed\n"
                "View order"
            ),
            ai=ai,
            known_customer=True,
        )
    )
    assert result.should_reply is False
    assert result.category == "automated"
    assert ai.called_with is None


def test_order_placed_alert_is_skipped_when_the_smart_filter_is_off():
    ai = _FakeAI(EmailFilterResult(should_reply=True, category="customer"))
    config = _config()
    config.enabled = False
    result = asyncio.run(
        evaluate_email_filter(
            config,
            sender="support.luxory@gmail.com",
            sender_email="support.luxory@gmail.com",
            subject="[LUXORY] Order #1213 placed by Mélanie Charland",
            body="Order placed. View order.",
            ai=ai,
            known_customer=True,
        )
    )
    assert result.should_reply is False
    assert ai.called_with is None


def test_merchant_alert_reply_to_is_not_used_as_the_customer():
    from app.ai_email_assistant.email_filter import customer_reply_address

    assert (
        customer_reply_address(
            sender_email="store+1@t.shopifyemail.com",
            subject="[LUXORY] Order #1213 placed by Mélanie Charland",
            body="Order placed",
            reply_to="Mélanie Charland <melanie@gmail.com>",
        )
        is None
    )


def test_customer_who_placed_an_order_is_not_a_merchant_alert():
    from app.ai_email_assistant.email_filter import merchant_order_alert_reason

    assert (
        merchant_order_alert_reason(
            "Where is my order?",
            "Hi, I placed order #1213 on September 29 and it has not arrived.",
        )
        is None
    )
    ai = _FakeAI(EmailFilterResult(should_reply=True, category="customer"))
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="Mélanie Charland <melanie@gmail.com>",
            sender_email="melanie@gmail.com",
            subject="Where is my order?",
            body="Hi, I placed order #1213 on September 29 and it has not arrived.",
            ai=ai,
            known_customer=True,
        )
    )
    assert result.should_reply is True


def test_unknown_sender_without_a_question_is_not_answered_when_ai_is_down():
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="news@deals.example",
            sender_email="news@deals.example",
            subject="Weekend picks",
            body="Ten products you might like this weekend.",
            ai=None,
            known_customer=False,
        )
    )
    assert result.should_reply is False


def test_unknown_sender_who_asks_for_help_is_still_answered_when_ai_is_down():
    result = asyncio.run(
        evaluate_email_filter(
            _config(),
            sender="sam@gmail.com",
            sender_email="sam@gmail.com",
            subject="Question about a ring",
            body="Do you ship this ring to the UK?",
            ai=None,
            known_customer=False,
        )
    )
    assert result.should_reply is True


def test_cash_refund_is_handed_to_a_teammate():
    from app.ai_email_assistant.email_filter import detect_manual_review_reason

    reason = detect_manual_review_reason(
        subject="Refund",
        body="I want a cash refund for order #1213.",
    )
    assert reason is not None
    assert "cash refund" in reason.lower()


def test_shopify_message_without_customer_address_is_never_sent_to_shopify():
    from app.ai_email_assistant.email_filter import customer_reply_address

    assert (
        customer_reply_address(
            sender_email="mailer@shopify.com",
            subject="New customer message",
            body="You received a new message from your online store's contact form.",
            reply_to="mailer@shopify.com",
        )
        is None
    )
