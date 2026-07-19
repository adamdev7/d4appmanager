from dataclasses import dataclass
from typing import Protocol


@dataclass
class EmailMessagePayload:
    to: str
    subject: str
    html_body: str
    text_body: str | None = None
    reply_to: str | None = None


@dataclass
class EmailSendResult:
    success: bool
    provider: str
    message_id: str | None = None
    error: str | None = None


class EmailSender(Protocol):
    """Provider-agnostic send interface (Gmail API, SMTP, etc.)."""

    provider_name: str

    async def send(
        self,
        *,
        account_id: str,
        message: EmailMessagePayload,
        store_id: str,
    ) -> EmailSendResult: ...
