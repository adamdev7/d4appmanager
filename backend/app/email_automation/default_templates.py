from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import EmailAutomationRule, EmailTemplate
from app.email_automation.events import AutomationEventType

# Shared inline styles for readable, email-client-safe body copy.
_P = 'style="margin:0 0 14px;color:#1f2937;font-size:15px;line-height:1.65;"'
_MUTED = 'style="margin:0 0 14px;color:#4b5563;font-size:14px;line-height:1.6;"'
_SIG = 'style="margin:16px 0 0;color:#1f2937;font-size:15px;line-height:1.65;"'


def _p(text: str, style: str = _P) -> str:
    """Build a paragraph without f-string brace collisions on {{tokens}}."""
    return f"<p {style}>{text}</p>"


_DEFAULTS: list[tuple[AutomationEventType, str, str, str]] = [
    (
        AutomationEventType.ORDER_PAID,
        "Purchase confirmation",
        "Order {{order_number}} confirmed — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Thank you for your order at <strong>{{store_name}}</strong>. "
            "We have received your payment and are preparing your items."
        )
        + _p(
            "<strong>Order number:</strong> {{order_number}}<br/>"
            "<strong>Items:</strong> {{product_name}}"
        )
        + _p(
            "You will receive another email when your order ships, including tracking details."
        )
        + _p(
            "If you did not place this order, please reply to this email so we can help right away.",
            _MUTED,
        )
        + _p("Thanks,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.ORDER_FULFILLED,
        "Shipping confirmation",
        "Your order {{order_number}} has shipped — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Good news — your order <strong>{{order_number}}</strong> from "
            "<strong>{{store_name}}</strong> is on its way."
        )
        + _p("<strong>Tracking number:</strong> {{tracking_number}}")
        + _p(
            "You can use this number on the carrier's website to follow delivery progress. "
            "Transit times vary by destination; most packages arrive within the timeframe shown at checkout."
        )
        + _p(
            "Questions about your shipment? Reply to this email and we will be happy to help.",
            _MUTED,
        )
        + _p("Thank you for shopping with us,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.ORDER_DELIVERED,
        "Delivery confirmation",
        "Your order {{order_number}} was delivered — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Your order <strong>{{order_number}}</strong> from <strong>{{store_name}}</strong> "
            "has been marked as delivered."
        )
        + _p(
            "We hope everything looks great. If something is missing or not as expected, "
            "reply to this email within a few days and we will sort it out."
        )
        + _p(
            "Thank you for choosing {{store_name}}. We appreciate your business.",
            _MUTED,
        )
        + _p("Warm regards,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.CUSTOMER_CREATED,
        "Welcome email",
        "Welcome to {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Welcome to <strong>{{store_name}}</strong> — we are glad you are here."
        )
        + _p(
            "Your account is ready. You can browse our latest products, place orders, "
            "and track deliveries from your account whenever you need to."
        )
        + _p(
            "If you ever need help with an order or have a question, just reply to this email. "
            "A real person on our team will get back to you."
        )
        + _p(
            "You are receiving this message because you created an account with {{store_name}}.",
            _MUTED,
        )
        + _p("Welcome aboard,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.FIRST_PURCHASE,
        "First purchase thank you",
        "Thank you for your first order at {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Thank you for your first order with <strong>{{store_name}}</strong>. "
            "We are excited to have you as a customer."
        )
        + _p("<strong>Order number:</strong> {{order_number}}")
        + _p(
            "We will send shipping updates to this email address as your order moves along. "
            "In the meantime, feel free to reply if you need anything — sizing help, gift notes, "
            "or order changes when still possible."
        )
        + _p(
            "We work hard to make every order smooth from checkout to delivery.",
            _MUTED,
        )
        + _p("Thanks again,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.REPEAT_PURCHASE,
        "Loyalty email",
        "Thank you for ordering again — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Welcome back — thank you for ordering again from <strong>{{store_name}}</strong>. "
            "Loyal customers like you mean a lot to us."
        )
        + _p("<strong>Order number:</strong> {{order_number}}")
        + _p(
            "We are preparing this order with the same care as always. You will get a shipping "
            "confirmation with tracking as soon as it leaves our facility."
        )
        + _p(
            "If there is anything we can do to make this order even better, reply anytime.",
            _MUTED,
        )
        + _p("With appreciation,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.TRACKING_ADDED,
        "Tracking notification",
        "Tracking available for order {{order_number}} — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "Tracking is now available for your <strong>{{store_name}}</strong> order "
            "<strong>{{order_number}}</strong>."
        )
        + _p("<strong>Tracking number:</strong> {{tracking_number}}")
        + _p(
            "Copy this number into the carrier's tracking page to see the latest status. "
            "The first scan can take a little time after the label is created — that is normal."
        )
        + _p(
            "Need help reading the status? Reply to this email and we will walk you through it.",
            _MUTED,
        )
        + _p("Thank you,<br/>The {{store_name}} team", _SIG),
    ),
    (
        AutomationEventType.IN_TRANSIT_UPDATE,
        "Shipping update",
        "Shipping update for order {{order_number}} — {{store_name}}",
        _p("Hi {{customer_name}},")
        + _p(
            "A quick update: your shipment for order <strong>{{order_number}}</strong> "
            "from <strong>{{store_name}}</strong> is in transit."
        )
        + _p("<strong>Tracking number:</strong> {{tracking_number}}")
        + _p(
            "Your package is moving through the carrier network toward its destination. "
            "We will notify you again when it is delivered, when that information is available."
        )
        + _p(
            "If the status has not changed for several days, reply to this email and we will investigate.",
            _MUTED,
        )
        + _p("Safe travels to your package,<br/>The {{store_name}} team", _SIG),
    ),
]

# Prior short bodies — used so seed can safely upgrade stores that still have starter copy.
_LEGACY_BODIES: frozenset[str] = frozenset(
    {
        "<p>Hi {{customer_name}},</p><p>Thanks for your order <strong>{{order_number}}</strong> at {{store_name}}.</p>"
        "<p>Items: {{product_name}}</p><p>We'll email you when it ships.</p>",
        "<p>Hi {{customer_name}},</p><p>Your order <strong>{{order_number}}</strong> is on the way.</p>"
        "<p>Tracking: {{tracking_number}}</p>",
        "<p>Hi {{customer_name}},</p><p>Your order <strong>{{order_number}}</strong> was delivered. Enjoy!</p>",
        "<p>Hi {{customer_name}},</p><p>Welcome to {{store_name}}. We're glad you're here.</p>",
        "<p>Hi {{customer_name}},</p><p>Thanks for placing your first order <strong>{{order_number}}</strong> with us.</p>",
        "<p>Hi {{customer_name}},</p><p>Thanks again for order <strong>{{order_number}}</strong>. We appreciate your loyalty.</p>",
        "<p>Hi {{customer_name}},</p><p>Tracking number: <strong>{{tracking_number}}</strong> for order {{order_number}}.</p>",
        "<p>Hi {{customer_name}},</p><p>Your shipment for order <strong>{{order_number}}</strong> is in transit.</p>"
        "<p>Tracking: {{tracking_number}}</p>",
    }
)


def _has_broken_single_brace_tokens(html: str) -> bool:
    """True when body has {token} from an f-string bug instead of {{token}}."""
    text = html or ""
    if "{{" in text:
        return False
    return "{customer_name}" in text or "{store_name}" in text or "{order_number}" in text


def seed_store_automation_defaults(
    db: Session, store_id: str, *, refresh_legacy_bodies: bool = True
) -> None:
    """Create default templates + rules for a store (idempotent per event type).

    When refresh_legacy_bodies is True, upgrades templates that still use the old
    one-line starter copy (or broken single-brace placeholders) to the fuller versions.
    """
    for event_type, template_name, subject, body in _DEFAULTS:
        existing_rule = db.scalar(
            select(EmailAutomationRule).where(
                EmailAutomationRule.store_id == store_id,
                EmailAutomationRule.event_type == event_type.value,
            )
        )

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
                layout_preset="classic",
            )
            db.add(template)
            db.flush()
        elif refresh_legacy_bodies and (
            (template.body_html or "").strip() in _LEGACY_BODIES
            or _has_broken_single_brace_tokens(template.body_html or "")
        ):
            template.subject = subject
            template.body_html = body

        if not existing_rule:
            db.add(
                EmailAutomationRule(
                    store_id=store_id,
                    event_type=event_type.value,
                    template_id=template.id,
                    is_enabled=False,
                )
            )
    db.commit()
