import logging

from app.core.email import send_email
from app.email_automation.sender.base import EmailMessagePayload, EmailSendResult

logger = logging.getLogger(__name__)


class SmtpFallbackSender:
    """Uses platform SMTP when no Gmail account is assigned (dev / fallback)."""

    provider_name = "smtp"

    async def send(
        self,
        *,
        account_id: str,
        message: EmailMessagePayload,
        store_id: str,
    ) -> EmailSendResult:
        _ = account_id, store_id
        try:
            await send_email(
                message.to,
                message.subject,
                message.html_body,
                message.text_body,
            )
            return EmailSendResult(success=True, provider=self.provider_name, message_id="smtp")
        except Exception as exc:
            logger.exception("SMTP fallback send failed")
            return EmailSendResult(success=False, provider=self.provider_name, error=str(exc))
