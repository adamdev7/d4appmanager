from __future__ import annotations

import asyncio
import logging

from app.db.models import CreativeGenerationJob, Store, User
from app.db.session import SessionLocal
from app.services.ai_ads.orchestrator import AdsAIOrchestrator

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_running: set[str] = set()


def enqueue_generation_job(job_id: str, api_key: str) -> None:
    asyncio.create_task(_run(job_id, api_key))


async def _run(job_id: str, api_key: str) -> None:
    async with _lock:
        if job_id in _running:
            return
        _running.add(job_id)
    db = SessionLocal()
    try:
        job = db.get(CreativeGenerationJob, job_id)
        if not job:
            return
        user = db.get(User, job.user_id)
        store = db.get(Store, job.store_id)
        if not user or not store:
            return
        orch = AdsAIOrchestrator(db, user, store, api_key)
        await orch.run_generation_job(job)
    except Exception:
        logger.exception("ai_ads job runner crashed job_id=%s", job_id)
    finally:
        db.close()
        _running.discard(job_id)
