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


@dataclass
class EmailFilterResult:
    should_reply: bool
    reason: str | None = None
    category: str | None = None  # customer | automated | newsletter | personal | other


@dataclass
class EmailFilterConfig:
    enabled: bool
    filter_automated: bool
    filter_non_business: bool
    custom_rules: str
    business_name: str
    business_type: str


def config_from_settings(row: AIEmailAssistantSettings) -> EmailFilterConfig:
    return EmailFilterConfig(
        enabled=row.email_filter_enabled,
        filter_automated=row.filter_automated_emails,
        filter_non_business=row.filter_non_business_emails,
        custom_rules=row.filter_custom_rules or "",
        business_name=row.business_name,
        business_type=row.business_type,
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


def apply_known_customer_guard(
    result: EmailFilterResult,
    *,
    known_customer: bool,
    platform_sender: bool,
) -> EmailFilterResult:
    """Never treat a Shopify buyer as 'not a client' just because the AI guessed personal."""
    if not known_customer or platform_sender or result.should_reply:
        return result
    if result.category in ("already_resolved", "acknowledgment"):
        return result
    return EmailFilterResult(
        should_reply=True,
        reason="Sender matches a Shopify customer — answering their email.",
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
        return EmailFilterResult(should_reply=True)

    if config.filter_automated:
        auto_reason = check_automated_heuristic(sender_email, subject, body)
        if auto_reason:
            return EmailFilterResult(
                should_reply=False,
                reason=auto_reason,
                category="automated",
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

    return apply_known_customer_guard(
        result, known_customer=known_customer, platform_sender=platform
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
    reason = data.get("reason") or (
        None if should_reply else "Classified as not requiring a business reply"
    )
    category = data.get("category")
    return EmailFilterResult(should_reply=should_reply, reason=reason, category=category)
