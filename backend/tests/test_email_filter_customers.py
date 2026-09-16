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
