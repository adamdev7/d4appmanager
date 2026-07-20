import asyncio
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
# Gmail lists newest-first; we scan this many unread IDs then sort by date ascending.
_UNREAD_SCAN_CAP = 200


@dataclass
class GmailMessageSummary:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    body_text: str
    snippet: str


@dataclass
class ThreadHistoryAnalysis:
    """Where a Gmail conversation stands between the store and the customer."""

    thread_id: str
    subject: str
    latest_message_id: str
    latest_from_customer: bool
    team_ever_replied: bool
    never_answered_by_team: bool
    customer_sender: str
    customer_email: str
    latest_body: str
    message_count: int


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
        oldest_first: bool = True,
    ) -> list[dict]:
        """List unread inbox messages.

        When oldest_first is True (default), scans a window of unread IDs,
        sorts by Gmail internalDate ascending, and returns the oldest
        max_results — so autopilot clears backlog before newer mail.
        """
        token = await self._token(account)
        if not token:
            return []

        query = "in:inbox is:unread"
        if only_customer_messages and account.email:
            query += f" -from:{account.email}"

        want = max(1, min(max_results, 50))
        if not oldest_first:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{GMAIL_API}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"q": query, "maxResults": want},
                )
                resp.raise_for_status()
                return resp.json().get("messages", [])

        scan_cap = min(_UNREAD_SCAN_CAP, max(want * 4, 100))
        refs: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            while len(refs) < scan_cap:
                params: dict = {
                    "q": query,
                    "maxResults": min(50, scan_cap - len(refs)),
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(
                    f"{GMAIL_API}/messages",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("messages") or []
                if not batch:
                    break
                refs.extend(batch)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

            if not refs:
                return []

            sem = asyncio.Semaphore(10)

            async def _dated(ref: dict) -> tuple[int, dict]:
                async with sem:
                    try:
                        meta = await client.get(
                            f"{GMAIL_API}/messages/{ref['id']}",
                            headers={"Authorization": f"Bearer {token}"},
                            params={"format": "minimal"},
                        )
                        meta.raise_for_status()
                        body = meta.json()
                        ts = int(body.get("internalDate") or 0)
                        return ts, {
                            "id": body.get("id") or ref["id"],
                            "threadId": body.get("threadId") or ref.get("threadId"),
                        }
                    except Exception:
                        logger.debug(
                            "Failed to fetch date for unread %s", ref.get("id"), exc_info=True
                        )
                        return 0, ref

            dated = await asyncio.gather(*[_dated(r) for r in refs])

        dated.sort(key=lambda item: item[0])  # oldest first
        return [msg for _, msg in dated[:want]]

    async def list_all_inbox_threads(
        self,
        account: GmailAccount,
        *,
        max_threads: int = 100,
        only_customer_messages: bool = True,
    ) -> list[dict]:
        """List inbox threads from the beginning of the mailbox (paginated)."""
        token = await self._token(account)
        if not token:
            return []

        query = "in:inbox"
        if only_customer_messages and account.email:
            query += f" -from:{account.email}"

        threads: list[dict] = []
        page_token: str | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            while len(threads) < max_threads:
                params: dict = {
                    "q": query,
                    "maxResults": min(50, max_threads - len(threads)),
                }
                if page_token:
                    params["pageToken"] = page_token
                resp = await client.get(
                    f"{GMAIL_API}/threads",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                resp.raise_for_status()
                data = resp.json()
                batch = data.get("threads") or []
                if not batch:
                    break
                threads.extend(batch)
                page_token = data.get("nextPageToken")
                if not page_token:
                    break

        return threads[:max_threads]

    async def analyze_thread_history(
        self, account: GmailAccount, thread_id: str
    ) -> ThreadHistoryAnalysis | None:
        """Load a full thread and determine reply state (who spoke last, ever answered)."""
        messages = await self.get_thread_conversation(account, thread_id, max_messages=40)
        if not messages:
            return None

        team_ever = any(m.is_from_business for m in messages)
        last = messages[-1]
        latest_from_customer = not last.is_from_business

        # Subject comes from Gmail metadata if available; fall back to first line
        subject = "(no subject)"
        token = await self._token(account)
        if token:
            async with httpx.AsyncClient(timeout=30) as client:
                meta = await client.get(
                    f"{GMAIL_API}/threads/{thread_id}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={"format": "metadata", "metadataHeaders": ["From", "Subject"]},
                )
                if meta.status_code < 400:
                    raw = meta.json().get("messages") or []
                    if raw:
                        headers = {
                            h["name"].lower(): h["value"]
                            for h in raw[-1].get("payload", {}).get("headers", [])
                        }
                        subject = headers.get("subject") or subject

        # Prefer the latest *customer* message as the one to answer
        customer_msgs = [m for m in messages if not m.is_from_business]
        focus = customer_msgs[-1] if customer_msgs else last

        return ThreadHistoryAnalysis(
            thread_id=thread_id,
            subject=subject,
            latest_message_id=focus.message_id,
            latest_from_customer=latest_from_customer,
            team_ever_replied=team_ever,
            never_answered_by_team=not team_ever,
            customer_sender=focus.from_header,
            customer_email=self.parse_sender_email(focus.from_header),
            latest_body=focus.body_text,
            message_count=len(messages),
        )

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
        """Remove the UNREAD label so the message stays read in Gmail."""
        token = await self._token(account)
        if not token:
            return False

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{GMAIL_API}/messages/{message_id}/modify",
                headers={"Authorization": f"Bearer {token}"},
                json={"removeLabelIds": ["UNREAD"]},
            )
            if resp.status_code >= 400:
                logger.warning(
                    "Gmail mark_as_read failed for %s: %s %s",
                    message_id,
                    resp.status_code,
                    resp.text[:200],
                )
                return False
            return True
