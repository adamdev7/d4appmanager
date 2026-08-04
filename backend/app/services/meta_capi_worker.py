"""24/7 Meta CAPI safety net: retry failures + reconcile Shopify paid orders."""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db.session import SessionLocal
from app.services.meta_capi_service import MetaCapiService

logger = logging.getLogger(__name__)

_stop_event: asyncio.Event | None = None
_task: asyncio.Task | None = None
_service = MetaCapiService()


async def _meta_capi_loop() -> None:
    assert _stop_event is not None
    interval = max(60, int(getattr(settings, "meta_capi_reconcile_seconds", 300) or 300))
    logger.info("meta_capi worker started interval=%ss", interval)
    # Short delay so API boot finishes before first Shopify pull
    try:
        await asyncio.wait_for(_stop_event.wait(), timeout=15)
        return
    except asyncio.TimeoutError:
        pass

    while not _stop_event.is_set():
        db = SessionLocal()
        try:
            summary = await _service.reconcile_all_configured_stores(db)
            if summary.get("sent") or summary.get("retried") or summary.get("failed"):
                logger.info("meta_capi reconcile %s", summary)
        except Exception:
            logger.exception("meta_capi reconcile cycle failed")
        finally:
            db.close()

        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            continue

    logger.info("meta_capi worker stopped")


def start_meta_capi_worker() -> None:
    global _task, _stop_event
    if _task and not _task.done():
        return
    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_meta_capi_loop())


async def stop_meta_capi_worker() -> None:
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
