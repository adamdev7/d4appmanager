"""Background full-inbox history scan — avoids HTTP/proxy gateway timeouts."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.ai_email_assistant.services.assistant_service import AIEmailAssistantService
from app.db.models import AIEmailAssistantSettings, User
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

_service = AIEmailAssistantService()
_running: set[str] = set()
_lock = asyncio.Lock()


def is_scan_running(settings_id: str) -> bool:
    return settings_id in _running


async def start_full_history_scan(
    *,
    settings_id: str,
    user_id: str,
    gmail_account_id: str,
    store_id: str | None,
    max_threads: int,
) -> bool:
    """Queue a background scan. Returns False if one is already running for this settings row."""
    async with _lock:
        if settings_id in _running:
            return False
        _running.add(settings_id)

    asyncio.create_task(
        _run_full_history_scan(
            settings_id=settings_id,
            user_id=user_id,
            gmail_account_id=gmail_account_id,
            store_id=store_id,
            max_threads=max_threads,
        )
    )
    return True


async def _run_full_history_scan(
    *,
    settings_id: str,
    user_id: str,
    gmail_account_id: str,
    store_id: str | None,
    max_threads: int,
) -> None:
    db = SessionLocal()
    try:
        settings_row = db.get(AIEmailAssistantSettings, settings_id)
        user = db.get(User, user_id)
        if not settings_row or not user:
            return

        settings_row.full_scan_status = "running"
        settings_row.full_scan_message = "Listing Gmail conversations…"
        settings_row.full_scan_progress = 0
        settings_row.full_scan_total = 0
        settings_row.full_scan_started_at = datetime.now(UTC)
        settings_row.full_scan_finished_at = None
        db.commit()

        def _progress(done: int, total: int, message: str) -> None:
            row = db.get(AIEmailAssistantSettings, settings_id)
            if not row:
                return
            row.full_scan_progress = done
            row.full_scan_total = total
            row.full_scan_message = message
            db.commit()

        result = await _service.full_history_scan(
            db,
            user,
            gmail_account_id=gmail_account_id,
            store_id=store_id,
            max_threads=max_threads,
            confirmed=True,
            progress_cb=_progress,
        )

        settings_row = db.get(AIEmailAssistantSettings, settings_id)
        if settings_row:
            settings_row.full_scan_status = "completed"
            settings_row.full_scan_message = result.message
            settings_row.full_scan_progress = result.threads_scanned
            settings_row.full_scan_total = result.threads_scanned
            settings_row.full_scan_finished_at = datetime.now(UTC)
            db.commit()
    except Exception as exc:
        logger.exception("Full history scan failed for settings %s", settings_id)
        try:
            settings_row = db.get(AIEmailAssistantSettings, settings_id)
            if settings_row:
                settings_row.full_scan_status = "failed"
                settings_row.full_scan_message = str(exc)[:500] or "Full inbox check failed"
                settings_row.full_scan_finished_at = datetime.now(UTC)
                db.commit()
        except Exception:
            logger.exception("Could not persist full-scan failure status")
    finally:
        db.close()
        async with _lock:
            _running.discard(settings_id)
