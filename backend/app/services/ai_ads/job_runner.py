from __future__ import annotations

import asyncio
import logging
import threading

from app.db.models import CreativeGenerationJob, Store, User
from app.db.session import SessionLocal
from app.services.ai_ads.job_progress import append_job_progress
from app.services.ai_ads.orchestrator import AdsAIOrchestrator

logger = logging.getLogger(__name__)

_thread_lock = threading.Lock()
_running: set[str] = set()


def is_job_running(job_id: str) -> bool:
    with _thread_lock:
        return job_id in _running


def enqueue_generation_job(job_id: str, api_key: str) -> None:
    """Start the job on the server event loop, or a background thread if none is running."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        loop.create_task(_run(job_id, api_key))
        return
    threading.Thread(target=_run_in_thread, args=(job_id, api_key), daemon=True).start()


def _run_in_thread(job_id: str, api_key: str) -> None:
    asyncio.run(_run(job_id, api_key))


async def _run(job_id: str, api_key: str) -> None:
    with _thread_lock:
        if job_id in _running:
            return
        _running.add(job_id)
    db = SessionLocal()
    try:
        job = db.get(CreativeGenerationJob, job_id)
        if not job:
            return
        if job.status not in ("QUEUED", "RUNNING"):
            return
        append_job_progress(
            job,
            step="start",
            title="Starting generation",
            detail="Worker picked up the job. Loading product and Meta history next.",
            pct=4,
        )
        job.status = "RUNNING"
        db.commit()
        user = db.get(User, job.user_id)
        store = db.get(Store, job.store_id)
        if not user or not store:
            job.status = "FAILED"
            job.error_message = "Missing user or store for this job"
            append_job_progress(
                job,
                step="error",
                title="Generation stopped",
                detail=job.error_message,
                pct=max(job.progress_pct or 0, 8),
            )
            db.commit()
            return
        orch = AdsAIOrchestrator(db, user, store, api_key)
        await orch.run_generation_job(job)
    except Exception:
        logger.exception("ai_ads job runner crashed job_id=%s", job_id)
        try:
            job = db.get(CreativeGenerationJob, job_id)
            if job and job.status in ("QUEUED", "RUNNING"):
                job.status = "FAILED"
                job.error_message = "Generation worker crashed. Try Generate again."
                append_job_progress(
                    job,
                    step="error",
                    title="Generation stopped",
                    detail=job.error_message,
                    pct=max(getattr(job, "progress_pct", 0) or 0, 8),
                )
                db.commit()
        except Exception:
            logger.exception("ai_ads job runner could not mark failed job_id=%s", job_id)
    finally:
        db.close()
        with _thread_lock:
            _running.discard(job_id)
