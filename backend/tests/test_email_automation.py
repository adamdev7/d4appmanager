from app.email_automation.events import AutomationEventType, derive_automation_events
from app.email_automation.variable_resolver import build_template_context, resolve_template_text


def test_derive_order_paid():
    events = derive_automation_events("orders/paid", {})
    assert events == [AutomationEventType.ORDER_PAID]


def test_derive_first_purchase():
    events = derive_automation_events(
        "orders/create",
        {"customer": {"orders_count": 1, "first_name": "Sam"}},
    )
    assert AutomationEventType.FIRST_PURCHASE in events


def test_resolve_variables():
    ctx = build_template_context(
        {
            "name": "#1001",
            "customer": {"first_name": "Sam", "email": "sam@example.com"},
            "line_items": [{"name": "Hat"}],
        },
        "Acme Shop",
    )
    subject = resolve_template_text(
        "Hi {{customer_name}}, order {{order_number}} from {{store_name}}",
        ctx,
    )
    assert subject == "Hi Sam, order #1001 from Acme Shop"
