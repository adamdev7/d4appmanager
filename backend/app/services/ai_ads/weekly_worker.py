"""Weekly creative generation worker. Does not auto-publish ads."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.core.openai_credentials import resolve_openai_api_key
from app.db.models import CreativeGenerationJob, Store, StoreAIAdsSettings, User
from app.db.session import SessionLocal
from app.services.ai_ads.job_runner import enqueue_generation_job
from app.services.ai_ads.orchestrator import AdsAIOrchestrator

logger = logging.getLogger(__name__)

_stop: asyncio.Event | None = None
_task: asyncio.Task | None = None


def start_ai_ads_worker() -> None:
    global _stop, _task
    _stop = asyncio.Event()
    _task = asyncio.create_task(_loop())


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
    if not settings.ai_ad_generation_enabled:
        return
    today = datetime.now(UTC).strftime("%A").lower()
    wanted = (settings.ai_ad_generation_day or "monday").strip().lower()
    if today != wanted:
        return
    db = SessionLocal()
    try:
        rows = db.scalars(
            select(StoreAIAdsSettings).where(StoreAIAdsSettings.weekly_generation_enabled.is_(True))
        ).all()
        for row in rows:
            last = row.last_weekly_run_at
            if last and last.date() == datetime.now(UTC).date():
                continue
            store = db.get(Store, row.store_id)
            if not store:
                continue
            user = db.get(User, store.owner_id)
            if not user:
                continue
            api_key = resolve_openai_api_key(user)
            if not api_key:
                row.last_weekly_error = "OpenAI API key is not configured"
                db.commit()
                continue
            orch = AdsAIOrchestrator(db, user, store, api_key)
            try:
                await orch.sync_meta()
                await orch.analyze_creatives()
            except Exception as exc:
                logger.warning("ai_ads weekly sync/analyze failed store=%s err=%s", store.id, exc)
            product_id = None
            client = orch.shopify_client()
            if client:
                try:
                    products = await client.list_products(limit=1)
                    if products:
                        product_id = str(products[0].get("id"))
                except Exception:
                    product_id = None
            if not product_id:
                row.last_weekly_error = "No Shopify products available for weekly generation"
                row.last_weekly_run_at = datetime.now(UTC)
                db.commit()
                continue
            job = CreativeGenerationJob(
                store_id=store.id,
                user_id=user.id,
                status="QUEUED",
                product_id=product_id,
                request_json=json.dumps(
                    {
                        "product_id": product_id,
                        "image_count": row.image_count or settings.ai_ad_image_count,
                        "video_count": row.video_count or settings.ai_ad_video_count,
                        "styles": json.loads(row.creative_styles_json or "[]"),
                        "audience": row.default_audience,
                        "objective": row.default_objective,
                        "placement": row.default_placement,
                        "aspect_ratio": row.default_aspect_ratio,
                        "brand_style": row.brand_style,
                        "source": "weekly_automation",
                    }
                ),
                progress_message="Queued by weekly automation",
            )
            db.add(job)
            row.last_weekly_run_at = datetime.now(UTC)
            row.last_weekly_error = None
            db.commit()
            enqueue_generation_job(job.id, api_key)
            logger.info("ai_ads weekly job queued store_id=%s job_id=%s", store.id, job.id)
    finally:
        db.close()
