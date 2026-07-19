import base64
import logging
import re
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr

import httpx
from sqlalchemy.orm import Session

from app.ai_email_assistant.thread_context import ThreadMessagePart
from app.db.models import GmailAccount
from app.integrations.gmail.auth import get_gmail_access_token

logger = logging.getLogger(__name__)

GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


@dataclass
class GmailMessageSummary:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    body_text: str
    snippet: str


class GmailInboxClient:
    """Read inbox and send threaded replies via Gmail API."""

    def __init__(self, db: Session) -> None:
        self._db = db

    async def _token(self, account: GmailAccount) -> str | None:
        return await get_gmail_access_token(self._db, account)

    async def list_unread_messages(
        self,
        account: GmailAccount,
        *,
        max_results: int = 20,
        only_customer_messages: bool = True,
    ) -> list[dict]:
        token = await self._token(account)
        if not token:
            return []

        query = "in:inbox is:unread"
        if only_customer_messages and account.email:
            query += f" -from:{account.email}"

        params = {
            "q": query,
            "maxResults": min(max_results, 50),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GMAIL_API}/messages",
                headers={"Authorization": f"Bearer {token}"},
                params=params,
            )
            resp.raise_for_status()
            return resp.json().get("messages", [])

    async def get_thread_conversation(
        self,
        account: GmailAccount,
        thread_id: str,
        *,
        max_messages: int = 12,
    ) -> list[ThreadMessagePart]:
        """Fetch recent messages in a thread for AI context (oldest → newest)."""
        token = await self._token(account)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{GMAIL_API}/threads/{thread_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "full"},
            )
            if resp.status_code >= 400:
                logger.warning("Could not load thread %s: %s", thread_id, resp.status_code)
                return []
            data = resp.json()

        our_email = account.email.lower()
        raw_messages = data.get("messages") or []
        selected = raw_messages[-max_messages:] if len(raw_messages) > max_messages else raw_messages

        parts: list[ThreadMessagePart] = []
        for msg in selected:
            msg_id = msg.get("id", "")
            headers = {
                h["name"].lower(): h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            from_header = headers.get("from", "Unknown")
            body = self._extract_body(msg.get("payload", {})) or msg.get("snippet", "")
            from_lower = from_header.lower()
            is_ours = our_email in from_lower
            parts.append(
                ThreadMessagePart(
                    message_id=msg_id,
                    from_header=from_header,
                    body_text=body,
                    is_from_business=is_ours,
                )
            )
        return parts

    async def get_message(self, account: GmailAccount, message_id: str) -> GmailMessageSummary | None:
        token = await self._token(account)
        if not token:
            return None

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GMAIL_API}/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "full"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()

        headers = {h["name"].lower(): h["value"] for h in data.get("payload", {}).get("headers", [])}
        sender = headers.get("from", "")
        subject = headers.get("subject", "(no subject)")
        body_text = self._extract_body(data.get("payload", {}))
        snippet = data.get("snippet", "")

        return GmailMessageSummary(
            message_id=message_id,
            thread_id=data.get("threadId", message_id),
            sender=sender,
            subject=subject,
            body_text=body_text or snippet,
            snippet=snippet,
        )

    def _extract_body(self, payload: dict) -> str:
        mime = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data")
        if body_data and mime.startswith("text/"):
            return self._decode_body(body_data)

        parts = payload.get("parts", [])
        plain = ""
        html = ""
        for part in parts:
            part_mime = part.get("mimeType", "")
            part_body = part.get("body", {}).get("data")
            if part_body and part_mime == "text/plain":
                plain = self._decode_body(part_body)
            elif part_body and part_mime == "text/html":
                html = self._strip_html(self._decode_body(part_body))
            elif part.get("parts"):
                nested = self._extract_body(part)
                if nested:
                    return nested
        return plain or html

    @staticmethod
    def _decode_body(data: str) -> str:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")

    @staticmethod
    def _strip_html(html: str) -> str:
        text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
        text = re.sub(r"</p>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
        return re.sub(r"\n{3,}", "\n\n", text).strip()

    @staticmethod
    def parse_sender_email(from_header: str) -> str:
        _, addr = parseaddr(from_header)
        return addr.lower() if addr else from_header

    async def send_thread_reply(
        self,
        account: GmailAccount,
        *,
        to: str,
        subject: str,
        body_text: str,
        thread_id: str,
        in_reply_to_message_id: str | None = None,
    ) -> dict | None:
        token = await self._token(account)
        if not token:
            return None

        em = EmailMessage()
        em["To"] = to
        em["From"] = account.email
        reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
        em["Subject"] = reply_subject
        em.set_content(body_text, subtype="plain")
        if in_reply_to_message_id:
            em["In-Reply-To"] = f"<{in_reply_to_message_id}>"
            em["References"] = f"<{in_reply_to_message_id}>"

        raw = base64.urlsafe_b64encode(em.as_bytes()).decode()
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GMAIL_API}/messages/send",
                headers={"Authorization": f"Bearer {token}"},
                json={"raw": raw, "threadId": thread_id},
            )
            if resp.status_code >= 400:
                logger.error("Gmail send failed: %s", resp.text[:500])
                return None
            return resp.json()

    async def we_sent_last_in_thread(self, account: GmailAccount, thread_id: str) -> bool:
        """True if the latest message in the thread is from our Gmail account."""
        token = await self._token(account)
        if not token:
            return False

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GMAIL_API}/threads/{thread_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "metadata", "metadataHeaders": "From"},
            )
            if resp.status_code >= 400:
                return False
            data = resp.json()

        messages = data.get("messages") or []
        if not messages:
            return False

        last = messages[-1]
        headers = {h["name"].lower(): h["value"] for h in last.get("payload", {}).get("headers", [])}
        from_header = headers.get("from", "").lower()
        our_email = account.email.lower()
        return our_email in from_header

    async def mark_thread_as_read(self, account: GmailAccount, thread_id: str) -> bool:
        """Mark every message in a thread as read so it is not picked up again."""
        token = await self._token(account)
        if not token:
            return False

        async with httpx.AsyncClient(timeout=30) as client:
            thread_resp = await client.get(
                f"{GMAIL_API}/threads/{thread_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "minimal"},
            )
            if thread_resp.status_code >= 400:
                return False
            message_ids = [m["id"] for m in thread_resp.json().get("messages", [])]

            ok = True
            for msg_id in message_ids:
                mod = await client.post(
                    f"{GMAIL_API}/messages/{msg_id}/modify",
                    headers={"Authorization": f"Bearer {token}"},
                    json={"removeLabelIds": ["UNREAD"]},
                )
                if mod.status_code >= 400:
                    ok = False
            return ok

    async def is_message_unread(self, account: GmailAccount, message_id: str) -> bool:
        """True if Gmail still has the UNREAD label on this message."""
        token = await self._token(account)
        if not token:
            return False

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{GMAIL_API}/messages/{message_id}",
                headers={"Authorization": f"Bearer {token}"},
                params={"format": "minimal"},
            )
            if resp.status_code >= 400:
                return False
            return "UNREAD" in (resp.json().get("labelIds") or [])

    async def mark_as_read(self, account: GmailAccount, message_id: str) -> bool:
        token = await self._token(account)
        if not token:
            return False

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GMAIL_API}/messages/{message_id}/modify",
                headers={"Authorization": f"Bearer {token}"},
                json={"removeLabelIds": ["UNREAD"]},
            )
            return resp.status_code < 400
