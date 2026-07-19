from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import GmailAccount, GmailAccountStatus, GmailStoreLink
from app.email_automation.sender.base import EmailMessagePayload, EmailSendResult
from app.email_automation.sender.gmail_sender import GmailApiSender
from app.email_automation.sender.smtp_fallback_sender import SmtpFallbackSender


class EmailSenderService:
    """Resolves sender account per store/rule and dispatches via Gmail or SMTP fallback."""

    def __init__(self, db: Session) -> None:
        self._db = db
        self._gmail = GmailApiSender(db)
        self._smtp = SmtpFallbackSender()

    def resolve_sender_account_id(
        self, store_id: str, preferred_gmail_account_id: str | None
    ) -> str | None:
        if preferred_gmail_account_id:
            account = self._db.get(GmailAccount, preferred_gmail_account_id)
            if account and account.status == GmailAccountStatus.CONNECTED.value:
                return account.id

        linked = self._db.scalar(
            select(GmailAccount)
            .join(GmailStoreLink, GmailStoreLink.gmail_account_id == GmailAccount.id)
            .where(
                GmailStoreLink.store_id == store_id,
                GmailAccount.status == GmailAccountStatus.CONNECTED.value,
            )
        )
        if linked:
            return linked.id

        default = self._db.scalar(
            select(GmailAccount).where(
                GmailAccount.is_default_sender.is_(True),
                GmailAccount.status == GmailAccountStatus.CONNECTED.value,
            )
        )
        return default.id if default else None

    async def send_automation_email(
        self,
        *,
        store_id: str,
        gmail_account_id: str | None,
        message: EmailMessagePayload,
    ) -> EmailSendResult:
        account_id = self.resolve_sender_account_id(store_id, gmail_account_id)
        if account_id:
            return await self._gmail.send(
                account_id=account_id,
                message=message,
                store_id=store_id,
            )
        return await self._smtp.send(
            account_id="smtp-fallback",
            message=message,
            store_id=store_id,
        )
