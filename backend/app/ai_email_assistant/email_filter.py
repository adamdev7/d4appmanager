import json
import logging
import re
from dataclasses import dataclass

from typing import Any

from app.db.models import AIEmailAssistantSettings

logger = logging.getLogger(__name__)

AUTOMATED_SENDER_PATTERNS = re.compile(
    r"(^|[.@])(no[-_]?reply|donotreply|mailer-daemon|notifications?|newsletter|"
    r"marketing|automated|system|bounce|alerts?|updates?|info@shopify|"
    r"account-security|mailgun|sendgrid|postmaster)([@.]|$)",
    re.I,
)

AUTOMATED_SUBJECT_PATTERNS = re.compile(
    r"(out of office|automatic reply|auto[- ]?reply|delivery status notification|"
    r"undeliverable|mail delivery failed|receipt from|your .+ (receipt|invoice) is ready|"
    r"password reset|verify your email|sign[- ]?in attempt|security alert)",
    re.I,
)

AUTOMATED_BODY_SNIPPETS = (
    "do not reply to this email",
    "this is an automated message",
    "this email was sent from a notification-only address",
    "unsubscribe",
    "you are receiving this email because",
    "no-reply",
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


def check_automated_heuristic(sender_email: str, subject: str, body: str) -> str | None:
    """Return skip reason if this looks like an automated/system email."""
    email_lower = sender_email.lower()
    if AUTOMATED_SENDER_PATTERNS.search(email_lower):
        return "Automated or no-reply sender address"

    if AUTOMATED_SUBJECT_PATTERNS.search(subject):
        return "Subject looks like an automated or system notification"

    body_lower = (body or "")[:2000].lower()
    for snippet in AUTOMATED_BODY_SNIPPETS:
        if snippet in body_lower and len(body_lower) < 800:
            return "Message appears to be an automated notification"

    return None


async def evaluate_email_filter(
    config: EmailFilterConfig,
    *,
    sender: str,
    sender_email: str,
    subject: str,
    body: str,
    thread_context: str | None = None,
    ai: Any | None = None,
) -> EmailFilterResult:
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
    if ai:
        try:
            return await ai.classify_should_reply(
                sender=sender,
                subject=subject,
                email_body=body,
                business_name=config.business_name,
                business_type=config.business_type,
                custom_skip_rules=config.custom_rules,
                thread_context=thread_context,
            )
        except Exception as exc:
            from app.ai_email_assistant.openai_errors import OpenAIServiceError

            if isinstance(exc, OpenAIServiceError) and exc.stop_autopilot:
                raise
            logger.warning("AI email filter classification failed: %s", exc)
            return EmailFilterResult(should_reply=True)

    return EmailFilterResult(should_reply=True)


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
