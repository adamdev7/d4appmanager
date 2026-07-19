import base64
import logging
from email.message import EmailMessage

import httpx
from sqlalchemy.orm import Session

from app.db.models import GmailAccount, GmailAccountStatus
from app.email_automation.sender.base import EmailMessagePayload, EmailSendResult
from app.integrations.gmail.auth import get_gmail_access_token

logger = logging.getLogger(__name__)

GMAIL_SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


class GmailApiSender:
    provider_name = "gmail"

    def __init__(self, db: Session) -> None:
        self._db = db

    async def _get_access_token(self, account: GmailAccount) -> str | None:
        return await get_gmail_access_token(self._db, account)

    def _build_raw_message(self, account: GmailAccount, message: EmailMessagePayload) -> str:
        em = EmailMessage()
        em["To"] = message.to
        em["From"] = account.email
        em["Subject"] = message.subject
        if message.reply_to:
            em["Reply-To"] = message.reply_to
        plain = message.text_body or ""
        em.set_content(plain, subtype="plain")
        em.add_alternative(message.html_body, subtype="html")
        return base64.urlsafe_b64encode(em.as_bytes()).decode()

    async def send(
        self,
        *,
        account_id: str,
        message: EmailMessagePayload,
        store_id: str,
    ) -> EmailSendResult:
        _ = store_id
        account = self._db.get(GmailAccount, account_id)
        if not account or account.status != GmailAccountStatus.CONNECTED.value:
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                error="Gmail account not connected",
            )

        access_token = await self._get_access_token(account)
        if not access_token:
            return EmailSendResult(
                success=False,
                provider=self.provider_name,
                error="Could not obtain Gmail access token",
            )

        raw = self._build_raw_message(account, message)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GMAIL_SEND_URL,
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            if resp.status_code >= 400:
                return EmailSendResult(
                    success=False,
                    provider=self.provider_name,
                    error=resp.text[:500],
                )
            data = resp.json()
            return EmailSendResult(
                success=True,
                provider=self.provider_name,
                message_id=data.get("id"),
            )
