"""Credit estimates (USD). Rates come from env so they can follow OpenAI pricing without a deploy."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import CreativeGenerationJob


def estimate_generation_usd(images: int, videos: int) -> float:
    images = max(0, int(images or 0))
    videos = max(0, int(videos or 0))
    if images + videos == 0:
        return 0.0
    total = (
        images * settings.ai_ad_cost_image_usd
        + videos * settings.ai_ad_cost_video_usd
        + settings.ai_ad_cost_plan_usd
    )
    return round(total, 2)


def director_run_usd() -> float:
    return round(settings.ai_ad_cost_director_run_usd, 2)


def week_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return start


def spent_this_week_usd(db: Session, store_id: str, now: datetime | None = None) -> float:
    """Estimated spend of generation jobs created since Monday 00:00 UTC (failed jobs still spend)."""
    start = week_start(now)
    jobs = db.scalars(
        select(CreativeGenerationJob).where(
            CreativeGenerationJob.store_id == store_id,
            CreativeGenerationJob.created_at >= start,
            CreativeGenerationJob.status != "CANCELLED",
        )
    ).all()
    total = 0.0
    for job in jobs:
        try:
            req = json.loads(job.request_json or "{}")
        except json.JSONDecodeError:
            req = {}
        total += estimate_generation_usd(req.get("image_count") or 0, req.get("video_count") or 0)
    return round(total, 2)


def budget_payload(db: Session, store_id: str, cap_usd: float | None) -> dict:
    spent = spent_this_week_usd(db, store_id)
    cap = float(cap_usd or 0)
    return {
        "spent_usd": spent,
        "cap_usd": cap,
        "remaining_usd": round(max(0.0, cap - spent), 2) if cap > 0 else None,
        "rates": {
            "image_usd": settings.ai_ad_cost_image_usd,
            "video_usd": settings.ai_ad_cost_video_usd,
            "plan_usd": settings.ai_ad_cost_plan_usd,
            "director_run_usd": settings.ai_ad_cost_director_run_usd,
        },
    }
