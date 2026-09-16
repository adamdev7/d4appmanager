"""Order-aware AI replies: prompt facts, tracking link, and the email button."""

import json
from datetime import UTC, datetime
from html import escape
from urllib.parse import parse_qs, urlparse

from app.ai_email_assistant.order_context import (
    MatchedOrder,
    TrackingLink,
    build_tracking_page_url,
    format_orders_for_prompt,
    pick_tracking_link,
    shipment_status_label,
    strip_tracking_ids_from_text,
)
from app.ai_email_assistant.prompt_builder import BusinessContext, build_reply_prompt
from app.ai_email_assistant.reply_html import render_reply_html, render_reply_text
from app.db.models import OrderTracking

TRACK_PAGE = "https://luxory.online/pages/track-your-order"


def _order(
    *,
    number="#1045",
    email="omw4973@outlook.com",
    tracking="YT2625500704564137",
    carrier="YunExpress",
    status="in_transit",
    timeline=None,
) -> OrderTracking:
    return OrderTracking(
        id=f"order-{number}",
        store_id="store-1",
        order_number_display=number,
        order_number_normalized=number.lstrip("#"),
        customer_email=email,
        tracking_number=tracking,
        carrier=carrier,
        status=status,
        order_placed_at=datetime(2026, 9, 10, tzinfo=UTC),
        order_total_display="59.90",
        order_currency="CAD",
        shopify_financial_status="paid",
        shopify_fulfillment_status="fulfilled",
        customer_name="Olivia W.",
        line_items_json=json.dumps([{"title": "Luxory Necklace", "quantity": 2}]),
        timeline_json=json.dumps(timeline or []),
    )


def test_tracking_url_prefills_order_and_email():
    url = build_tracking_page_url(TRACK_PAGE, "#1045", "omw4973@outlook.com")
    assert url is not None

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.netloc == "luxory.online"
    assert parsed.path == "/pages/track-your-order"
    # The "#" is stripped so the value matches what the storefront form expects.
    assert query["order_number"] == ["1045"]
    assert query["order"] == ["1045"]
    assert query["email"] == ["omw4973@outlook.com"]


def test_tracking_url_requires_order_and_email():
    assert build_tracking_page_url(TRACK_PAGE, "", "a@b.com") is None
    assert build_tracking_page_url(TRACK_PAGE, "1045", "") is None
    assert build_tracking_page_url("", "1045", "a@b.com") is None


def test_tracking_url_keeps_existing_query_params():
    url = build_tracking_page_url(f"{TRACK_PAGE}?utm_source=email", "1045", "a@b.com")
    query = parse_qs(urlparse(url).query)
    assert query["utm_source"] == ["email"]
    assert query["order_number"] == ["1045"]


def test_tracking_link_prefers_the_order_quoted_in_the_email():
    newest = MatchedOrder(row=_order(number="#1099", tracking="AAA111"), match_reason="customer_email")
    quoted = MatchedOrder(row=_order(number="#1045"), match_reason="order_number_in_email")

    link = pick_tracking_link(
        [newest, quoted], page_url=TRACK_PAGE, customer_email="omw4973@outlook.com"
    )
    assert link is not None
    assert link.order_number == "1045"
    assert "order_number=1045" in link.url
    assert "email=omw4973" in link.url


def test_tracking_link_for_unshipped_order_uses_order_and_email_only():
    matched = [MatchedOrder(row=_order(tracking=None, status="pending"), match_reason="customer_email")]
    link = pick_tracking_link(matched, page_url=TRACK_PAGE, customer_email="omw4973@outlook.com")
    assert link is not None
    assert link.order_number == "1045"
    assert "order_number=1045" in link.url
    assert "email=" in link.url


def test_no_tracking_link_when_page_url_missing():
    matched = [MatchedOrder(row=_order(), match_reason="customer_email")]
    assert pick_tracking_link(matched, page_url="", customer_email="a@b.com") is None


def test_shipment_status_label():
    assert shipment_status_label(_order()) == "On the way"
    assert shipment_status_label(_order(status="delivered")) == "Delivered"
    assert shipment_status_label(_order(tracking=None)) == "Not shipped yet"


def test_prompt_order_block_carries_shipment_facts():
    matched = [
        MatchedOrder(
            row=_order(
                timeline=[
                    {
                        "status": "in_transit",
                        "description": "Shipper added tracking YT2625500704564137",
                        "location": "Shopify",
                        "at": "2026-09-12T01:13:00Z",
                    }
                ]
            ),
            match_reason="order_number_in_email",
        )
    ]
    link = pick_tracking_link(matched, page_url=TRACK_PAGE, customer_email="omw4973@outlook.com")
    block = format_orders_for_prompt(matched, tracking_link=link)

    assert "Order #1045" in block
    assert "On the way" in block
    assert "YT2625500704564137" not in block
    assert "Luxory Necklace x2" in block
    assert "Shipper added tracking" in block
    assert "quoted in their email" in block
    assert "Track my order" in block
    assert "do not share the tracking number" in block.lower() or "never" in block.lower()


def test_prompt_only_claims_a_button_for_the_order_that_has_one():
    quoted = MatchedOrder(row=_order(number="#1045"), match_reason="order_number_in_email")
    other = MatchedOrder(
        row=_order(number="#1099", tracking="AAA111"), match_reason="customer_email"
    )
    link = pick_tracking_link(
        [other, quoted], page_url=TRACK_PAGE, customer_email="omw4973@outlook.com"
    )
    block = format_orders_for_prompt([other, quoted], tracking_link=link)

    assert block.count("Track my order") == 1
    # The note belongs to the quoted order, not the other shipped one.
    after_1099 = block.split("Order #1099", 1)[1].split("Order #1045", 1)[0]
    assert "Track my order" not in after_1099


def test_prompt_order_block_is_empty_without_matches():
    assert format_orders_for_prompt([]) == ""


def test_reply_prompt_instructs_model_to_use_order_data_and_button():
    ctx = BusinessContext(
        business_name="Luxory",
        business_type="e-commerce",
        tone_of_voice="warm",
        rules="",
        policies="",
        faq="",
    )
    prompt = build_reply_prompt(
        context=ctx,
        sender="omw4973@outlook.com",
        subject="Where is my order #1045?",
        email_body="Any update?",
        order_context="Order #1045\n- Shipment: On the way",
        has_tracking_button=True,
    )

    assert "Order #1045" in prompt.user_message
    assert "source of truth" in prompt.system_message
    assert "Track my order" in prompt.system_message
    assert "do not paste" in prompt.system_message.lower() or "Never paste" in prompt.system_message
    assert "tracking number" in prompt.system_message.lower()
    assert "quote the tracking number" not in prompt.system_message.lower()


def test_reply_prompt_omits_button_rule_when_not_trackable():
    ctx = BusinessContext("Luxory", "e-commerce", "warm", "", "", "")
    prompt = build_reply_prompt(
        context=ctx,
        sender="a@b.com",
        subject="Hi",
        email_body="Hello",
    )
    assert "Track my order" not in prompt.system_message


def test_reply_html_renders_prefilled_button():
    link = TrackingLink(
        url=f"{TRACK_PAGE}?order_number=1045&email=omw4973%40outlook.com",
        order_number="1045",
        tracking_number="YT2625500704564137",
        carrier="YunExpress",
    )
    html = render_reply_html("Hi Olivia,\n\nYour order shipped.", tracking_link=link)

    assert html is not None
    assert "Track my order" in html
    # The href is HTML-escaped, so "&" between query params becomes "&amp;".
    assert escape(link.url, quote=True) in html
    assert "Your order shipped." in html
    assert "Order 1045" in html
    assert "YT2625500704564137" not in html
    assert "YunExpress" not in html


def test_reply_html_escapes_body_content():
    link = TrackingLink(url=f"{TRACK_PAGE}?order_number=1", order_number="1", tracking_number="", carrier="")
    html = render_reply_html("<script>alert(1)</script>", tracking_link=link)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_reply_stays_plain_text_without_a_tracking_link():
    assert render_reply_html("Hello there", tracking_link=None) is None
    assert render_reply_text("Hello there", tracking_link=None) == "Hello there"


def test_reply_text_spells_out_the_link_for_plain_text_clients():
    link = TrackingLink(
        url=f"{TRACK_PAGE}?order_number=1045",
        order_number="1045",
        tracking_number="YT123",
        carrier="YunExpress",
    )
    text = render_reply_text("Your order shipped.", tracking_link=link)
    assert "Your order shipped." in text
    assert link.url in text
    assert "Order 1045" in text
    assert "YT123" not in text
    assert "YunExpress" not in text
    assert "Tracking number" not in text


def test_strip_tracking_ids_from_draft():
    text = strip_tracking_ids_from_text(
        "Your parcel is on the way. Tracking number: YT2625500704564137 (YunExpress).",
        ["YT2625500704564137"],
    )
    assert "YT2625500704564137" not in text
    assert "on the way" in text
