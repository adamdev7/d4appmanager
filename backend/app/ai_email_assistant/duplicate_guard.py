"""Prevent multiple AI replies to the same Gmail conversation."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AIEmailReply, AIReplyStatus, InboxEmail, InboxEmailStatus

logger = logging.getLogger(__name__)

ALREADY_REPLIED_REASON = "Already replied in this email conversation (duplicate prevention)."
GENERATING_MODEL_MARKER = "generating"

# Statuses that mean a send is done or in flight — never send again for this reply/thread.
_ACTIVE_REPLY_STATUSES = (
    AIReplyStatus.DRAFT.value,
    AIReplyStatus.SENDING.value,
    AIReplyStatus.SENT.value,
)


def find_sent_reply(email: InboxEmail) -> AIEmailReply | None:
    for reply in email.replies or []:
        if reply.status == AIReplyStatus.SENT.value:
            return reply
    return None


def find_active_draft(email: InboxEmail) -> AIEmailReply | None:
    """Return draft or in-flight send for this inbox row (most recent first)."""
    drafts = [
        r
        for r in (email.replies or [])
        if r.status in (AIReplyStatus.DRAFT.value, AIReplyStatus.SENDING.value)
    ]
    if not drafts:
        return None
    return sorted(drafts, key=lambda r: r.created_at, reverse=True)[0]


def thread_has_sent_reply(
    db: Session,
    *,
    gmail_account_id: str,
    thread_id: str,
    exclude_reply_id: str | None = None,
) -> bool:
    """True if any OTHER reply in this Gmail thread was already sent (or is sending)."""
    rows = db.scalars(
        select(InboxEmail).where(
            InboxEmail.gmail_account_id == gmail_account_id,
            InboxEmail.thread_id == thread_id,
        )
    ).all()
    for row in rows:
        for reply in row.replies or []:
            if exclude_reply_id and reply.id == exclude_reply_id:
                continue
            if reply.status in (AIReplyStatus.SENT.value, AIReplyStatus.SENDING.value):
                return True
        if row.status == InboxEmailStatus.REPLIED.value:
            # Another inbox row in this thread already finished a send.
            if exclude_reply_id and any(
                r.id == exclude_reply_id for r in (row.replies or [])
            ):
                continue
            return True
    return False


def thread_has_answered_in_db(
    db: Session,
    *,
    gmail_account_id: str,
    thread_id: str,
    exclude_inbox_id: str | None = None,
) -> bool:
    """True if this conversation already has a draft/send — skip creating another."""
    rows = db.scalars(
        select(InboxEmail).where(
            InboxEmail.gmail_account_id == gmail_account_id,
            InboxEmail.thread_id == thread_id,
        )
    ).all()

    for row in rows:
        if exclude_inbox_id and row.id == exclude_inbox_id:
            # Still block if THIS inbox row already has an active reply.
            for reply in row.replies or []:
                if reply.status in _ACTIVE_REPLY_STATUSES:
                    return True
            if row.status == InboxEmailStatus.REPLIED.value:
                return True
            continue
        if row.status == InboxEmailStatus.REPLIED.value:
            return True
        if row.status == InboxEmailStatus.DRAFT_PENDING.value and row.replies:
            return True
        for reply in row.replies or []:
            if reply.status in _ACTIVE_REPLY_STATUSES:
                return True
    return False


def mark_thread_siblings_handled(
    db: Session,
    *,
    gmail_account_id: str,
    thread_id: str,
    keep_inbox_id: str,
    reason: str = ALREADY_REPLIED_REASON,
) -> int:
    """Mark other messages in the same thread so autopilot does not reply again."""
    siblings = db.scalars(
        select(InboxEmail).where(
            InboxEmail.gmail_account_id == gmail_account_id,
            InboxEmail.thread_id == thread_id,
            InboxEmail.id != keep_inbox_id,
            InboxEmail.status.in_(
                (
                    InboxEmailStatus.NEW.value,
                    InboxEmailStatus.DRAFT_PENDING.value,
                )
            ),
        )
    ).all()
    count = 0
    for row in siblings:
        # Do not clobber a draft that is mid-send on another row.
        active = find_active_draft(row)
        if active and active.status == AIReplyStatus.SENDING.value:
            continue
        row.status = InboxEmailStatus.SKIPPED.value
        row.skip_reason = reason
        count += 1
    if count:
        db.commit()
    return count
