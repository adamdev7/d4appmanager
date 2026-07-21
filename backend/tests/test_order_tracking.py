from datetime import UTC, datetime

from app.integrations.tracking.carrier_api import _map_17track_main_status
from app.tracking.track_service import TrackOrderService
from app.tracking.payload_parser import (
    fulfillments_from_payload,
    map_shipment_status_to_tracking_status,
    normalize_order_number,
    order_number_from_payload,
    order_number_variants,
    order_summary_from_payload,
    recipient_email,
    timeline_event,
    tracking_from_payload,
)
from app.tracking.timeline_normalize import normalize_timeline


def test_normalize_order_number():
    assert normalize_order_number("#1001") == "1001"
    assert normalize_order_number("1001") == "1001"


def test_order_number_variants():
    assert set(order_number_variants("1001")) == {"1001", "#1001"}


def test_order_number_from_shopify_order():
    assert order_number_from_payload({"name": "#1001", "order_number": 1001}) == "#1001"


def test_order_number_from_fulfillment_webhook_is_empty():
    assert (
        order_number_from_payload(
            {
                "id": 999,
                "order_id": 555,
                "tracking_number": "YT123",
                "tracking_company": "YunExpress",
                "status": "success",
            }
        )
        == ""
    )


def test_tracking_from_fulfillment_payload():
    number, carrier = tracking_from_payload(
        {
            "tracking_number": "YT123",
            "tracking_company": "YunExpress",
            "shipment_status": "in_transit",
        }
    )
    assert number == "YT123"
    assert carrier == "YunExpress"


def test_fulfillments_from_order_payload():
    fulfillments = fulfillments_from_payload(
        {
            "name": "#1001",
            "fulfillments": [
                {
                    "id": 1,
                    "status": "success",
                    "tracking_number": "YT999",
                    "tracking_company": "YunExpress",
                    "shipment_status": "in_transit",
                    "updated_at": "2026-07-19T10:00:00Z",
                    "line_items": [{"title": "Ring", "quantity": 1}],
                }
            ],
        }
    )
    assert len(fulfillments) == 1
    assert fulfillments[0]["tracking_number"] == "YT999"
    assert fulfillments[0]["carrier"] == "YunExpress"
    assert fulfillments[0]["items"] == ["Ring"]


def test_fulfillments_from_fulfillment_webhook():
    fulfillments = fulfillments_from_payload(
        {
            "id": 88,
            "order_id": 555,
            "status": "success",
            "tracking_number": "YT888",
            "tracking_company": "YunExpress",
            "shipment_status": "in_transit",
            "tracking_url": "https://example.com/YT888",
            "line_items": [{"title": "Necklace", "quantity": 2}],
        }
    )
    assert len(fulfillments) == 1
    assert fulfillments[0]["tracking_number"] == "YT888"
    assert fulfillments[0]["tracking_url"] == "https://example.com/YT888"


def test_recipient_email_nested_customer():
    assert recipient_email({"customer": {"email": "Sam@Example.com"}}) == "sam@example.com"


def test_17track_string_status_delivered():
    assert _map_17track_main_status("Delivered") == "delivered"
    assert _map_17track_main_status("InTransit") == "in_transit"
    assert _map_17track_main_status("OutForDelivery") == "in_transit"
    assert _map_17track_main_status(None, sub_status="Delivered_Other") == "delivered"


def test_17track_legacy_numeric_status():
    assert _map_17track_main_status(40) == "delivered"
    assert _map_17track_main_status(30) == "in_transit"


def test_status_mapping():
    assert map_shipment_status_to_tracking_status("delivered", True) == "delivered"
    assert map_shipment_status_to_tracking_status("in_transit", True) == "in_transit"
    assert map_shipment_status_to_tracking_status("", False) == "pending"


def test_order_summary_from_shopify_order():
    summary = order_summary_from_payload(
        {
            "created_at": "2026-05-18T14:05:00-04:00",
            "total_price": "2480.00",
            "currency": "USD",
            "line_items": [
                {
                    "title": "Solitaire Diamond Ring",
                    "variant_title": "18K White Gold",
                    "quantity": 1,
                    "price": "2180.00",
                },
                {
                    "title": "Care Kit",
                    "variant_title": "",
                    "quantity": 1,
                    "price": "300.00",
                },
            ],
        }
    )
    assert summary["total_display"] == "$2,480.00"
    assert summary["currency"] == "USD"
    assert summary["placed_at"] is not None
    assert len(summary["line_items"]) == 2
    assert summary["line_items"][0]["title"] == "Solitaire Diamond Ring"


def test_normalize_timeline_newest_first_and_filters_internal():
    from datetime import UTC, datetime

    raw = [
        timeline_event("pending", "Tracking: YT1 — Tracking added", at=datetime(2026, 5, 28, 16, 0, tzinfo=UTC)),
        timeline_event(
            "delivered",
            "This parcel has been delivered (Alexandria,GB) — YunExpress",
            at=datetime(2026, 5, 28, 15, 56, tzinfo=UTC),
        ),
        timeline_event(
            "in_transit",
            "Shipment information received — YunExpress",
            at=datetime(2026, 5, 19, 7, 15, tzinfo=UTC),
        ),
        timeline_event(
            "delivered",
            "This parcel has been delivered",
            at=datetime(2026, 5, 27, 14, 2, tzinfo=UTC),
        ),
        timeline_event("in_transit", "Updated from 17track", at=datetime(2026, 5, 28, 16, 59, tzinfo=UTC)),
    ]
    out = normalize_timeline(raw, shipment_status="delivered")
    assert len(out) == 3
    assert out[0]["status"] == "delivered"
    assert "alexandria" not in out[0]["description"].lower()  # location stripped to field
    assert out[0]["location"] == "Alexandria,GB"
    assert out[-1]["status"] == "label_created"
    assert "information received" in out[-1]["description"].lower()
    assert all("tracking added" not in e["description"].lower() for e in out)
    assert all("updated from" not in e["description"].lower() for e in out)


def test_should_refresh_carrier_for_shopify_placeholder_timeline():
    class Row:
        tracking_number = "YT2613900703325478"
        last_updated_at = datetime.now(UTC)
        timeline_json = (
            '[{"status":"in_transit","description":"Shipper added tracking YT2613900703325478",'
            '"location":"YunExpress","at":"2026-07-21T04:59:33+00:00"}]'
        )

    assert TrackOrderService._timeline_needs_carrier_enrichment(Row()) is True
    assert TrackOrderService._should_refresh_carrier(Row()) is True


def test_should_not_force_refresh_when_carrier_events_exist():
    class Row:
        tracking_number = "YT2613900703325478"
        last_updated_at = datetime.now(UTC)
        timeline_json = (
            '[{"status":"in_transit","description":"Arrived at sorting center",'
            '"location":"","at":"2026-07-21T05:00:00+00:00"}]'
        )

    assert TrackOrderService._timeline_needs_carrier_enrichment(Row()) is False
    assert TrackOrderService._should_refresh_carrier(Row()) is False
