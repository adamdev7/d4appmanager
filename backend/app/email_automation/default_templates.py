from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmailAutomationRule, EmailTemplate
from app.email_automation.events import AutomationEventType

_DEFAULTS: list[tuple[AutomationEventType, str, str, str]] = [
    (
        AutomationEventType.ORDER_PAID,
        "Purchase confirmation",
        "Order {{order_number}} confirmed — {{store_name}}",
        "<p>Hi {{customer_name}},</p><p>Thanks for your order <strong>{{order_number}}</strong> at {{store_name}}.</p>"
        "<p>Items: {{product_name}}</p><p>We'll email you when it ships.</p>",
    ),
    (
        AutomationEventType.ORDER_FULFILLED,
        "Shipping confirmation",
        "Your order {{order_number}} has shipped",
        "<p>Hi {{customer_name}},</p><p>Your order <strong>{{order_number}}</strong> is on the way.</p>"
        "<p>Tracking: {{tracking_number}}</p>",
    ),
    (
        AutomationEventType.ORDER_DELIVERED,
        "Delivery confirmation",
        "Delivered: order {{order_number}}",
        "<p>Hi {{customer_name}},</p><p>Your order <strong>{{order_number}}</strong> was delivered. Enjoy!</p>",
    ),
    (
        AutomationEventType.CUSTOMER_CREATED,
        "Welcome email",
        "Welcome to {{store_name}}",
        "<p>Hi {{customer_name}},</p><p>Welcome to {{store_name}}. We're glad you're here.</p>",
    ),
    (
        AutomationEventType.FIRST_PURCHASE,
        "First purchase thank you",
        "Thanks for your first order at {{store_name}}",
        "<p>Hi {{customer_name}},</p><p>Thanks for placing your first order <strong>{{order_number}}</strong> with us.</p>",
    ),
    (
        AutomationEventType.REPEAT_PURCHASE,
        "Loyalty email",
        "Welcome back to {{store_name}}",
        "<p>Hi {{customer_name}},</p><p>Thanks again for order <strong>{{order_number}}</strong>. We appreciate your loyalty.</p>",
    ),
    (
        AutomationEventType.TRACKING_ADDED,
        "Tracking notification",
        "Tracking for order {{order_number}}",
        "<p>Hi {{customer_name}},</p><p>Tracking number: <strong>{{tracking_number}}</strong> for order {{order_number}}.</p>",
    ),
    (
        AutomationEventType.IN_TRANSIT_UPDATE,
        "Shipping update",
        "Shipping update for order {{order_number}}",
        "<p>Hi {{customer_name}},</p><p>Your shipment for order <strong>{{order_number}}</strong> is in transit.</p>"
        "<p>Tracking: {{tracking_number}}</p>",
    ),
]


def seed_store_automation_defaults(db: Session, store_id: str) -> None:
    """Create default templates + rules for a store (idempotent per event type)."""
    for event_type, template_name, subject, body in _DEFAULTS:
        existing_rule = db.scalar(
            select(EmailAutomationRule).where(
                EmailAutomationRule.store_id == store_id,
                EmailAutomationRule.event_type == event_type.value,
            )
        )
        if existing_rule:
            continue

        template = db.scalar(
            select(EmailTemplate).where(
                EmailTemplate.store_id == store_id,
                EmailTemplate.name == template_name,
            )
        )
        if not template:
            template = EmailTemplate(
                store_id=store_id,
                name=template_name,
                subject=subject,
                body_html=body,
            )
            db.add(template)
            db.flush()

        db.add(
            EmailAutomationRule(
                store_id=store_id,
                event_type=event_type.value,
                template_id=template.id,
                is_enabled=False,
            )
        )
    db.commit()
