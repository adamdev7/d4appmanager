"""Creative Director: runs, idea board, suggestion decisions, challenges, outcomes, playbook.

Everything the Director produces is a suggestion. Generating goes through the normal
generation job (approval queue, nothing published); the owner can always override.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.openai_credentials import OPENAI_MODULE_AI_ADS, resolve_openai_api_key
from app.db.models import (
    AIAdsPlaybookEntry,
    AIDirectorReport,
    AIDirectorSettings,
    AIDirectorSuggestion,
    CreativeAsset,
    CreativeGenerationJob,
    CreativePerformanceSnapshot,
    ShopifyCatalogProduct,
    Store,
    StoreAIAdsSettings,
    User,
)
from app.db.session import SessionLocal
from app.services.ai_ads.ad_types import AD_TYPES, clamp_media, get_ad_type, registry_payload
from app.services.ai_ads.director.context import build_context, director_lists, prompt_view
from app.services.ai_ads.director.costs import budget_payload, director_run_usd, estimate_generation_usd
from app.services.ai_ads.director.engine import (
    DirectorEngine,
    apply_reviews,
    build_alerts,
    build_brief,
    request_checks,
    screen_candidates,
    select_board,
)
from app.services.ai_ads.director.memory import build_memory
from app.services.ai_ads.exceptions import operator_error_message
from app.services.ai_ads.openai_client import AdsOpenAIClient

logger = logging.getLogger(__name__)

AGGRESSIVENESS_LEVELS = ("safe", "balanced", "bold")
IDEA_COUNT = 16
ACTIVE = ("QUEUED", "RUNNING")
CHALLENGE_TIMEOUT = 25
CONTEXT_FRESH_HOURS = 24
DEFAULT_MAX_IMAGES = 6
DEFAULT_MAX_VIDEOS = 2

_tasks: set[asyncio.Task] = set()
_active_lock = threading.Lock()
_active_reports: set[str] = set()


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat()


def _loads(raw: str | None, default: Any) -> Any:
    try:
        value = json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


# ------------------------------------------------------------------ settings


def get_director_settings(db: Session, store_id: str) -> AIDirectorSettings:
    row = db.scalar(select(AIDirectorSettings).where(AIDirectorSettings.store_id == store_id))
    if row:
        return row
    row = AIDirectorSettings(store_id=store_id, never_do_json="[]", offers_json="[]")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def settings_card(row: AIDirectorSettings) -> dict[str, Any]:
    lists = director_lists(row)
    return {
        "enabled": bool(row.enabled),
        "drive_weekly": bool(row.drive_weekly),
        "challenge_requests": bool(row.challenge_requests),
        "aggressiveness": row.aggressiveness or "balanced",
        "weekly_credit_cap_usd": row.weekly_credit_cap_usd or 0,
        "priority_product_ids": lists["priority"],
        "excluded_product_ids": lists["excluded"],
        "offers": lists["offers"],
        "never_do": lists["never_do"],
        "margin_floor_pct": row.margin_floor_pct,
        "low_stock_threshold": row.low_stock_threshold,
        "copy_language": row.copy_language or "auto",
        "last_run_at": _iso(row.last_run_at),
        "server_enabled": bool(settings.ai_director_enabled),
    }


def update_director_settings(db: Session, row: AIDirectorSettings, body: dict[str, Any]) -> AIDirectorSettings:
    for key in ("enabled", "drive_weekly", "challenge_requests"):
        if body.get(key) is not None:
            setattr(row, key, bool(body[key]))
    if body.get("aggressiveness") in AGGRESSIVENESS_LEVELS:
        row.aggressiveness = body["aggressiveness"]
    if body.get("weekly_credit_cap_usd") is not None:
        row.weekly_credit_cap_usd = max(0.0, float(body["weekly_credit_cap_usd"]))
    if "margin_floor_pct" in body:
        value = body["margin_floor_pct"]
        row.margin_floor_pct = None if value in (None, "") else max(0.0, min(95.0, float(value)))
    if body.get("low_stock_threshold") is not None:
        row.low_stock_threshold = max(0, int(body["low_stock_threshold"]))
    if body.get("copy_language") in ("auto", "en", "fr"):
        row.copy_language = body["copy_language"]
    for key, attr in (("priority_product_ids", "priority_product_ids_json"), ("excluded_product_ids", "excluded_product_ids_json")):
        if body.get(key) is not None:
            setattr(row, attr, json.dumps([str(x) for x in body[key] if str(x).strip()][:100]))
    if body.get("never_do") is not None:
        row.never_do_json = json.dumps([str(x).strip()[:200] for x in body["never_do"] if str(x).strip()][:40])
    if body.get("offers") is not None:
        offers = []
        for i, offer in enumerate(body["offers"][:20]):
            label = str((offer or {}).get("label") or "").strip()[:120]
            if not label:
                continue
            offers.append(
                {
                    "id": str(offer.get("id") or f"offer_{i + 1}")[:40],
                    "label": label,
                    "details": str(offer.get("details") or "").strip()[:300],
                }
            )
        row.offers_json = json.dumps(offers)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------------ cards


def suggestion_card(s: AIDirectorSuggestion) -> dict[str, Any]:
    ad_type = get_ad_type(s.ad_type)
    return {
        "id": s.id,
        "report_id": s.report_id,
        "kind": s.kind,
        "status": s.status,
        "in_brief": bool(s.in_brief),
        "is_experiment": bool(s.is_experiment),
        "concept_name": s.concept_name,
        "ad_type": s.ad_type,
        "ad_type_label": ad_type.label,
        "product_id": s.product_id,
        "product_title": s.product_title,
        "image_count": s.image_count,
        "video_count": s.video_count,
        "hook": s.hook,
        "hook_type": s.hook_type,
        "angle": s.angle,
        "emotion": s.emotion,
        "funnel": s.funnel,
        "audience": s.audience,
        "occasion": s.occasion,
        "why": s.why,
        "rationale": s.rationale,
        "hypothesis": s.hypothesis,
        "test_variable": s.test_variable,
        "test_design": s.test_design,
        "test_budget": s.test_budget,
        "ad_name": s.ad_name,
        "script": _loads(s.script_json, {}),
        "scores": _loads(s.scores_json, {}),
        "flags": _loads(s.flags_json, []),
        "estimated_cost_usd": s.estimated_cost_usd,
        "source_creative_id": s.source_creative_id,
        "dismiss_reason": s.dismiss_reason,
        "job_id": s.job_id,
        "outcome": _loads(s.outcome_json, {}),
        "decided_at": _iso(s.decided_at),
        "created_at": _iso(s.created_at),
    }


def report_card(r: AIDirectorReport | None) -> dict[str, Any] | None:
    if not r:
        return None
    return {
        "id": r.id,
        "trigger": r.trigger,
        "week_key": r.week_key,
        "status": r.status,
        "progress": r.progress,
        "brief": _loads(r.brief_json, {}),
        "alerts": _loads(r.alerts_json, []),
        "audience_ideas": _loads(r.audience_ideas_json, []),
        "offer_ideas": _loads(r.offer_ideas_json, []),
        "data_gaps": _loads(r.context_json, {}).get("data_gaps", []),
        "estimated_cost_usd": r.estimated_cost_usd,
        "model_used": r.model_used,
        "weekly_run_id": r.weekly_run_id,
        "error_message": r.error_message,
        "started_at": _iso(r.started_at),
        "finished_at": _iso(r.finished_at),
        "created_at": _iso(r.created_at),
    }


def _week_key(now: datetime | None = None) -> str:
    year, week, _ = (now or _now()).date().isocalendar()
    return f"{year}-W{week:02d}"


def _test_budget(is_experiment: bool, currency: str) -> str:
    return f"{currency} 10–20/day for 3–4 days (suggested test)" if is_experiment else f"{currency} 20–40/day for 5–7 days (suggested)"


def _product_texts(db: Session, store_id: str, context: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in db.scalars(select(ShopifyCatalogProduct).where(ShopifyCatalogProduct.store_id == store_id)).all():
        out[row.shopify_product_id] = f"{row.title} {row.description or ''} {row.appearance_lock or ''}"
    for p in context.get("products") or []:
        out[p["id"]] = f"{out.get(p['id'], '')} {p.get('title', '')} {p.get('tags', '')} {p.get('product_type', '')}"
    return out


def _latest_context(db: Session, store_id: str) -> tuple[dict[str, Any] | None, datetime | None]:
    report = db.scalar(
        select(AIDirectorReport)
        .where(AIDirectorReport.store_id == store_id, AIDirectorReport.status == "COMPLETED")
        .order_by(desc(AIDirectorReport.created_at))
    )
    if not report:
        return None, None
    return _loads(report.context_json, {}), report.finished_at


# ------------------------------------------------------------------ pipeline


def _progress(db: Session, report: AIDirectorReport, text: str) -> None:
    report.progress = text[:255]
    db.commit()
    logger.info("ai_ads director report=%s store=%s %s", report.id, report.store_id, text)


async def run_pipeline(
    db: Session,
    store: Store,
    user: User,
    api_key: str,
    report: AIDirectorReport,
    *,
    max_images: int | None = None,
    max_videos: int | None = None,
) -> AIDirectorReport:
    from app.core.openai_models import server_text_fallback, use_text_model

    ads_row = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store.id))
    with use_text_model(ads_row.text_model if ads_row else None, fallback=server_text_fallback()):
        return await _run_pipeline_body(
            db,
            store,
            user,
            api_key,
            report,
            max_images=max_images,
            max_videos=max_videos,
        )


async def _run_pipeline_body(
    db: Session,
    store: Store,
    user: User,
    api_key: str,
    report: AIDirectorReport,
    *,
    max_images: int | None = None,
    max_videos: int | None = None,
) -> AIDirectorReport:
    """Context -> ideation -> guardrails/novelty -> critique -> board, brief, alerts. Commits as it goes."""
    report.status = "RUNNING"
    report.started_at = report.started_at or _now()
    director = get_director_settings(db, store.id)
    ads = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store.id))
    aggressiveness = director.aggressiveness or "balanced"
    _progress(db, report, "Reading Shopify sales, inventory, Meta results, and the playbook")

    refresh_outcomes(db, store.id)
    previous, _ = _latest_context(db, store.id)
    context = await build_context(db, store, ads_settings=ads, director=director, include_orders=True, previous=previous)
    view = prompt_view(context)
    memory = build_memory(db, store.id)
    product_texts = _product_texts(db, store.id, context)

    engine = DirectorEngine(
        AdsOpenAIClient(api_key, store_id=store.id),
        model=settings.resolved_ai_strategy_model,
        critique_model=settings.resolved_ai_analysis_model,
    )
    report.model_used = settings.resolved_ai_strategy_model[:64]
    _progress(db, report, f"Ideating {IDEA_COUNT} concepts ({aggressiveness})")
    ideas = await engine.ideate(view, count=IDEA_COUNT, aggressiveness=aggressiveness)
    candidates, rejected = screen_candidates(ideas.concepts, context, memory, product_texts)
    if not candidates:
        raise RuntimeError(
            "Every idea was blocked by guardrails or was too close to past ads: "
            + "; ".join(r["reason"] for r in rejected[:4])
        )

    budget = budget_payload(db, store.id, director.weekly_credit_cap_usd)
    cap_images = max_images if max_images is not None else DEFAULT_MAX_IMAGES
    cap_videos = max_videos if max_videos is not None else DEFAULT_MAX_VIDEOS
    budget.update({"max_images": cap_images, "max_videos": cap_videos})
    _progress(db, report, f"Critiquing {len(candidates)} concepts ({len(rejected)} filtered out)")
    critique = None
    try:
        critique = await engine.critique(view, candidates, budget)
    except Exception as exc:
        logger.warning("ai_ads director critique failed store=%s err=%s", store.id, exc)
    scored = apply_reviews(candidates, critique, aggressiveness)
    board = select_board(scored, aggressiveness)
    brief = build_brief(
        board,
        critique,
        remaining_usd=budget["remaining_usd"],
        max_images=cap_images,
        max_videos=cap_videos,
    )
    if critique is None:
        brief["summary"] = brief["summary"] or "The critique step was unavailable; ideas are ranked by guardrails and novelty only."

    # Unsaved ideas from older boards give way to this week's board.
    for old in db.scalars(
        select(AIDirectorSuggestion).where(
            AIDirectorSuggestion.store_id == store.id, AIDirectorSuggestion.status == "NEW"
        )
    ).all():
        old.status = "EXPIRED"

    products = {p["id"]: p for p in context.get("products") or []}
    brief_counts = {item["index"]: item for item in brief["items"]}
    week = _week_key()
    currency = store.currency or "CAD"
    for concept in board:
        product = products.get(str(concept.get("product_id") or "")) or {}
        in_brief = concept["index"] in brief_counts
        images, videos = concept["image_count"], concept["video_count"]
        if in_brief:
            images, videos = brief_counts[concept["index"]]["image_count"], brief_counts[concept["index"]]["video_count"]
        ad_type = get_ad_type(concept["ad_type"])
        row = AIDirectorSuggestion(
            store_id=store.id,
            report_id=report.id,
            kind="wildcard" if concept.get("is_wildcard") else concept.get("kind") or "new",
            status="NEW",
            in_brief=in_brief,
            is_experiment=bool(concept.get("is_wildcard")),
            concept_name=str(concept.get("concept_name") or "")[:255],
            ad_type=ad_type.id,
            product_id=str(concept.get("product_id") or "") or None,
            product_title=str(product.get("title") or "")[:512],
            image_count=images,
            video_count=videos,
            hook=str(concept.get("hook") or ""),
            hook_type=str(concept.get("hook_type") or "")[:32],
            angle=str(concept.get("angle") or ""),
            emotion=str(concept.get("emotion") or "")[:64],
            funnel=concept.get("funnel") or "prospecting",
            audience=str(concept.get("audience") or ""),
            occasion=str(concept.get("occasion") or "")[:64],
            why=str(concept.get("why") or ""),
            rationale=str((concept.get("review") or {}).get("verdict") or ""),
            hypothesis=str(concept.get("hypothesis") or ""),
            test_variable=str(concept.get("test_variable") or "")[:64],
            test_design=str(concept.get("test_design") or ""),
            test_budget=_test_budget(bool(concept.get("is_wildcard")), currency),
            ad_name=f"LUX | {week} | {(product.get('title') or '')[:24]} | {ad_type.id} | {concept.get('test_variable') or 'angle'}-A",
            script_json=json.dumps(concept.get("script") or {}),
            scores_json=json.dumps({**(concept.get("review") or {}), "score": concept.get("score"), "measured_novelty": concept.get("novelty")}),
            flags_json=json.dumps(concept.get("flags") or []),
            estimated_cost_usd=estimate_generation_usd(images, videos),
            source_creative_id=str(concept.get("source_creative_id") or "") or None,
        )
        db.add(row)
        db.flush()
        if in_brief:
            brief_counts[concept["index"]]["suggestion_id"] = row.id
    brief["items"] = [i for i in brief["items"] if i.get("suggestion_id")]
    brief["filtered_out"] = rejected[:12]

    confirmed_ids = {o["id"] for o in context.get("confirmed_offers") or []}
    offer_ideas = []
    for idea in ideas.offer_ideas[:4]:
        data = idea.model_dump()
        data["requires_confirmation"] = data.get("offer_id") not in confirmed_ids
        offer_ideas.append(data)

    _apply_playbook_updates(db, store.id, critique)
    report.brief_json = json.dumps(brief)
    report.alerts_json = json.dumps(build_alerts(context))
    report.audience_ideas_json = json.dumps([a.model_dump() for a in ideas.audience_ideas[:5]])
    report.offer_ideas_json = json.dumps(offer_ideas)
    context.pop("memory", None)
    report.context_json = json.dumps(context, default=str)[:400000]
    report.week_key = week
    report.estimated_cost_usd = round(brief["estimated_cost_usd"] + director_run_usd(), 2)
    report.status = "COMPLETED"
    report.progress = f"{len(board)} ideas, {len(brief['items'])} in this week's brief"
    report.finished_at = _now()
    director.last_run_at = report.finished_at
    db.commit()
    logger.info(
        "ai_ads director done report=%s store=%s board=%s brief=%s est=$%s",
        report.id,
        store.id,
        len(board),
        len(brief["items"]),
        report.estimated_cost_usd,
    )
    return report


def _apply_playbook_updates(db: Session, store_id: str, critique: Any) -> None:
    if not critique:
        return
    for update in critique.playbook_updates or []:
        entry = db.get(AIAdsPlaybookEntry, update.hypothesis_id)
        if not entry or entry.store_id != store_id or entry.kind != "hypothesis":
            continue
        if update.status not in ("supported", "refuted", "inconclusive") or not update.evidence.strip():
            continue
        entry.status = update.status
        evidence = _loads(entry.evidence_json, [])
        evidence.append({"at": _now().isoformat(), "source": "director_review", "note": update.evidence[:400]})
        entry.evidence_json = json.dumps(evidence[-10:])


def create_report(db: Session, store_id: str, *, trigger: str, weekly_run_id: str | None = None) -> AIDirectorReport:
    report = AIDirectorReport(store_id=store_id, trigger=trigger, status="QUEUED", weekly_run_id=weekly_run_id, week_key=_week_key())
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def start_report(report_id: str) -> None:
    with _active_lock:
        if report_id in _active_reports:
            return
        _active_reports.add(report_id)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        task = loop.create_task(_execute_report(report_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)
        return
    threading.Thread(target=lambda: asyncio.run(_execute_report(report_id)), daemon=True).start()


async def _execute_report(report_id: str) -> None:
    db = SessionLocal()
    try:
        report = db.get(AIDirectorReport, report_id)
        if not report:
            return
        store = db.get(Store, report.store_id)
        user = db.get(User, store.owner_id) if store else None
        api_key = resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) if user else None
        if not store or not user or not api_key:
            report.status = "FAILED"
            report.error_message = "Add your OpenAI API key under Settings → API keys, then run the Director again."
            report.finished_at = _now()
            db.commit()
            return
        try:
            await run_pipeline(db, store, user, api_key, report)
        except Exception as exc:
            logger.exception("ai_ads director run failed report=%s", report_id)
            db.rollback()
            report = db.get(AIDirectorReport, report_id)
            if report:
                report.status = "FAILED"
                report.error_message = operator_error_message(exc)[:1000]
                report.finished_at = _now()
                db.commit()
    finally:
        db.close()
        with _active_lock:
            _active_reports.discard(report_id)


def reconcile_reports(db: Session) -> None:
    """Reports left RUNNING by a restart are marked failed so the UI does not spin forever."""
    stale = _now() - timedelta(minutes=20)
    for report in db.scalars(select(AIDirectorReport).where(AIDirectorReport.status.in_(ACTIVE))).all():
        with _active_lock:
            if report.id in _active_reports:
                continue
        started = report.started_at or report.created_at
        if started and started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        if report.weekly_run_id and started and started > stale:
            continue
        report.status = "FAILED"
        report.error_message = "Interrupted by a server restart. Run the Director again."
        report.finished_at = _now()
    db.commit()


# ------------------------------------------------------------------ outcomes & feedback


def _outcome(db: Session, suggestion: AIDirectorSuggestion) -> dict[str, Any]:
    job = db.get(CreativeGenerationJob, suggestion.job_id) if suggestion.job_id else None
    assets = db.scalars(
        select(CreativeAsset).where(CreativeAsset.job_id == suggestion.job_id)
    ).all() if suggestion.job_id else []
    counts: dict[str, int] = {}
    for asset in assets:
        state = (asset.status or "").upper()
        counts[state] = counts.get(state, 0) + 1
    perf = None
    ids = [a.id for a in assets]
    if ids:
        snaps = db.scalars(
            select(CreativePerformanceSnapshot)
            .where(CreativePerformanceSnapshot.generated_asset_id.in_(ids))
            .order_by(desc(CreativePerformanceSnapshot.created_at))
        ).all()
        if snaps:
            spend = sum(s.spend or 0 for s in snaps[: len(ids)])
            best = max(snaps[: len(ids)], key=lambda s: (s.roas or 0, s.ctr or 0))
            perf = {"ctr": best.ctr, "roas": best.roas, "spend": round(spend, 2), "frequency": best.frequency}
    approved = counts.get("APPROVED", 0) + counts.get("PUBLISHED", 0) + counts.get("PAUSED", 0)
    parts = [f"{len(assets)} made"] if assets else [f"job {(job.status if job else 'missing').lower()}"]
    if approved:
        parts.append(f"{approved} approved")
    if counts.get("REJECTED"):
        parts.append(f"{counts['REJECTED']} rejected")
    if counts.get("PUBLISHED"):
        parts.append(f"{counts['PUBLISHED']} live")
    if perf and perf.get("ctr") is not None:
        parts.append(f"CTR {perf['ctr']:.2f}%")
    if perf and perf.get("roas") is not None:
        parts.append(f"ROAS {perf['roas']:.2f}")
    return {
        "job_status": job.status if job else None,
        "made": len(assets),
        "approved": approved,
        "rejected": counts.get("REJECTED", 0),
        "published": counts.get("PUBLISHED", 0),
        "performance": perf,
        "summary": " · ".join(parts),
    }


def refresh_outcomes(db: Session, store_id: str) -> None:
    """Update outcomes of accepted suggestions and attach them as evidence to their hypotheses."""
    rows = db.scalars(
        select(AIDirectorSuggestion)
        .where(AIDirectorSuggestion.store_id == store_id, AIDirectorSuggestion.status == "GENERATED")
        .order_by(desc(AIDirectorSuggestion.decided_at))
        .limit(60)
    ).all()
    for row in rows:
        outcome = _outcome(db, row)
        previous = _loads(row.outcome_json, {})
        if outcome == previous:
            continue
        row.outcome_json = json.dumps(outcome)
        if outcome.get("performance") and outcome.get("performance") != previous.get("performance"):
            for entry in db.scalars(
                select(AIAdsPlaybookEntry).where(AIAdsPlaybookEntry.suggestion_id == row.id)
            ).all():
                evidence = _loads(entry.evidence_json, [])
                evidence.append({"at": _now().isoformat(), "source": "meta", "note": outcome["summary"]})
                entry.evidence_json = json.dumps(evidence[-10:])
    db.commit()


def _add_playbook(db: Session, store_id: str, *, kind: str, statement: str, suggestion_id: str | None, source: str) -> None:
    statement = statement.strip()
    if not statement:
        return
    db.add(
        AIAdsPlaybookEntry(
            store_id=store_id,
            kind=kind,
            statement=statement[:1000],
            status="open" if kind == "hypothesis" else "active",
            source=source,
            suggestion_id=suggestion_id,
        )
    )


# ------------------------------------------------------------------ service


class DirectorService:
    def _store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def _suggestion(self, db: Session, store_id: str, suggestion_id: str) -> AIDirectorSuggestion:
        row = db.get(AIDirectorSuggestion, suggestion_id)
        if not row or row.store_id != store_id:
            raise HTTPException(status_code=404, detail="Suggestion not found")
        return row

    def overview(self, db: Session, user: User, store_id: str) -> dict[str, Any]:
        self._store(db, user, store_id)
        director = get_director_settings(db, store_id)
        refresh_outcomes(db, store_id)
        latest = db.scalar(
            select(AIDirectorReport).where(AIDirectorReport.store_id == store_id).order_by(desc(AIDirectorReport.created_at))
        )
        completed = latest if latest and latest.status == "COMPLETED" else db.scalar(
            select(AIDirectorReport)
            .where(AIDirectorReport.store_id == store_id, AIDirectorReport.status == "COMPLETED")
            .order_by(desc(AIDirectorReport.created_at))
        )
        board = db.scalars(
            select(AIDirectorSuggestion)
            .where(AIDirectorSuggestion.store_id == store_id, AIDirectorSuggestion.status.in_(("NEW", "SAVED")))
            .order_by(desc(AIDirectorSuggestion.created_at))
            .limit(40)
        ).all()
        log = db.scalars(
            select(AIDirectorSuggestion)
            .where(AIDirectorSuggestion.store_id == store_id, AIDirectorSuggestion.status.in_(("GENERATED", "DISMISSED")))
            .order_by(desc(AIDirectorSuggestion.decided_at))
            .limit(30)
        ).all()
        playbook = db.scalars(
            select(AIAdsPlaybookEntry)
            .where(AIAdsPlaybookEntry.store_id == store_id)
            .order_by(desc(AIAdsPlaybookEntry.updated_at))
            .limit(25)
        ).all()
        return {
            "settings": settings_card(director),
            "budget": budget_payload(db, store_id, director.weekly_credit_cap_usd),
            "latest_run": report_card(latest),
            "report": report_card(completed),
            "board": [suggestion_card(s) for s in board],
            "log": [suggestion_card(s) for s in log],
            "playbook": [
                {
                    "id": e.id,
                    "kind": e.kind,
                    "statement": e.statement,
                    "status": e.status,
                    "source": e.source,
                    "evidence": _loads(e.evidence_json, []),
                    "updated_at": _iso(e.updated_at),
                }
                for e in playbook
            ],
            "ad_types": registry_payload(),
        }

    def run_now(self, db: Session, user: User, store_id: str) -> dict[str, Any]:
        self._store(db, user, store_id)
        if not settings.ai_director_enabled:
            raise HTTPException(status_code=400, detail="The Creative Director is switched off on the server (AI_DIRECTOR_ENABLED=false).")
        if not resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS):
            raise HTTPException(status_code=400, detail="Add your OpenAI API key in AI Ads → Settings first")
        busy = db.scalar(
            select(AIDirectorReport).where(AIDirectorReport.store_id == store_id, AIDirectorReport.status.in_(ACTIVE))
        )
        if busy:
            raise HTTPException(status_code=409, detail="The Director is already working on this store.")
        report = create_report(db, store_id, trigger="manual")
        start_report(report.id)
        return report_card(report)  # type: ignore[return-value]

    def update_settings(self, db: Session, user: User, store_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._store(db, user, store_id)
        return settings_card(update_director_settings(db, get_director_settings(db, store_id), body))

    def edit_suggestion(self, db: Session, user: User, store_id: str, suggestion_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._store(db, user, store_id)
        row = self._suggestion(db, store_id, suggestion_id)
        if row.status not in ("NEW", "SAVED"):
            raise HTTPException(status_code=400, detail="Only open suggestions can be edited.")
        for key in ("concept_name", "hook", "angle", "audience", "hypothesis", "test_design"):
            if body.get(key) is not None:
                setattr(row, key, str(body[key])[:2000])
        if body.get("ad_type") and str(body["ad_type"]).upper() in AD_TYPES:
            row.ad_type = str(body["ad_type"]).upper()
        if body.get("product_id"):
            product = db.scalar(
                select(ShopifyCatalogProduct).where(
                    ShopifyCatalogProduct.store_id == store_id,
                    ShopifyCatalogProduct.shopify_product_id == str(body["product_id"]),
                )
            )
            if not product:
                raise HTTPException(status_code=400, detail="Product not found in the catalog.")
            row.product_id = product.shopify_product_id
            row.product_title = product.title
        if body.get("image_count") is not None or body.get("video_count") is not None:
            row.image_count, row.video_count = clamp_media(
                get_ad_type(row.ad_type),
                body.get("image_count", row.image_count),
                body.get("video_count", row.video_count),
            )
        row.estimated_cost_usd = estimate_generation_usd(row.image_count, row.video_count)
        db.commit()
        return suggestion_card(row)

    def dismiss(self, db: Session, user: User, store_id: str, suggestion_id: str, reason: str) -> dict[str, Any]:
        self._store(db, user, store_id)
        row = self._suggestion(db, store_id, suggestion_id)
        row.status = "DISMISSED"
        row.dismiss_reason = (reason or "").strip()[:500]
        row.decided_at = _now()
        _add_playbook(
            db,
            store_id,
            kind="preference",
            statement=(
                f"Owner dismissed {get_ad_type(row.ad_type).label} idea “{row.concept_name}” (angle: {row.angle[:80]})"
                + (f". Reason: {row.dismiss_reason}" if row.dismiss_reason else ". No reason given.")
            ),
            suggestion_id=row.id,
            source="feedback",
        )
        db.commit()
        return suggestion_card(row)

    def save_for_later(self, db: Session, user: User, store_id: str, suggestion_id: str) -> dict[str, Any]:
        self._store(db, user, store_id)
        row = self._suggestion(db, store_id, suggestion_id)
        if row.status in ("NEW", "EXPIRED", "DISMISSED"):
            row.status = "SAVED"
            db.commit()
        return suggestion_card(row)

    def generate(
        self, db: Session, user: User, store_id: str, suggestion_id: str, *, override_cap: bool = False
    ) -> dict[str, Any]:
        from app.services.ai_ads.service import AIAdsService

        store = self._store(db, user, store_id)
        row = self._suggestion(db, store_id, suggestion_id)
        if row.status == "GENERATED" and row.job_id:
            raise HTTPException(status_code=400, detail="This suggestion was already generated.")
        director = get_director_settings(db, store_id)
        previous, _ = _latest_context(db, store_id)
        product = next((p for p in (previous or {}).get("products") or [] if p.get("id") == row.product_id), None)
        if product and product.get("stock") == "out":
            raise HTTPException(status_code=400, detail=f"{row.product_title} is out of stock. Pick another product with Edit.")
        cost = estimate_generation_usd(row.image_count, row.video_count)
        budget = budget_payload(db, store_id, director.weekly_credit_cap_usd)
        if budget["remaining_usd"] is not None and cost > budget["remaining_usd"] and not override_cap:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"This costs about ${cost:.2f} and only ${budget['remaining_usd']:.2f} of your "
                    f"${budget['cap_usd']:.2f} weekly cap is left. Generate anyway to override."
                ),
            )
        ads = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store_id))
        body = generation_body(row, ads, director)
        card = AIAdsService().create_generation_job(db, user, store.id, body)
        row.status = "GENERATED"
        row.job_id = card.get("job_id") or card.get("id")
        row.decided_at = _now()
        _add_playbook(db, store_id, kind="hypothesis", statement=row.hypothesis, suggestion_id=row.id, source="director")
        db.commit()
        return {"suggestion": suggestion_card(row), "job": card}

    async def challenge(self, db: Session, user: User, store_id: str, request: dict[str, Any]) -> dict[str, Any]:
        store = self._store(db, user, store_id)
        director = get_director_settings(db, store_id)
        if not director.enabled or not director.challenge_requests or not settings.ai_director_enabled:
            return {"verdict": "go", "notes": [], "alternative": None, "skipped": True}
        previous, finished = _latest_context(db, store_id)
        if finished and finished.tzinfo is None:
            finished = finished.replace(tzinfo=UTC)
        fresh = bool(previous and finished and _now() - finished < timedelta(hours=CONTEXT_FRESH_HOURS))
        if fresh:
            context = previous or {}
        else:
            ads = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store_id))
            try:
                context = await asyncio.wait_for(
                    build_context(db, store, ads_settings=ads, director=director, include_orders=False, previous=previous),
                    timeout=CHALLENGE_TIMEOUT,
                )
            except Exception as exc:
                logger.warning("ai_ads director challenge context failed store=%s err=%s", store_id, exc)
                context = previous or {}
        memory = build_memory(db, store_id)
        context["memory"] = [
            {k: m.get(k) for k in ("source", "hook", "angle", "performance")} for m in memory[:30]
        ]
        checks = request_checks(request, context, memory)
        verdict = "reconsider" if checks else "go"
        notes = list(checks)
        alternative = None
        api_key = resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS)
        if api_key:
            engine = DirectorEngine(
                AdsOpenAIClient(api_key, store_id=store_id),
                model=settings.resolved_ai_strategy_model,
                critique_model=settings.resolved_ai_analysis_model,
            )
            try:
                result = await asyncio.wait_for(engine.challenge(prompt_view(context), request, checks), timeout=CHALLENGE_TIMEOUT)
                if result.verdict == "reconsider":
                    verdict = "reconsider"
                for note in result.notes[:4]:
                    if note and note not in notes:
                        notes.append(note)
                if result.alternative and (result.alternative.hook or result.alternative.angle or result.alternative.ad_type):
                    alt = result.alternative.model_dump()
                    alt["ad_type"] = get_ad_type(alt.get("ad_type")).id
                    alt["ad_type_label"] = get_ad_type(alt["ad_type"]).label
                    alt["product_id"] = alt.get("product_id") or str(request.get("product_id") or "")
                    alternative = alt
            except Exception as exc:
                logger.warning("ai_ads director challenge model failed store=%s err=%s", store_id, exc)
        return {"verdict": verdict, "notes": notes[:6], "alternative": alternative, "skipped": False}

    def save_alternative(self, db: Session, user: User, store_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self._store(db, user, store_id)
        alt = body.get("alternative") or {}
        request = body.get("request") or {}
        ad_type = get_ad_type(alt.get("ad_type"))
        product_id = str(alt.get("product_id") or request.get("product_id") or "")
        product = db.scalar(
            select(ShopifyCatalogProduct).where(
                ShopifyCatalogProduct.store_id == store_id, ShopifyCatalogProduct.shopify_product_id == product_id
            )
        )
        images, videos = clamp_media(ad_type, request.get("image_count", 1), request.get("video_count", 0))
        row = AIDirectorSuggestion(
            store_id=store_id,
            kind="new",
            status="SAVED",
            concept_name=str(alt.get("hook") or alt.get("angle") or ad_type.label)[:255],
            ad_type=ad_type.id,
            product_id=product_id or None,
            product_title=(product.title if product else "")[:512],
            image_count=images,
            video_count=videos,
            hook=str(alt.get("hook") or ""),
            angle=str(alt.get("angle") or ""),
            audience=str(alt.get("audience") or request.get("audience") or ""),
            why=str(alt.get("why") or ""),
            test_variable="angle",
            estimated_cost_usd=estimate_generation_usd(images, videos),
        )
        db.add(row)
        db.commit()
        return suggestion_card(row)


def concept_payload(row: AIDirectorSuggestion) -> dict[str, Any]:
    """What the planner must execute for this suggestion."""
    ad_type = get_ad_type(row.ad_type)
    return {
        "suggestion_id": row.id,
        "concept_name": row.concept_name,
        "ad_type": ad_type.id,
        "ad_type_label": ad_type.label,
        "direction": ad_type.direction,
        "testimonial_style": ad_type.testimonial_style,
        "hook": row.hook,
        "hook_type": row.hook_type,
        "angle": row.angle,
        "emotion": row.emotion,
        "funnel": row.funnel,
        "audience": row.audience,
        "occasion": row.occasion,
        "hypothesis": row.hypothesis,
        "test_variable": row.test_variable,
        "script": _loads(row.script_json, {}),
        "image_count": row.image_count,
        "video_count": row.video_count,
    }


def generation_body(
    row: AIDirectorSuggestion, ads: StoreAIAdsSettings | None, director: AIDirectorSettings
) -> dict[str, Any]:
    ad_type = get_ad_type(row.ad_type)
    return {
        "product_id": row.product_id,
        "image_count": row.image_count,
        "video_count": row.video_count,
        "styles": [ad_type.style],
        "audience": row.audience or (ads.default_audience if ads else ""),
        "brand_style": ads.brand_style if ads else "",
        "copy_language": director.copy_language or "auto",
        "director_concepts": [concept_payload(row)],
    }


def brief_jobs(db: Session, report: AIDirectorReport) -> list[dict[str, Any]]:
    """Group the brief's items by product: one generation job per product."""
    brief = _loads(report.brief_json, {})
    grouped: dict[str, dict[str, Any]] = {}
    for item in brief.get("items") or []:
        row = db.get(AIDirectorSuggestion, item.get("suggestion_id") or "")
        if not row or not row.product_id or row.status not in ("NEW", "SAVED"):
            continue
        group = grouped.setdefault(
            row.product_id,
            {"product_id": row.product_id, "product_title": row.product_title, "image_count": 0, "video_count": 0, "styles": [], "rows": []},
        )
        group["image_count"] += row.image_count
        group["video_count"] += row.video_count
        style = get_ad_type(row.ad_type).style
        if style not in group["styles"]:
            group["styles"].append(style)
        group["rows"].append(row)
    return list(grouped.values())


def mark_generated(db: Session, rows: list[AIDirectorSuggestion], job_id: str) -> None:
    for row in rows:
        row.status = "GENERATED"
        row.job_id = job_id
        row.decided_at = _now()
        _add_playbook(db, row.store_id, kind="hypothesis", statement=row.hypothesis, suggestion_id=row.id, source="weekly")
