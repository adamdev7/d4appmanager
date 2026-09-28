"""Weekly creative generation scheduler. Does not auto-publish ads.

Each tick: finish/resume weekly runs whose job ended or was abandoned, then start a batch for
every enabled store whose weekday + hour (store timezone) has passed this week and has no
scheduled run yet. That one rule covers the on-time run, catch-up after downtime, and the
first run right after the toggle is switched on.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from app.config import settings
from app.db.session import SessionLocal
from app.services.ai_ads.weekly_runs import reconcile_runs, schedule_due_runs

logger = logging.getLogger(__name__)

_stop: asyncio.Event | None = None
_task: asyncio.Task | None = None
_last_tick_at: datetime | None = None


def scheduler_heartbeat() -> datetime | None:
    return _last_tick_at


def start_ai_ads_worker() -> None:
    global _stop, _task
    _stop = asyncio.Event()
    _task = asyncio.create_task(_loop())
    logger.info(
        "ai_ads weekly scheduler started enabled=%s hour=%s poll=%ss",
        settings.ai_ad_weekly_scheduler_enabled,
        settings.ai_ad_weekly_hour,
        max(30, settings.ai_ad_poll_seconds),
    )


async def stop_ai_ads_worker() -> None:
    global _stop, _task
    if _stop:
        _stop.set()
    if _task:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):
            pass
    _task = None


async def _loop() -> None:
    assert _stop is not None
    while not _stop.is_set():
        try:
            await _tick()
        except Exception:
            logger.exception("ai_ads weekly worker tick failed")
        try:
            await asyncio.wait_for(_stop.wait(), timeout=max(30, settings.ai_ad_poll_seconds))
        except (TimeoutError, asyncio.TimeoutError):
            continue


async def _tick() -> None:
    global _last_tick_at
    _last_tick_at = datetime.now(UTC)
    db = SessionLocal()
    try:
        try:
            reconcile_runs(db)
        except Exception:
            logger.exception("ai_ads weekly reconcile failed")
            db.rollback()
        try:
            from app.services.ai_ads.director.service import reconcile_reports

            reconcile_reports(db)
        except Exception:
            logger.exception("ai_ads director reconcile failed")
            db.rollback()
        if not settings.ai_ad_weekly_scheduler_enabled:
            return
        started = schedule_due_runs(db)
        if started:
            logger.info("ai_ads weekly scheduler started %s run(s): %s", len(started), ", ".join(started))
    finally:
        db.close()
