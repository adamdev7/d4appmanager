"""Weekly AI Ads batch: schedule math, one batch per store per week, and a visible run history.

The scheduler and "Run now" both go through ``create_run`` + ``start_run``. Every step records
its own outcome, so a Meta or WhatsApp problem never stops the stills/videos from being made.
Nothing here publishes: creatives land in the approval queue as READY.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.openai_credentials import OPENAI_MODULE_AI_ADS, resolve_openai_api_key
from app.db.models import (
    AIAdsWeeklyRun,
    AIDirectorReport,
    CreativeAsset,
    CreativeGenerationJob,
    ShopifyCatalogProduct,
    Store,
    StoreAIAdsSettings,
    StoreAnalyticsSettings,
    User,
)
from app.db.session import SessionLocal
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.complete_creative import resolve_generation_counts
from app.services.ai_ads.exceptions import PILLOW_INSTALL_HINT, operator_error_message
from app.services.ai_ads.job_progress import append_job_progress
from app.services.ai_ads.job_runner import enqueue_generation_job, is_job_running
from app.services.ai_ads.media_io import imaging_available
from app.services.ai_ads.product_catalog import ShopifyProductCatalog

logger = logging.getLogger(__name__)

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
FALLBACK_TIMEZONE = "America/Toronto"
ACTIVE_STATUSES = ("QUEUED", "RUNNING")
TERMINAL_JOB_STATUSES = ("COMPLETED", "PARTIAL", "FAILED", "CANCELLED")
STEP_KEYS = ("preflight", "meta_sync", "products", "director", "stills", "videos", "whatsapp")
STEP_LABELS = {
    "preflight": "Checks",
    "meta_sync": "Meta sync",
    "products": "Product",
    "director": "Creative Director",
    "stills": "Stills",
    "videos": "Videos",
    "whatsapp": "WhatsApp",
}
# Catch-up runs started this long after the slot are labelled "catch_up" instead of "schedule".
_ON_TIME_WINDOW = timedelta(hours=2)
_META_SYNC_TIMEOUT = 300
_ANALYZE_TIMEOUT = 600
_CATALOG_SYNC_TIMEOUT = 600
_DIRECTOR_TIMEOUT = 600

_active_lock = threading.Lock()
_active_runs: set[str] = set()
_tasks: set[asyncio.Task] = set()


class WeeklyRunBusy(Exception):
    """A weekly batch is already in progress for this store."""


# ------------------------------------------------------------------ schedule math


def _match_weekday(token: str) -> int | None:
    token = token.strip().lower()
    if token.isdigit():
        # Cron style: 0 or 7 = Sunday, 1 = Monday.
        return (int(token) - 1) % 7
    for idx, name in enumerate(WEEKDAYS):
        if token and name.startswith(token[:3]):
            return idx
    return None


def weekday_index(day: str | None) -> int:
    idx = _match_weekday(str(day or ""))
    if idx is None:
        idx = _match_weekday(settings.ai_ad_generation_day or "")
    return 0 if idx is None else idx


def store_timezone_name(store: Store | None) -> str:
    raw = (getattr(store, "timezone", "") or "").strip()
    # Stores are created with "UTC" and only get their real zone after a Shopify sync.
    if not raw or raw.upper() in {"UTC", "ETC/UTC", "GMT"}:
        raw = (settings.ai_ad_weekly_default_timezone or FALLBACK_TIMEZONE).strip()
    try:
        ZoneInfo(raw)
        return raw
    except Exception:
        return FALLBACK_TIMEZONE


def run_hour() -> int:
    try:
        return min(23, max(0, int(settings.ai_ad_weekly_hour)))
    except (TypeError, ValueError):
        return 6


def latest_slot(now: datetime, day: str | None, tz_name: str, hour: int | None = None) -> datetime:
    """Most recent scheduled moment (weekday at ``hour`` local) that is <= now."""
    zone = ZoneInfo(tz_name)
    local = now.astimezone(zone)
    target = weekday_index(day)
    at = run_hour() if hour is None else hour
    back = (local.weekday() - target) % 7
    slot = datetime(local.year, local.month, local.day, at, 0, tzinfo=zone) - timedelta(days=back)
    if slot > local:
        slot -= timedelta(days=7)
    return slot


def next_slot(now: datetime, day: str | None, tz_name: str, hour: int | None = None) -> datetime:
    # Aware + timedelta keeps local wall-clock time, so DST changes stay at the same hour.
    return latest_slot(now, day, tz_name, hour) + timedelta(days=7)


def week_key(slot: datetime) -> str:
    year, week, _ = slot.date().isocalendar()
    return f"{year}-W{week:02d}"


# ------------------------------------------------------------------ steps


def _now() -> datetime:
    return datetime.now(UTC)


def _initial_steps() -> list[dict[str, Any]]:
    return [
        {"key": key, "label": STEP_LABELS[key], "status": "pending", "detail": "", "at": None}
        for key in STEP_KEYS
    ]


def load_steps(run: AIAdsWeeklyRun) -> list[dict[str, Any]]:
    try:
        steps = json.loads(run.steps_json or "[]")
    except json.JSONDecodeError:
        steps = []
    if not isinstance(steps, list) or not steps:
        steps = _initial_steps()
    return steps


def set_step(run: AIAdsWeeklyRun, key: str, status: str, detail: str = "") -> None:
    steps = load_steps(run)
    step = next((s for s in steps if s.get("key") == key), None)
    if step is None:
        # Runs created before a step existed get it inserted in its usual position.
        step = {"key": key, "label": STEP_LABELS.get(key, key), "status": "pending", "detail": "", "at": None}
        steps.append(step)
        order = {k: i for i, k in enumerate(STEP_KEYS)}
        steps.sort(key=lambda s: order.get(s.get("key"), len(order)))
    step["status"] = status
    step["detail"] = (detail or "")[:500]
    step["at"] = _now().isoformat()
    run.steps_json = json.dumps(steps)
    logger.info("ai_ads weekly run=%s store=%s step=%s status=%s %s", run.id, run.store_id, key, status, detail)


def _step_status(run: AIAdsWeeklyRun, key: str) -> str:
    return next((s.get("status", "") for s in load_steps(run) if s.get("key") == key), "")


def _fail(db: Session, run: AIAdsWeeklyRun, step: str, message: str) -> None:
    set_step(run, step, "failed", message)
    for key in STEP_KEYS:
        if _step_status(run, key) == "pending":
            set_step(run, key, "skipped", "Not reached")
    run.status = "FAILED"
    run.error_message = message[:1000]
    run.finished_at = _now()
    _mirror_settings(db, run)
    db.commit()


def _mirror_settings(db: Session, run: AIAdsWeeklyRun) -> None:
    row = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == run.store_id))
    if not row:
        return
    row.last_weekly_run_at = run.started_at or _now()
    row.last_weekly_error = run.error_message if run.status in ("FAILED", "PARTIAL") else None


# ------------------------------------------------------------------ create / start


def active_run(db: Session, store_id: str) -> AIAdsWeeklyRun | None:
    return db.scalar(
        select(AIAdsWeeklyRun)
        .where(AIAdsWeeklyRun.store_id == store_id, AIAdsWeeklyRun.status.in_(ACTIVE_STATUSES))
        .order_by(desc(AIAdsWeeklyRun.created_at))
    )


def create_run(
    db: Session,
    store_id: str,
    *,
    trigger: str,
    slot: datetime | None = None,
) -> AIAdsWeeklyRun | None:
    """Insert a QUEUED run. Returns None when a scheduled run for that week already exists."""
    if active_run(db, store_id):
        raise WeeklyRunBusy("A weekly batch is already running for this store.")
    store = db.get(Store, store_id)
    when = slot or _now().astimezone(ZoneInfo(store_timezone_name(store)))
    key = week_key(when)
    run = AIAdsWeeklyRun(
        store_id=store_id,
        trigger=trigger,
        week_key=key,
        schedule_key=None if trigger == "manual" else key,
        status="QUEUED",
        steps_json=json.dumps(_initial_steps()),
        scheduled_for=slot.astimezone(UTC) if slot else None,
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    db.refresh(run)
    logger.info("ai_ads weekly run queued run=%s store=%s trigger=%s week=%s", run.id, store_id, trigger, key)
    return run


def start_run(run_id: str) -> None:
    """Execute a queued run in the background (same pattern as generation jobs)."""
    with _active_lock:
        if run_id in _active_runs:
            return
        _active_runs.add(run_id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        task = loop.create_task(_execute_guarded(run_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return
    threading.Thread(target=lambda: asyncio.run(_execute_guarded(run_id)), daemon=True).start()


def is_run_active_in_process(run_id: str) -> bool:
    with _active_lock:
        return run_id in _active_runs


async def _execute_guarded(run_id: str) -> None:
    try:
        await execute_run(run_id)
    except Exception as exc:
        logger.exception("ai_ads weekly run crashed run=%s", run_id)
        db = SessionLocal()
        try:
            run = db.get(AIAdsWeeklyRun, run_id)
            if run and run.status in ACTIVE_STATUSES and not run.job_id:
                _fail(db, run, "preflight", operator_error_message(exc))
        except Exception:
            logger.exception("ai_ads weekly run could not record crash run=%s", run_id)
        finally:
            db.close()
    finally:
        with _active_lock:
            _active_runs.discard(run_id)


# ------------------------------------------------------------------ execution


async def execute_run(run_id: str) -> None:
    from app.services.ai_ads.orchestrator import AdsAIOrchestrator

    db = SessionLocal()
    try:
        run = db.get(AIAdsWeeklyRun, run_id)
        if not run or run.status not in ACTIVE_STATUSES:
            return
        run.status = "RUNNING"
        run.started_at = run.started_at or _now()
        set_step(run, "preflight", "running")
        db.commit()

        store = db.get(Store, run.store_id)
        if not store:
            _fail(db, run, "preflight", "Store no longer exists.")
            return
        user = db.get(User, store.owner_id)
        if not user:
            _fail(db, run, "preflight", "Store owner account not found.")
            return
        row = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store.id))
        if not row:
            _fail(db, run, "preflight", "Save AI Ads settings first.")
            return
        api_key = resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS)
        if not api_key:
            _fail(
                db,
                run,
                "preflight",
                "No OpenAI API key. Add one in AI Ads → Settings, then use Run now.",
            )
            return
        if not imaging_available():
            _fail(db, run, "preflight", PILLOW_INSTALL_HINT)
            return
        images, videos = resolve_generation_counts(
            row.image_count,
            row.video_count,
            default_images=settings.ai_ad_image_count,
            default_videos=settings.ai_ad_video_count,
        )
        run.images_requested = images
        run.videos_requested = videos
        if images + videos < 1:
            _fail(db, run, "preflight", "Weekly stills and videos are both set to 0.")
            return
        if not store.access_token_encrypted:
            _fail(db, run, "preflight", "Shopify is not connected for this store.")
            return
        set_step(
            run,
            "preflight",
            "ok",
            f"{images} still{'s' if images != 1 else ''}, {videos} video{'s' if videos != 1 else ''}",
        )
        db.commit()

        orch = AdsAIOrchestrator(db, user, store, api_key)

        # Meta is optional: without it the batch still uses brand style, audience, and products.
        set_step(run, "meta_sync", "running")
        db.commit()
        if not orch.meta_client():
            set_step(
                run,
                "meta_sync",
                "warning",
                "Meta Ads not connected. Using brand style, default audience, and store products.",
            )
        else:
            try:
                result = await asyncio.wait_for(orch.sync_meta(), timeout=_META_SYNC_TIMEOUT)
                detail = f"{int(result.get('ads') or 0)} ads synced"
                try:
                    await asyncio.wait_for(orch.analyze_creatives(), timeout=_ANALYZE_TIMEOUT)
                except Exception as exc:
                    logger.warning("ai_ads weekly analyze failed store=%s err=%s", store.id, exc)
                    db.rollback()
                    set_step(run, "meta_sync", "warning", f"{detail}; analysis skipped: {operator_error_message(exc)}")
                else:
                    set_step(run, "meta_sync", "ok", detail)
            except Exception as exc:
                logger.warning("ai_ads weekly meta sync failed store=%s err=%s", store.id, exc)
                db.rollback()
                set_step(
                    run,
                    "meta_sync",
                    "warning",
                    f"Meta sync failed ({operator_error_message(exc)}). Continuing without fresh Meta data.",
                )
        db.commit()

        set_step(run, "products", "running")
        db.commit()
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        sync_note = ""
        client = orch.shopify_client()
        if client:
            try:
                await asyncio.wait_for(catalog.sync_store(client), timeout=_CATALOG_SYNC_TIMEOUT)
            except Exception as exc:
                logger.warning("ai_ads weekly catalog sync failed store=%s err=%s", store.id, exc)
                db.rollback()
                sync_note = f" (Shopify sync failed: {operator_error_message(exc)}; used cached products)"
        else:
            sync_note = " (Shopify credentials unreadable; used cached products)"
        set_step(run, "products", "warning" if sync_note else "ok", f"Catalog ready{sync_note}")
        db.commit()

        plans = await _director_plans(db, run, store, user, api_key, catalog, images, videos)
        if not plans:
            plan = _fallback_plan(db, run, store, catalog, row, images, videos)
            if isinstance(plan, str):
                _fail(db, run, "products", plan + sync_note)
                return
            plans = [plan]

        jobs: list[CreativeGenerationJob] = []
        for plan in plans:
            job = _create_job(
                db,
                run,
                store,
                user,
                row,
                plan["image_count"],
                plan["video_count"],
                product_id=plan["product_id"],
                styles=plan.get("styles"),
                director_concepts=plan.get("director_concepts"),
            )
            jobs.append(job)
            if plan.get("rows"):
                from app.services.ai_ads.director.service import mark_generated

                mark_generated(db, plan["rows"], job.id)
        images = sum(p["image_count"] for p in plans)
        videos = sum(p["video_count"] for p in plans)
        titles = [p["product_title"] or p["product_id"] for p in plans]
        run.images_requested = images
        run.videos_requested = videos
        run.product_id = plans[0]["product_id"]
        run.product_title = ", ".join(titles)[:512]
        run.job_id = jobs[0].id
        run.job_ids_json = json.dumps([j.id for j in jobs])
        set_step(
            run,
            "products",
            "warning" if sync_note else "ok",
            f"{'; '.join(titles)}{sync_note}",
        )
        set_step(run, "stills", "running" if images else "skipped", "" if images else "Set to 0")
        set_step(run, "videos", "running" if videos else "skipped", "" if videos else "Set to 0")
        db.commit()
        for job in jobs:
            enqueue_generation_job(job.id, api_key)
        logger.info(
            "ai_ads weekly jobs queued run=%s store=%s jobs=%s",
            run.id,
            store.id,
            ",".join(j.id for j in jobs),
        )
    finally:
        db.close()


async def _director_plans(
    db: Session,
    run: AIAdsWeeklyRun,
    store: Store,
    user: User,
    api_key: str,
    catalog: ShopifyProductCatalog,
    images: int,
    videos: int,
) -> list[dict[str, Any]]:
    """Let the Creative Director pick products and concepts. Empty list means use the classic single product."""
    from app.services.ai_ads.director.service import (
        brief_jobs,
        concept_payload,
        create_report,
        get_director_settings,
        run_pipeline,
    )

    director = get_director_settings(db, store.id)
    if not settings.ai_director_enabled or not director.enabled or not director.drive_weekly:
        set_step(run, "director", "skipped", "Director is off for weekly runs; using the classic single-product batch.")
        db.commit()
        return []
    set_step(run, "director", "running", "Planning this week's brief")
    db.commit()
    report = create_report(db, store.id, trigger="weekly", weekly_run_id=run.id)
    run.director_report_id = report.id
    db.commit()
    try:
        await asyncio.wait_for(
            run_pipeline(db, store, user, api_key, report, max_images=images, max_videos=videos),
            timeout=_DIRECTOR_TIMEOUT,
        )
    except Exception as exc:
        logger.warning("ai_ads weekly director failed run=%s store=%s err=%s", run.id, store.id, exc)
        db.rollback()
        report = db.get(AIDirectorReport, report.id)
        if report:
            report.status = "FAILED"
            report.error_message = operator_error_message(exc)[:1000]
            report.finished_at = _now()
        set_step(run, "director", "warning", f"Director failed ({operator_error_message(exc)}). Using one product instead.")
        db.commit()
        return []

    plans: list[dict[str, Any]] = []
    for group in brief_jobs(db, report):
        if not catalog.has_usable_photos(group["product_id"]):
            continue
        plans.append(
            {
                "product_id": group["product_id"],
                "product_title": group["product_title"],
                "image_count": group["image_count"],
                "video_count": group["video_count"],
                "styles": group["styles"],
                "director_concepts": [concept_payload(r) for r in group["rows"]],
                "rows": group["rows"],
            }
        )
    if not plans:
        set_step(run, "director", "warning", "Brief was empty (budget cap or guardrails). Using one product instead.")
        db.commit()
        return []
    concepts = sum(len(p["rows"]) for p in plans)
    set_step(
        run,
        "director",
        "ok",
        f"{concepts} concept{'s' if concepts != 1 else ''} across {len(plans)} product{'s' if len(plans) != 1 else ''}"
        f" · est. ${report.estimated_cost_usd:.2f}",
    )
    db.commit()
    return plans


def _fallback_plan(
    db: Session,
    run: AIAdsWeeklyRun,
    store: Store,
    catalog: ShopifyProductCatalog,
    row: StoreAIAdsSettings,
    images: int,
    videos: int,
) -> dict[str, Any] | str:
    """Classic batch: one rotating product with the saved counts, trimmed to the Director's credit cap."""
    from app.services.ai_ads.director.costs import budget_payload, estimate_generation_usd
    from app.services.ai_ads.director.service import get_director_settings

    product = pick_product(db, store, catalog)
    if not product:
        return "No Shopify product with photos. Add product photos on Generate, then use Run now."
    director = get_director_settings(db, store.id)
    if settings.ai_director_enabled and director.enabled:
        remaining = budget_payload(db, store.id, director.weekly_credit_cap_usd)["remaining_usd"]
        if remaining is not None:
            while videos and estimate_generation_usd(images, videos) > remaining:
                videos -= 1
            while images and estimate_generation_usd(images, videos) > remaining:
                images -= 1
            if images + videos < 1:
                return (
                    f"Weekly credit cap reached (${director.weekly_credit_cap_usd:.2f}). "
                    "Raise it in AI Ads → Director settings, or wait for next week."
                )
    return {
        "product_id": product.shopify_product_id,
        "product_title": product.title or "",
        "image_count": images,
        "video_count": videos,
    }


def pick_product(
    db: Session, store: Store, catalog: ShopifyProductCatalog
) -> ShopifyCatalogProduct | None:
    """Rotate through products with photos, least recently used by weekly runs first."""
    products = db.scalars(
        select(ShopifyCatalogProduct)
        .where(ShopifyCatalogProduct.store_id == store.id)
        .order_by(ShopifyCatalogProduct.created_at)
    ).all()
    usable = [p for p in products if catalog.has_usable_photos(p.shopify_product_id)]
    if not usable:
        return None
    history = db.scalars(
        select(AIAdsWeeklyRun.product_id)
        .where(AIAdsWeeklyRun.store_id == store.id, AIAdsWeeklyRun.product_id.is_not(None))
        .order_by(desc(AIAdsWeeklyRun.created_at))
        .limit(200)
    ).all()
    recency = {}
    for idx, pid in enumerate(history):
        recency.setdefault(pid, idx)
    never = [p for p in usable if p.shopify_product_id not in recency]
    if never:
        return never[0]
    return max(usable, key=lambda p: recency[p.shopify_product_id])


def _create_job(
    db: Session,
    run: AIAdsWeeklyRun,
    store: Store,
    user: User,
    row: StoreAIAdsSettings,
    images: int,
    videos: int,
    *,
    product_id: str | None = None,
    styles: list[str] | None = None,
    director_concepts: list[dict[str, Any]] | None = None,
) -> CreativeGenerationJob:
    product_id = product_id or run.product_id
    placement = row.default_placement or "feed"
    aspect = row.default_aspect_ratio or "4:5"
    if videos and not images:
        placement = row.default_placement or "reels"
        aspect = "9:16"
    if not styles:
        try:
            styles = list(json.loads(row.creative_styles_json or "[]"))
        except json.JSONDecodeError:
            styles = []
    payload = {
        "product_id": product_id,
        "image_count": images,
        "video_count": videos,
        "styles": styles,
        "audience": row.default_audience,
        "objective": row.default_objective,
        "placement": placement,
        "aspect_ratio": aspect,
        "brand_style": row.brand_style,
        "copy_language": "auto",
        "portfolio_mix": {
            "winner_variation": row.winner_pct,
            "combination": row.combination_pct,
            "exploration": row.exploration_pct,
            "experimental": row.experimental_pct,
        },
        "source": "weekly_automation",
        "weekly_run_id": run.id,
        "director_concepts": director_concepts or [],
    }
    job = CreativeGenerationJob(
        store_id=store.id,
        user_id=user.id,
        status="QUEUED",
        product_id=product_id,
        request_json=json.dumps(payload),
        progress_message="Queued by weekly automation",
        progress_step="queued",
        progress_pct=2,
        total_items=images + videos,
    )
    append_job_progress(
        job,
        step="queued",
        title="Queued by weekly automation",
        detail="Weekly batch saved. Creatives go to the approval queue; nothing is published.",
        pct=2,
    )
    db.add(job)
    db.flush()
    return job


# ------------------------------------------------------------------ finalize / reconcile


def _asset_counts(db: Session, job_id: str) -> tuple[int, int, int, int]:
    assets = db.scalars(select(CreativeAsset).where(CreativeAsset.job_id == job_id)).all()
    ok_images = ok_videos = bad_images = bad_videos = 0
    for asset in assets:
        state = (asset.status or "").upper()
        is_video = (asset.type or "").upper() == "VIDEO"
        if state == "FAILED":
            if is_video:
                bad_videos += 1
            else:
                bad_images += 1
        elif state != "GENERATING":
            if is_video:
                ok_videos += 1
            else:
                ok_images += 1
    return ok_images, ok_videos, bad_images, bad_videos


def _count_step(run: AIAdsWeeklyRun, key: str, ok: int, wanted: int, noun: str) -> None:
    if wanted < 1:
        if _step_status(run, key) in ("pending", "running"):
            set_step(run, key, "skipped", "Set to 0")
        return
    status = "ok" if ok >= wanted else ("warning" if ok else "failed")
    set_step(run, key, status, f"{ok} of {wanted} {noun} ready for approval")


def run_job_ids(run: AIAdsWeeklyRun) -> list[str]:
    try:
        ids = [str(i) for i in json.loads(run.job_ids_json or "[]") if i]
    except (json.JSONDecodeError, TypeError):
        ids = []
    if not ids and run.job_id:
        ids = [run.job_id]
    return ids


def run_for_job(db: Session, job_id: str) -> AIAdsWeeklyRun | None:
    run = db.scalar(select(AIAdsWeeklyRun).where(AIAdsWeeklyRun.job_id == job_id))
    if run:
        return run
    candidates = db.scalars(
        select(AIAdsWeeklyRun).where(AIAdsWeeklyRun.job_ids_json.contains(job_id))
    ).all()
    return next((r for r in candidates if job_id in run_job_ids(r)), None)


def run_jobs(db: Session, run: AIAdsWeeklyRun) -> list[CreativeGenerationJob]:
    return [j for j in (db.get(CreativeGenerationJob, i) for i in run_job_ids(run)) if j]


def jobs_all_terminal(jobs: list[CreativeGenerationJob]) -> bool:
    return bool(jobs) and all((j.status or "").upper() in TERMINAL_JOB_STATUSES for j in jobs)


def finalize_run_for_job(
    db: Session,
    job: CreativeGenerationJob,
    *,
    whatsapp: tuple[str, str] | None = None,
) -> AIAdsWeeklyRun | None:
    """Copy finished jobs' outcome onto their weekly run once every job of the run is done."""
    run = run_for_job(db, job.id)
    if not run:
        return None
    jobs = run_jobs(db, run) or [job]
    if not jobs_all_terminal(jobs):
        return run
    ok_images = ok_videos = 0
    for item in jobs:
        imgs, vids, _, _ = _asset_counts(db, item.id)
        ok_images += imgs
        ok_videos += vids
    run.images_generated = ok_images
    run.videos_generated = ok_videos
    _count_step(run, "stills", ok_images, run.images_requested, "stills")
    _count_step(run, "videos", ok_videos, run.videos_requested, "videos")
    if whatsapp:
        wa_status, wa_detail = whatsapp
        set_step(run, "whatsapp", {"ok": "ok", "failed": "warning"}.get(wa_status, "skipped"), wa_detail)
    elif _step_status(run, "whatsapp") in ("pending", "running"):
        set_step(run, "whatsapp", "skipped", "No recap sent for this run.")

    statuses = [(j.status or "").upper() for j in jobs]
    errors = "; ".join(j.error_message for j in jobs if j.error_message)[:1000] or None
    made = ok_images + ok_videos
    wanted = run.images_requested + run.videos_requested
    if "CANCELLED" in statuses:
        run.status = "PARTIAL" if made else "FAILED"
        run.error_message = errors or "Stopped before finishing."
    elif all(s == "FAILED" for s in statuses) or made == 0:
        run.status = "FAILED"
        run.error_message = errors or "No creatives were produced."
    elif made < wanted or any(s in ("PARTIAL", "FAILED") for s in statuses):
        run.status = "PARTIAL"
        run.error_message = errors or f"{made} of {wanted} creatives ready."
    else:
        run.status = "SUCCEEDED"
        run.error_message = None
    finished = [j.finished_at for j in jobs if j.finished_at]
    run.finished_at = max(finished) if finished else _now()
    _mirror_settings(db, run)
    db.commit()
    logger.info(
        "ai_ads weekly run finished run=%s store=%s status=%s images=%s videos=%s",
        run.id,
        run.store_id,
        run.status,
        ok_images,
        ok_videos,
    )
    return run


def reconcile_runs(db: Session) -> None:
    """Close runs whose job ended outside the worker, restart abandoned jobs, retry interrupted runs."""
    runs = db.scalars(select(AIAdsWeeklyRun).where(AIAdsWeeklyRun.status.in_(ACTIVE_STATUSES))).all()
    for run in runs:
        if is_run_active_in_process(run.id):
            continue
        if not run.job_id:
            # Server restarted between preflight and job creation; free the week so it retries.
            run.schedule_key = None
            _fail(db, run, "preflight", "Interrupted by a server restart before generation started.")
            continue
        jobs = run_jobs(db, run)
        if not jobs:
            _fail(db, run, "stills", "Generation job disappeared.")
            continue
        if jobs_all_terminal(jobs):
            finalize_run_for_job(db, jobs[0])
            continue
        api_key: str | None = None
        for job in jobs:
            if (job.status or "").upper() in TERMINAL_JOB_STATUSES or is_job_running(job.id):
                continue
            if api_key is None:
                store = db.get(Store, run.store_id)
                user = db.get(User, store.owner_id) if store else None
                api_key = (resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) if user else None) or ""
            if not api_key:
                job.status = "FAILED"
                job.error_message = "OpenAI API key missing when resuming the weekly job."
                job.finished_at = _now()
                db.commit()
                finalize_run_for_job(db, job)
                continue
            if job.status == "RUNNING":
                job.status = "QUEUED"
                job.error_message = None
                db.commit()
            logger.info("ai_ads weekly job resumed run=%s job=%s", run.id, job.id)
            enqueue_generation_job(job.id, api_key)


# ------------------------------------------------------------------ scheduler entry


def due_slot(db: Session, row: StoreAIAdsSettings, store: Store, now: datetime) -> datetime | None:
    """This week's slot if it has passed and no scheduled run exists for it yet."""
    slot = latest_slot(now, row.generation_day, store_timezone_name(store))
    exists = db.scalar(
        select(AIAdsWeeklyRun.id).where(
            AIAdsWeeklyRun.store_id == store.id,
            AIAdsWeeklyRun.schedule_key == week_key(slot),
        )
    )
    return None if exists else slot


def schedule_due_runs(db: Session, now: datetime | None = None) -> list[str]:
    now = now or _now()
    started: list[str] = []
    rows = db.scalars(
        select(StoreAIAdsSettings).where(StoreAIAdsSettings.weekly_generation_enabled.is_(True))
    ).all()
    for row in rows:
        store = db.get(Store, row.store_id)
        if not store:
            continue
        slot = due_slot(db, row, store, now)
        if not slot:
            continue
        trigger = "schedule" if now - slot.astimezone(UTC) <= _ON_TIME_WINDOW else "catch_up"
        try:
            run = create_run(db, store.id, trigger=trigger, slot=slot)
        except WeeklyRunBusy:
            continue
        if run:
            start_run(run.id)
            started.append(run.id)
    return started


# ------------------------------------------------------------------ API payloads


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def run_card(run: AIAdsWeeklyRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "trigger": run.trigger,
        "week_key": run.week_key,
        "status": run.status,
        "steps": load_steps(run),
        "job_id": run.job_id,
        "job_ids": run_job_ids(run),
        "director_report_id": run.director_report_id,
        "product_id": run.product_id,
        "product_title": run.product_title,
        "images_requested": run.images_requested,
        "videos_requested": run.videos_requested,
        "images_generated": run.images_generated,
        "videos_generated": run.videos_generated,
        "error_message": run.error_message,
        "scheduled_for": _iso(run.scheduled_for),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "created_at": _iso(run.created_at),
    }


def schedule_status(db: Session, user: User, store: Store, row: StoreAIAdsSettings) -> dict[str, Any]:
    from app.notifications.whatsapp import whatsapp_public_payload
    from app.services.ai_ads.weekly_worker import scheduler_heartbeat

    now = _now()
    tz_name = store_timezone_name(store)
    enabled = bool(row.weekly_generation_enabled)
    scheduler_on = bool(settings.ai_ad_weekly_scheduler_enabled)
    next_run: str | None = None
    catching_up = False
    if enabled and scheduler_on:
        slot = due_slot(db, row, store, now)
        if slot:
            catching_up = True
            next_run = now.isoformat()
        else:
            next_run = next_slot(now, row.generation_day, tz_name).astimezone(UTC).isoformat()
    last = db.scalar(
        select(AIAdsWeeklyRun)
        .where(AIAdsWeeklyRun.store_id == store.id)
        .order_by(desc(AIAdsWeeklyRun.created_at))
    )

    problems: list[dict[str, str]] = []
    if not scheduler_on:
        problems.append({"level": "error", "message": "The weekly scheduler is switched off on the server (AI_AD_WEEKLY_SCHEDULER_ENABLED=false)."})
    if not resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS):
        problems.append({"level": "error", "message": "No OpenAI API key. Weekly runs cannot generate until you add one."})
    if not store.access_token_encrypted:
        problems.append({"level": "error", "message": "Shopify is not connected, so there are no products to generate for."})
    analytics = db.scalar(select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == store.id))
    if not (analytics and analytics.meta_access_token_encrypted and analytics.meta_ad_account_id):
        problems.append({"level": "warning", "message": "Meta Ads not connected. Runs still work using brand style, audience, and products."})
    if getattr(row, "whatsapp_weekly_alerts_enabled", False) and not whatsapp_public_payload(db, user).get("whatsapp_configured"):
        problems.append({"level": "warning", "message": "WhatsApp alerts are on, but no WhatsApp number is connected. Runs still happen; no message is sent."})

    heartbeat = scheduler_heartbeat()
    return {
        "enabled": enabled,
        "scheduler_enabled": scheduler_on,
        "scheduler_alive": bool(heartbeat and now - heartbeat < timedelta(minutes=10)),
        "scheduler_last_tick_at": _iso(heartbeat),
        "timezone": tz_name,
        "hour": run_hour(),
        "generation_day": (row.generation_day or "monday").lower(),
        "next_run_at": next_run,
        "catching_up": catching_up,
        "last_run_at": _iso(last.started_at or last.created_at) if last else None,
        "last_run_status": last.status if last else None,
        "last_error": row.last_weekly_error,
        "problems": problems,
    }
