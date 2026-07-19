from dataclasses import dataclass
from typing import Protocol


@dataclass
class InboundMessage:
    """Provider-agnostic inbound customer message (Gmail today; WhatsApp/Shopify later)."""

    channel: str
    external_id: str
    thread_id: str
    sender: str
    subject: str
    body_text: str


@dataclass
class OutboundReply:
    thread_id: str
    to: str
    subject: str
    body_text: str
    in_reply_to_id: str | None = None


class MessageChannel(Protocol):
    """Future: implement for WhatsApp, Shopify Inbox, Instagram DM, etc."""

    channel_name: str

    async def fetch_unread(self, *, limit: int) -> list[InboundMessage]: ...

    async def send_reply(self, reply: OutboundReply) -> str | None: ...
