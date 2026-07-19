import logging
import re

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import EmailAutomationRule, EmailSendLog, EmailSendStatus, Store
from app.email_automation.events import AutomationEventType, derive_automation_events
from app.email_automation.sender.base import EmailMessagePayload
from app.email_automation.sender.service import EmailSenderService
from app.email_automation.variable_resolver import build_template_context, resolve_template_text

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _html_to_plain(html: str) -> str:
    text = _HTML_TAG_RE.sub("", html)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


class EmailTriggerService:
    """Processes Shopify webhook payloads and runs matching automation rules."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._sender = EmailSenderService(db)

    async def process_shopify_webhook(
        self, *, store_id: str, topic: str, payload: dict
    ) -> list[dict]:
        store = self._db.get(Store, store_id)
        if not store:
            logger.warning("Email automation: store %s not found", store_id)
            return []

        events = derive_automation_events(topic, payload)
        results: list[dict] = []
        for event_type in events:
            result = await self._process_event(
                store=store,
                event_type=event_type,
                payload=payload,
            )
            if result:
                results.append(result)
        return results

    def _recipient_email(self, payload: dict) -> str | None:
        customer = payload.get("customer") or {}
        email = customer.get("email") or payload.get("email") or payload.get("contact_email")
        if email and isinstance(email, str):
            return email.strip().lower()
        return None

    async def _process_event(
        self,
        *,
        store: Store,
        event_type: AutomationEventType,
        payload: dict,
    ) -> dict | None:
        rule = self._db.scalar(
            select(EmailAutomationRule)
            .where(
                EmailAutomationRule.store_id == store.id,
                EmailAutomationRule.event_type == event_type.value,
                EmailAutomationRule.is_enabled.is_(True),
            )
            .options(joinedload(EmailAutomationRule.template))
        )
        if not rule or not rule.template:
            return None

        recipient = self._recipient_email(payload)
        if not recipient:
            self._log_send(
                store_id=store.id,
                rule_id=rule.id,
                event_type=event_type.value,
                recipient="",
                subject="",
                status=EmailSendStatus.SKIPPED.value,
                error="No recipient email in webhook payload",
            )
            return {"event_type": event_type.value, "status": "skipped", "reason": "no_recipient"}

        context = build_template_context(payload, store.name)
        subject = resolve_template_text(rule.template.subject, context)
        body_html = resolve_template_text(rule.template.body_html, context)

        message = EmailMessagePayload(
            to=recipient,
            subject=subject,
            html_body=body_html,
            text_body=_html_to_plain(body_html),
        )

        send_result = await self._sender.send_automation_email(
            store_id=store.id,
            gmail_account_id=rule.gmail_account_id,
            message=message,
        )

        status = EmailSendStatus.SENT.value if send_result.success else EmailSendStatus.FAILED.value
        self._log_send(
            store_id=store.id,
            rule_id=rule.id,
            event_type=event_type.value,
            recipient=recipient,
            subject=subject,
            status=status,
            error=send_result.error,
            provider_message_id=send_result.message_id,
        )

        logger.info(
            "Automation %s for store %s -> %s (%s)",
            event_type.value,
            store.shop_domain,
            recipient,
            status,
        )

        return {
            "event_type": event_type.value,
            "status": status,
            "recipient": recipient,
            "provider": send_result.provider,
        }

    def _log_send(
        self,
        *,
        store_id: str,
        rule_id: str | None,
        event_type: str,
        recipient: str,
        subject: str,
        status: str,
        error: str | None = None,
        provider_message_id: str | None = None,
    ) -> None:
        self._db.add(
            EmailSendLog(
                store_id=store_id,
                rule_id=rule_id,
                event_type=event_type,
                recipient=recipient,
                subject=subject,
                status=status,
                error_message=error,
                provider_message_id=provider_message_id,
            )
        )
        self._db.commit()
