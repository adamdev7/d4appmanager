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


def config_from_settings(row: AIEmailAssistantSettings) -> EmailFilterConfig:
    return EmailFilterConfig(
        enabled=row.email_filter_enabled,
        filter_automated=row.filter_automated_emails,
        filter_non_business=row.filter_non_business_emails,
        custom_rules=row.filter_custom_rules or "",
        business_name=row.business_name,
        business_type=row.business_type,
        business_rules=row.rules or "",
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


def check_automated_heuristic(sender_email: str, subject: str, body: str) -> str | None:
    """Return skip reason if this looks like an automated/system email."""
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

_SHOPIFY_CONTACT_FORM = re.compile(
    r"Name:\s*(?P<name>.+?)\s+Email:\s*(?P<email>\S+@\S+)\s+Phone:\s*(?P<phone>.*?)\s+Body:\s*(?P<body>.+)",
    re.I | re.S,
)


def parse_shopify_contact_form(subject: str, body: str) -> tuple[str, str, str] | None:
    """Pull the shopper out of a Shopify 'new customer message' notification.

    Those emails arrive from mailer@shopify.com, but the buyer wrote the form.
    Returns (name, email, message) when the body has that form layout.
    """
    blob = f"{subject or ''}\n{body or ''}"
    if "contact form" not in blob.lower() and "new customer message" not in blob.lower():
        return None
    match = _SHOPIFY_CONTACT_FORM.search(body or "")
    if not match:
        return None
    address = match.group("email").strip().strip("<>").rstrip(".,;")
    message = match.group("body").strip()
    if "@" not in address or not message:
        return None
    return match.group("name").strip(), address, message


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
                thread_context=thread_context,
                known_customer=known_customer,
            )
        except Exception as exc:
            from app.ai_email_assistant.openai_errors import OpenAIServiceError

            if isinstance(exc, OpenAIServiceError) and exc.stop_autopilot:
                raise
            logger.warning("AI email filter classification failed: %s", exc)
            result = EmailFilterResult(should_reply=True)
    else:
        result = EmailFilterResult(should_reply=True)

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
