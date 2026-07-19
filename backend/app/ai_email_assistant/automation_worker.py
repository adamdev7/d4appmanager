"""Background autopilot: sync unread Gmail and generate/send replies on a schedule."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_email_assistant.automation_control import stop_autopilot
from app.ai_email_assistant.openai_errors import OpenAIServiceError, openai_error_from_exception
from app.ai_email_assistant.services.assistant_service import AIEmailAssistantService
from app.config import settings
from app.core.openai_credentials import is_openai_configured
from app.db.models import AIEmailAssistantSettings, User
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_service = AIEmailAssistantService()
_stop_event: asyncio.Event | None = None
_task: asyncio.Task | None = None


async def run_automation_for_settings(settings_id: str, *, force: bool = False) -> dict:
    """Run one autopilot cycle for a single settings row."""
    db = SessionLocal()
    try:
        settings_row = db.get(AIEmailAssistantSettings, settings_id)
        if not settings_row:
            return {"skipped": True, "reason": "settings not found"}
        if not settings_row.automation_enabled and not force:
            return {"skipped": True, "reason": "automation disabled"}

        user = db.get(User, settings_row.user_id)
        if not user or not user.is_active:
            return {"skipped": True, "reason": "user inactive"}

        if not is_openai_configured(user):
            stop_autopilot(
                db,
                settings_row,
                "OpenAI API key is not configured. Add your key under Business context.",
            )
            return {
                "ok": False,
                "stopped": True,
                "error": settings_row.automation_last_error,
            }

        gmail_id = _service.resolve_gmail_account_id(db, user, settings_row)
        if not gmail_id:
            stop_autopilot(
                db,
                settings_row,
                "No connected Gmail account. Connect Gmail in Settings, then re-enable autopilot.",
            )
            return {
                "ok": False,
                "stopped": True,
                "error": settings_row.automation_last_error,
            }

        store_id = settings_row.store_id
        max_emails = settings_row.automation_max_emails_per_run

        await _service.sync_inbox(
            db,
            user,
            gmail_account_id=gmail_id,
            store_id=store_id,
            max_results=max_emails,
        )
        processed = await _service.process_pending_replies(
            db, user, settings_row, store_id=store_id, limit=max_emails
        )

        settings_row.automation_last_run_at = datetime.now(UTC)
        settings_row.automation_last_error = None
        db.commit()
        return {"ok": True, "processed": processed, "stopped": False}
    except OpenAIServiceError as exc:
        logger.warning("Autopilot AI error for settings %s: %s", settings_id, exc.user_message)
        row = db.get(AIEmailAssistantSettings, settings_id)
        if row and exc.stop_autopilot:
            stop_autopilot(db, row, exc.user_message)
            return {"ok": False, "stopped": True, "error": row.automation_last_error}
        if row:
            row.automation_last_error = exc.user_message[:500]
            db.commit()
        return {"ok": False, "stopped": False, "error": exc.user_message}
    except Exception as exc:
        logger.exception("Autopilot failed for settings %s: %s", settings_id, exc)
        parsed = openai_error_from_exception(exc)
        row = db.get(AIEmailAssistantSettings, settings_id)
        if row:
            if parsed.stop_autopilot:
                stop_autopilot(db, row, parsed.user_message)
                return {"ok": False, "stopped": True, "error": row.automation_last_error}
            row.automation_last_error = parsed.user_message[:500]
            db.commit()
        return {"ok": False, "stopped": False, "error": parsed.user_message}
    finally:
        db.close()


async def run_due_automations() -> None:
    """Run autopilot for all users whose interval has elapsed."""
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(AIEmailAssistantSettings).where(AIEmailAssistantSettings.automation_enabled.is_(True))
        ).all()
        now = datetime.now(UTC)
        for row in rows:
            interval = max(5, min(row.automation_interval_minutes, 120))
            due = True
            if row.automation_last_run_at:
                last = row.automation_last_run_at
                if last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                due = now >= last + timedelta(minutes=interval)
            if due:
                await run_automation_for_settings(row.id)
    finally:
        db.close()


async def _automation_loop() -> None:
    poll = max(30, settings.automation_poll_seconds)
    logger.info("AI Email Assistant autopilot started (poll every %ss)", poll)
    while _stop_event and not _stop_event.is_set():
        try:
            await run_due_automations()
        except Exception:
            logger.exception("Autopilot scheduler tick failed")
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=poll)
        except asyncio.TimeoutError:
            continue
    logger.info("AI Email Assistant autopilot stopped")


def start_automation_worker() -> None:
    global _stop_event, _task
    if _task and not _task.done():
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_automation_loop())


async def stop_automation_worker() -> None:
    global _task, _stop_event
    if _stop_event:
        _stop_event.set()
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except asyncio.TimeoutError:
            _task.cancel()
        _task = None
    _stop_event = None
