"""Prevent multiple AI replies to the same Gmail conversation."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AIEmailReply, AIReplyStatus, InboxEmail, InboxEmailStatus

logger = logging.getLogger(__name__)

ALREADY_REPLIED_REASON = "Already replied in this email conversation (duplicate prevention)."


def thread_has_answered_in_db(
    db: Session,
    *,
    gmail_account_id: str,
    thread_id: str,
    exclude_inbox_id: str | None = None,
) -> bool:
    rows = db.scalars(
        select(InboxEmail).where(
            InboxEmail.gmail_account_id == gmail_account_id,
            InboxEmail.thread_id == thread_id,
        )
    ).all()

    for row in rows:
        if exclude_inbox_id and row.id == exclude_inbox_id:
            continue
        if row.status == InboxEmailStatus.REPLIED.value:
            return True
        if row.status == InboxEmailStatus.DRAFT_PENDING.value and row.replies:
            return True
        for reply in row.replies:
            if reply.status in (AIReplyStatus.SENT.value, AIReplyStatus.DRAFT.value):
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
            InboxEmail.status == InboxEmailStatus.NEW.value,
        )
    ).all()
    count = 0
    for row in siblings:
        row.status = InboxEmailStatus.SKIPPED.value
        row.skip_reason = reason
        count += 1
    if count:
        db.commit()
    return count
