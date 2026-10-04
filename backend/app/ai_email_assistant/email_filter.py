import json
import logging
import re
from dataclasses import dataclass

from typing import Any

from app.db.models import AIEmailAssistantSettings

logger = logging.getLogger(__name__)

# Tokens in the local-part or labels that almost always mean "do not reply".
AUTOMATED_SENDER_PATTERNS = re.compile(
    r"(^|[.@])(no[-_]?reply|donotreply|mailer-daemon|notifications?|newsletter|"
    r"marketing|automated|bounce|alerts?|account-security|mailgun|sendgrid|"
    r"postmaster)([@.]|$)",
    re.I,
)

# Merchant/platform mailboxes. Shopify order alerts come from these — they are
# not the customer writing in, even when the subject names the buyer.
PLATFORM_SENDER_DOMAINS = re.compile(
    r"@(?:.+\.)?(?:shopifyemail\.com|myshopify\.com|shopify\.com|mail\.shopify\.com|"
    r"amazonses\.com|sendgrid\.net|mailgun\.org)\b",
    re.I,
)

AUTOMATED_SUBJECT_PATTERNS = re.compile(
    r"(out of office|automatic reply|auto[- ]?reply|delivery status notification|"
    r"undeliverable|mail delivery failed|password reset|verify your email|"
    r"sign[- ]?in attempt|security alert)",
    re.I,
)

# Shopify's mail to the merchant when someone buys. The subject names the buyer,
# but the buyer did not write this email. A real customer says "I placed an order",
# not "Order #1234 placed by Jane".
_MERCHANT_ORDER_SUBJECT = re.compile(
    r"("
    r"order\s*#\s*\d+\s+placed\s+by\b|"
    r"\bplaced\s+by\b.{0,80}\border\s*#\s*\d+|"
    r"\ba\s+new\s+order\s+(was|has\s+been)\s+placed\b|"
    r"\byou\s+(have\s+)?received\s+a\s+new\s+order\b|"
    r"\byou\s+have\s+a\s+new\s+order\b|"
    r"\bnew\s+order\s*:\s*#?\d+"
    r")",
    re.I | re.S,
)
_SHOPIFY_ORDER_CARD = re.compile(r"\bitems?\s+from\s+shopify\b", re.I)
_SHOPIFY_ORDER_CARD_CUE = re.compile(r"\b(order\s+placed|view\s+order)\b", re.I)

# Language that means this person is shopping / asking about an order, not a random chat.
_CLIENT_CONVERSATION_HINTS = re.compile(
    r"\b(order|commande|#\d{3,}|shipping|shipped|livraison|refund|remboursement|"
    r"return|retour|package|colis|tracking|purchase|bought|payment|paiement|"
    r"cancel|annul|delivery|delivered|where is my|ou est ma)\b",
    re.I,
)

_CANCEL_VERBS = r"cancel+\w*|stop|end|pause|terminate"
_SUB_NOUNS = r"subscription|membership|recurring|auto[- ]?renew"

# Word boundaries matter: unanchored "end" matches inside "send" / "friend" / "weekend"
# and was parking ordinary "please send me my subscription…" mail for manual review.
_SUBSCRIPTION_CANCEL = re.compile(
    rf"(\b(?:{_CANCEL_VERBS})\b.{{0,60}}\b(?:{_SUB_NOUNS})\b|"
    rf"\b(?:{_SUB_NOUNS})\b.{{0,60}}\b(?:{_CANCEL_VERBS})\b|"
    r"unsubscribe\s+(me\s+)?from\s+(the\s+)?(subscription|membership|club|box))",
    re.I | re.S,
)

_UNRECOGNIZED_CHARGE = re.compile(
    r"("
    r"(don'?t|do\s+not|didn'?t|did\s+not)\s+(recognize|authori[sz]e|approve).{0,50}"
    r"(charge|payment|transaction|purchase)|"
    r"(didn'?t|did\s+not)\s+make\s+(this|that|any)\s+(charge|purchase|transaction)|"
    r"(unauthori[sz]ed|unrecognized|fraudulent|mystery)\s+(charge|payment|transaction)|"
    r"(charge|payment|transaction).{0,50}(don'?t|do\s+not|didn'?t)\s+(recognize|authori[sz]e)|"
    r"chargeback|dispute\s+(this\s+|the\s+|a\s+)?(charge|payment)|"
    r"stolen\s+(card|credit)|identity\s+theft|fraud\s+alert"
    r")",
    re.I | re.S,
)

_ADMIN_SITUATIONS = re.compile(
    r"("
    r"lawyer|attorney|legal\s+action|sue\s+(you|the\s+company)|small\s+claims|"
    r"better\s+business\s+bureau|\bbbb\b|consumer\s+protection|police\s+report"
    r")",
    re.I,
)


@dataclass
class EmailFilterResult:
    should_reply: bool
    reason: str | None = None
    category: str | None = None  # customer | automated | newsletter | personal | other | manual_review
    needs_manual_review: bool = False


@dataclass
class EmailFilterConfig:
    enabled: bool
    filter_automated: bool
    filter_non_business: bool
    custom_rules: str
    business_name: str
    business_type: str
    business_rules: str = ""
    policies: str = ""


def config_from_settings(row: AIEmailAssistantSettings) -> EmailFilterConfig:
    return EmailFilterConfig(
        enabled=row.email_filter_enabled,
        filter_automated=row.filter_automated_emails,
        filter_non_business=row.filter_non_business_emails,
        custom_rules=row.filter_custom_rules or "",
        business_name=row.business_name,
        business_type=row.business_type,
        business_rules=row.rules or "",
        policies=row.policies or "",
    )


def is_platform_sender(sender_email: str) -> bool:
    """True when From is Shopify/SES/etc. — not a person writing to support."""
    email_lower = (sender_email or "").lower().strip()
    if not email_lower:
        return False
    if PLATFORM_SENDER_DOMAINS.search(email_lower):
        return True
    if AUTOMATED_SENDER_PATTERNS.search(email_lower):
        return True
    return False


def merchant_order_alert_reason(subject: str, body: str) -> str | None:
    """Shopify (or similar) notice that a purchase happened. Never a customer email."""
    blob = f"{subject or ''}\n{body or ''}"
    subject_hit = _MERCHANT_ORDER_SUBJECT.search(blob)
    card_hit = _SHOPIFY_ORDER_CARD.search(blob) and _SHOPIFY_ORDER_CARD_CUE.search(blob)
    if not subject_hit and not card_hit:
        return None
    return (
        "This is a store notification that an order was placed, not from the customer. "
        "No reply was sent."
    )


def check_automated_heuristic(sender_email: str, subject: str, body: str) -> str | None:
    """Return skip reason if this looks like an automated/system email."""
    alert = merchant_order_alert_reason(subject, body)
    if alert:
        return alert
    if is_platform_sender(sender_email):
        if PLATFORM_SENDER_DOMAINS.search((sender_email or "").lower()):
            return (
                "This came from Shopify/a platform, not from the customer. "
                "Reply to messages whose From address is the customer's email."
            )
        return "Automated or no-reply sender address"

    if AUTOMATED_SUBJECT_PATTERNS.search(subject or ""):
        return "Subject looks like an automated or system notification"

    # Body boilerplate is only a signal for no-reply senders. Customer mail that
    # quotes a receipt often contains the same phrases.
    return None


def conversation_looks_like_client(
    *,
    thread_context: str | None,
    subject: str = "",
    body: str = "",
) -> bool:
    """True when Gmail history or this message reads like a shopper writing in."""
    ctx = (thread_context or "").strip()
    if ctx:
        if "EARLIER EMAILS" in ctx:
            return True
        # More than one message in the relationship (this thread or prior).
        if ctx.count("--- ") >= 2:
            return True
        if _CLIENT_CONVERSATION_HINTS.search(ctx):
            return True
    return bool(_CLIENT_CONVERSATION_HINTS.search(f"{subject}\n{body}"))


_HELP_GREETING = re.compile(
    r"\b(hello|hi|hey|bonjour|bonsoir|good morning|good afternoon|good evening)\b",
    re.I,
)

_FORM_EMAIL = re.compile(r"\bE-?mail\s*:\s*<?(?P<email>[^\s<>]+@[^\s<>]+?)>?(?=\s|$)", re.I)
_FORM_NAME = re.compile(
    r"\bName\s*:\s*(?P<name>.+?)(?=\s+(?:E-?mail|Phone|Body|Country Code|Id)\s*:|\n|$)",
    re.I,
)
_FORM_BODY = re.compile(r"\b(?:Body|Message|Comment)\s*:\s*(?P<body>.+)", re.I | re.S)


def is_shopify_customer_message(subject: str, body: str) -> bool:
    blob = f"{subject or ''}\n{body or ''}".lower()
    return (
        "contact form" in blob
        or "new customer message" in blob
        or "customer message" in (subject or "").lower()
    )


def parse_shopify_contact_form(subject: str, body: str) -> tuple[str, str, str] | None:
    """Pull the shopper out of a Shopify 'new customer message' notification.

    Those emails arrive from mailer@shopify.com, but the buyer wrote the form.
    Returns (name, email, message). Name or message may be empty; email is required.
    """
    if not is_shopify_customer_message(subject, body):
        return None
    text = body or ""
    email_match = _FORM_EMAIL.search(text)
    if not email_match:
        return None
    address = email_match.group("email").strip().rstrip(".,;")
    if "@" not in address or is_platform_sender(address):
        return None
    name_match = _FORM_NAME.search(text)
    body_match = _FORM_BODY.search(text)
    name = name_match.group("name").strip() if name_match else ""
    message = body_match.group("body").strip() if body_match else ""
    return name, address.lower(), message


def customer_reply_address(
    *,
    sender_email: str,
    subject: str = "",
    body: str = "",
    reply_to: str = "",
) -> str | None:
    """Who a reply must go to. Never a Shopify/platform mailbox."""
    if merchant_order_alert_reason(subject, body):
        return None
    if sender_email and not is_platform_sender(sender_email):
        return sender_email.lower()
    parsed = parse_shopify_contact_form(subject, body)
    if parsed:
        return parsed[1]
    from email.utils import parseaddr

    _, reply_addr = parseaddr(reply_to or "")
    if reply_addr and "@" in reply_addr and not is_platform_sender(reply_addr):
        return reply_addr.lower()
    return None


def message_asks_for_help(subject: str = "", body: str = "") -> bool:
    """True when a person is greeting the store or asking for information."""
    text = f"{subject}\n{body}".strip()
    if not text:
        return False
    if "?" in text or "？" in text:
        return True
    if _CLIENT_CONVERSATION_HINTS.search(text):
        return True
    return bool(_HELP_GREETING.search(text))


def detect_manual_review_reason(
    *,
    subject: str = "",
    body: str = "",
    thread_context: str | None = None,
) -> str | None:
    """Topics a teammate must finish: cancellation, disputed charges, legal mail.

    The customer still gets a reply. This only flags the case for the admin.
    """
    blob = f"{subject}\n{body}\n{thread_context or ''}"
    if _SUBSCRIPTION_CANCEL.search(blob):
        return "Subscription cancellation — a teammate needs to finish this."
    if re.search(r"cash\s+refund|refund\s+(?:me\s+)?(?:in\s+)?cash", blob, re.I):
        return "Cash refund request — a teammate needs to finish this."
    if _UNRECOGNIZED_CHARGE.search(blob):
        return "Unrecognized or disputed charge — a teammate needs to finish this."
    if _ADMIN_SITUATIONS.search(blob):
        return "This looks like a legal or dispute issue — a teammate needs to finish this."
    return None


def apply_known_customer_guard(
    result: EmailFilterResult,
    *,
    known_customer: bool,
    platform_sender: bool,
) -> EmailFilterResult:
    """Buyers always get a reply. Sensitive topics still go to a teammate, but not in silence."""
    if result.needs_manual_review or result.category == "manual_review":
        if platform_sender:
            return EmailFilterResult(
                should_reply=False,
                reason=result.reason or "Platform mail does not get a customer reply.",
                category="manual_review",
                needs_manual_review=True,
            )
        return EmailFilterResult(
            should_reply=True,
            reason=result.reason
            or "A teammate will handle the decision. The customer still gets a reply.",
            category="manual_review",
            needs_manual_review=True,
        )
    if platform_sender or result.should_reply:
        return result
    if not known_customer:
        return result
    if result.category in ("automated", "newsletter", "spam"):
        return result
    return EmailFilterResult(
        should_reply=True,
        reason="Sender is a known client (order or conversation history) — answering their email.",
        category="customer",
    )


def ensure_customer_is_answered(
    result: EmailFilterResult,
    *,
    subject: str,
    body: str,
    known_customer: bool,
    platform_sender: bool,
) -> EmailFilterResult:
    """Purchasers and people asking for information are never left without a reply."""
    if platform_sender or result.category in ("automated", "newsletter", "spam"):
        return result
    if result.should_reply:
        return result
    if not known_customer and not message_asks_for_help(subject, body):
        return result
    if result.needs_manual_review or result.category == "manual_review":
        return EmailFilterResult(
            should_reply=True,
            reason=result.reason
            or "A teammate will handle the decision. The customer still gets a reply.",
            category="manual_review",
            needs_manual_review=True,
        )
    return EmailFilterResult(
        should_reply=True,
        reason=result.reason
        or (
            "Sender is a known client — answering their email."
            if known_customer
            else "Customer is asking for information — answering their email."
        ),
        category="customer",
    )


def _reply_without_classifier(subject: str, body: str, *, known_customer: bool) -> EmailFilterResult:
    """When the model is unavailable: known buyers still get a reply; strangers must ask."""
    if known_customer or message_asks_for_help(subject, body):
        return EmailFilterResult(should_reply=True, category="customer")
    return EmailFilterResult(
        should_reply=False,
        reason=(
            "This email address is not on an order, and the message does not "
            "ask the store for help."
        ),
        category="other",
    )


async def evaluate_email_filter(
    config: EmailFilterConfig,
    *,
    sender: str,
    sender_email: str,
    subject: str,
    body: str,
    thread_context: str | None = None,
    ai: Any | None = None,
    known_customer: bool = False,
) -> EmailFilterResult:
    platform = is_platform_sender(sender_email)
    alert = merchant_order_alert_reason(subject, body)
    if alert:
        return EmailFilterResult(should_reply=False, reason=alert, category="automated")

    if not config.enabled:
        hold_reason = detect_manual_review_reason(
            subject=subject, body=body, thread_context=thread_context
        )
        if hold_reason and not platform:
            return EmailFilterResult(
                should_reply=True,
                reason=hold_reason,
                category="manual_review",
                needs_manual_review=True,
            )
        return EmailFilterResult(should_reply=True)

    if config.filter_automated:
        auto_reason = check_automated_heuristic(sender_email, subject, body)
        if auto_reason:
            return EmailFilterResult(
                should_reply=False,
                reason=auto_reason,
                category="automated",
            )

    hold_reason = detect_manual_review_reason(
        subject=subject, body=body, thread_context=thread_context
    )
    if hold_reason:
        # The teammate finishes the cancellation, dispute, or legal step.
        # The customer still receives a reply that says so.
        if platform:
            return EmailFilterResult(
                should_reply=False,
                reason=hold_reason,
                category="automated",
            )
        return EmailFilterResult(
            should_reply=True,
            reason=hold_reason,
            category="manual_review",
            needs_manual_review=True,
        )

    # Always use AI when available so it can read full thread history and decide whether
    # the issue was already answered (reply vs ignore / leave as read).
    result: EmailFilterResult
    if ai:
        try:
            result = await ai.classify_should_reply(
                sender=sender,
                subject=subject,
                email_body=body,
                business_name=config.business_name,
                business_type=config.business_type,
                custom_skip_rules=config.custom_rules,
                business_rules=config.business_rules,
                policies=config.policies,
                thread_context=thread_context,
                known_customer=known_customer,
            )
        except Exception as exc:
            from app.ai_email_assistant.openai_errors import OpenAIServiceError

            if isinstance(exc, OpenAIServiceError) and exc.stop_autopilot:
                raise
            logger.warning("AI email filter classification failed: %s", exc)
            result = _reply_without_classifier(
                subject, body, known_customer=known_customer
            )
    else:
        result = _reply_without_classifier(subject, body, known_customer=known_customer)

    if result.category == "personal" and not config.filter_non_business:
        result = EmailFilterResult(should_reply=True, reason=result.reason, category="customer")

    result = apply_known_customer_guard(
        result, known_customer=known_customer, platform_sender=platform
    )
    return ensure_customer_is_answered(
        result,
        subject=subject,
        body=body,
        known_customer=known_customer,
        platform_sender=platform,
    )


def parse_classification_json(raw: str) -> EmailFilterResult:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return EmailFilterResult(should_reply=True)

    should_reply = bool(data.get("should_reply", True))
    category = data.get("category")
    needs_manual_review = bool(data.get("needs_manual_review")) or category == "manual_review"
    if needs_manual_review:
        # Platform noise can stay silent. A person still gets a reply while a teammate
        # handles the refund, cancellation, or dispute.
        if category in ("automated", "newsletter", "spam"):
            should_reply = False
        else:
            should_reply = True
            category = "manual_review"
    reason = data.get("reason") or (
        "A teammate will handle the decision. The customer still gets a reply."
        if needs_manual_review and should_reply
        else (None if should_reply else "Classified as not requiring a business reply")
    )
    return EmailFilterResult(
        should_reply=should_reply,
        reason=reason,
        category=category,
        needs_manual_review=needs_manual_review,
    )
