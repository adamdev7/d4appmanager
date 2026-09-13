from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value
from app.core.openai_credentials import is_openai_configured, openai_key_status, resolve_openai_api_key
from app.db.models import (
    AIAdStrategy,
    AIRecommendation,
    BrandAvatar,
    CreativeAsset,
    CreativeConcept,
    CreativeDNA,
    CreativeGenerationJob,
    CreativePerformanceSnapshot,
    MetaCreative,
    Store,
    StoreAIAdsSettings,
    StoreAnalyticsSettings,
    User,
)
from app.integrations.shopify.client import ShopifyClient
from app.services.ai_ads.job_runner import enqueue_generation_job
from app.services.ai_ads.orchestrator import AdsAIOrchestrator
from app.services.ai_ads.product_context import normalize_product
from app.services.ai_ads.publisher import MetaCreativePublisher


class AIAdsService:
    def ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def get_or_create_settings(self, db: Session, store_id: str) -> StoreAIAdsSettings:
        row = db.scalar(select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == store_id))
        if row:
            return row
        row = StoreAIAdsSettings(
            store_id=store_id,
            weekly_generation_enabled=False,
            generation_day=settings.ai_ad_generation_day,
            image_count=settings.ai_ad_image_count,
            video_count=settings.ai_ad_video_count,
            auto_publish=False,
            winner_pct=settings.ai_ad_winner_pct,
            combination_pct=settings.ai_ad_combination_pct,
            exploration_pct=settings.ai_ad_exploration_pct,
            experimental_pct=settings.ai_ad_experimental_pct,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    def _orch(self, db: Session, user: User, store: Store) -> AdsAIOrchestrator:
        key = resolve_openai_api_key(user)
        if not key:
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key in AI Email Assistant → Business context first",
            )
        return AdsAIOrchestrator(db, user, store, key)

    def get_settings(self, db: Session, user: User, store_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, store_id)
        analytics = db.scalar(
            select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == store_id)
        )
        openai = openai_key_status(user)
        meta_configured = bool(
            analytics and analytics.meta_access_token_encrypted and analytics.meta_ad_account_id
        )
        try:
            styles = json.loads(row.creative_styles_json or "[]")
        except json.JSONDecodeError:
            styles = []
        return {
            "store_id": store_id,
            "weekly_generation_enabled": row.weekly_generation_enabled,
            "generation_day": row.generation_day,
            "image_count": row.image_count,
            "video_count": row.video_count,
            "auto_publish": False if not settings.ai_ad_auto_publish else row.auto_publish,
            "env_auto_publish": settings.ai_ad_auto_publish,
            "winner_pct": row.winner_pct,
            "combination_pct": row.combination_pct,
            "exploration_pct": row.exploration_pct,
            "experimental_pct": row.experimental_pct,
            "brand_style": row.brand_style,
            "default_audience": row.default_audience,
            "default_objective": row.default_objective,
            "default_placement": row.default_placement,
            "default_aspect_ratio": row.default_aspect_ratio,
            "creative_styles": styles,
            "meta_page_id": row.meta_page_id,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "last_analyze_at": row.last_analyze_at.isoformat() if row.last_analyze_at else None,
            "last_weekly_run_at": row.last_weekly_run_at.isoformat() if row.last_weekly_run_at else None,
            "meta_configured": meta_configured,
            "openai_configured": openai["openai_configured"],
            "openai_key_masked": openai["openai_key_masked"],
            "strategy_model": settings.resolved_ai_strategy_model,
            "analysis_model": settings.resolved_ai_analysis_model,
            "creative_model": settings.resolved_ai_creative_model,
            "image_model": settings.resolved_ai_image_model,
        }

    def update_settings(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self.ensure_store(db, user, store_id)
        row = self.get_or_create_settings(db, store_id)
        mapping = {
            "weekly_generation_enabled": "weekly_generation_enabled",
            "generation_day": "generation_day",
            "image_count": "image_count",
            "video_count": "video_count",
            "brand_style": "brand_style",
            "default_audience": "default_audience",
            "default_objective": "default_objective",
            "default_placement": "default_placement",
            "default_aspect_ratio": "default_aspect_ratio",
            "meta_page_id": "meta_page_id",
            "winner_pct": "winner_pct",
            "combination_pct": "combination_pct",
            "exploration_pct": "exploration_pct",
            "experimental_pct": "experimental_pct",
        }
        for key, attr in mapping.items():
            if key in body and body[key] is not None:
                setattr(row, attr, body[key])
        if "creative_styles" in body and body["creative_styles"] is not None:
            row.creative_styles_json = json.dumps(list(body["creative_styles"]))
        if "auto_publish" in body and body["auto_publish"] is not None:
            row.auto_publish = bool(body["auto_publish"]) and bool(settings.ai_ad_auto_publish)
        db.commit()
        return self.get_settings(db, user, store_id)

    def overview(self, db: Session, user: User, store_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        week_ago = datetime.now(UTC) - timedelta(days=7)
        generated_week = db.scalars(
            select(CreativeAsset).where(
                CreativeAsset.store_id == store_id,
                CreativeAsset.created_at >= week_ago,
            )
        ).all()
        images = sum(1 for a in generated_week if a.type == "IMAGE")
        videos = sum(1 for a in generated_week if a.type == "VIDEO")
        imported = db.scalar(
            select(func.count()).select_from(MetaCreative).where(MetaCreative.store_id == store_id)
        ) or 0
        analyzed = db.scalar(
            select(func.count()).select_from(CreativeDNA).where(CreativeDNA.store_id == store_id)
        ) or 0
        top = db.scalar(
            select(CreativeAsset)
            .where(CreativeAsset.store_id == store_id, CreativeAsset.ai_score.is_not(None))
            .order_by(desc(CreativeAsset.ai_score))
        )
        strategy = db.scalar(
            select(AIAdStrategy)
            .where(AIAdStrategy.store_id == store_id)
            .order_by(desc(AIAdStrategy.created_at))
        )
        recs = db.scalars(
            select(AIRecommendation)
            .where(AIRecommendation.store_id == store_id)
            .order_by(desc(AIRecommendation.created_at))
            .limit(5)
        ).all()
        running = db.scalar(
            select(CreativeGenerationJob)
            .where(
                CreativeGenerationJob.store_id == store_id,
                CreativeGenerationJob.status.in_(("QUEUED", "RUNNING")),
            )
            .order_by(desc(CreativeGenerationJob.created_at))
        )
        settings_row = self.get_or_create_settings(db, store_id)
        return {
            "generated_this_week": {"images": images, "videos": videos},
            "imported_meta_creatives": imported,
            "analyzed_creatives": analyzed,
            "top_creative": _asset_card(top) if top else None,
            "current_strategy": _strategy_card(strategy) if strategy else None,
            "recommendations": [_rec_card(r) for r in recs],
            "active_job": _job_card(running) if running else None,
            "last_sync_at": settings_row.last_sync_at.isoformat() if settings_row.last_sync_at else None,
            "last_analyze_at": settings_row.last_analyze_at.isoformat() if settings_row.last_analyze_at else None,
            "openai_configured": is_openai_configured(user),
        }

    async def list_products(self, db: Session, user: User, store_id: str) -> list[dict]:
        store = self.ensure_store(db, user, store_id)
        if not store.access_token_encrypted:
            raise HTTPException(status_code=400, detail="Connect a Shopify store first")
        try:
            token = decrypt_value(store.access_token_encrypted)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not read Shopify credentials") from exc
        client = ShopifyClient(store.shop_domain, token)
        products = await client.list_products(limit=100)
        out = []
        for p in products:
            ctx = normalize_product(p, shop_domain=store.shop_domain, currency=store.currency)
            out.append(
                {
                    "id": ctx.product_id,
                    "title": ctx.title,
                    "price": ctx.price,
                    "currency": ctx.currency,
                    "image": ctx.images[0].src if ctx.images else None,
                    "product_url": ctx.product_url,
                }
            )
        return out

    async def sync_meta(self, db: Session, user: User, store_id: str) -> dict:
        store = self.ensure_store(db, user, store_id)
        orch = self._orch(db, user, store)
        try:
            return await orch.sync_meta()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc

    async def analyze(self, db: Session, user: User, store_id: str) -> dict:
        store = self.ensure_store(db, user, store_id)
        orch = self._orch(db, user, store)
        report = await orch.analyze_creatives()
        return report.model_dump()

    async def create_strategy(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        store = self.ensure_store(db, user, store_id)
        orch = self._orch(db, user, store)
        product_id = str(body.get("product_id") or "")
        if not product_id:
            raise HTTPException(status_code=400, detail="product_id is required")
        product = await orch.load_product(product_id)
        settings_row = self.get_or_create_settings(db, store_id)
        strategy = await orch.create_strategy(
            product=product,
            brand_style=str(body.get("brand_style") or settings_row.brand_style),
            audience=str(body.get("audience") or settings_row.default_audience),
            objective=str(body.get("objective") or settings_row.default_objective),
        )
        return _strategy_card(strategy)

    def latest_strategy(self, db: Session, user: User, store_id: str) -> dict | None:
        self.ensure_store(db, user, store_id)
        row = db.scalar(
            select(AIAdStrategy)
            .where(AIAdStrategy.store_id == store_id)
            .order_by(desc(AIAdStrategy.created_at))
        )
        return _strategy_card(row) if row else None

    def create_generation_job(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self.ensure_store(db, user, store_id)
        if not resolve_openai_api_key(user):
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key in AI Email Assistant → Business context first",
            )
        product_id = str(body.get("product_id") or "")
        if not product_id:
            raise HTTPException(status_code=400, detail="product_id is required")
        settings_row = self.get_or_create_settings(db, store_id)
        payload = {
            "product_id": product_id,
            "image_count": int(body.get("image_count") or settings_row.image_count or 10),
            "video_count": int(body.get("video_count") or settings_row.video_count or 10),
            "styles": list(body.get("styles") or json.loads(settings_row.creative_styles_json or "[]")),
            "audience": body.get("audience") or settings_row.default_audience,
            "objective": body.get("objective") or settings_row.default_objective,
            "placement": body.get("placement") or settings_row.default_placement,
            "aspect_ratio": body.get("aspect_ratio") or settings_row.default_aspect_ratio,
            "brand_style": body.get("brand_style") or settings_row.brand_style,
            "avatar_id": body.get("avatar_id"),
            "portfolio_mix": {
                "winner_variation": settings_row.winner_pct,
                "combination": settings_row.combination_pct,
                "exploration": settings_row.exploration_pct,
                "experimental": settings_row.experimental_pct,
            },
        }
        job = CreativeGenerationJob(
            store_id=store_id,
            user_id=user.id,
            status="QUEUED",
            product_id=product_id,
            request_json=json.dumps(payload),
            progress_message="Queued",
            total_items=int(payload["image_count"]) + int(payload["video_count"]),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        enqueue_generation_job(job.id, resolve_openai_api_key(user) or "")
        return _job_card(job)

    def get_job(self, db: Session, user: User, store_id: str, job_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        job = db.get(CreativeGenerationJob, job_id)
        if not job or job.store_id != store_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return _job_card(job)

    def list_jobs(self, db: Session, user: User, store_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        jobs = db.scalars(
            select(CreativeGenerationJob)
            .where(CreativeGenerationJob.store_id == store_id)
            .order_by(desc(CreativeGenerationJob.created_at))
            .limit(20)
        ).all()
        return [_job_card(j) for j in jobs]

    def job_creatives(self, db: Session, user: User, store_id: str, job_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        job = db.get(CreativeGenerationJob, job_id)
        if not job or job.store_id != store_id:
            raise HTTPException(status_code=404, detail="Job not found")
        assets = db.scalars(
            select(CreativeAsset)
            .where(CreativeAsset.store_id == store_id, CreativeAsset.job_id == job_id)
            .order_by(CreativeAsset.created_at.desc())
        ).all()
        return [_asset_card(a) for a in assets]

    def list_creatives(
        self,
        db: Session,
        user: User,
        store_id: str,
        *,
        source: str | None = None,
        status: str | None = None,
        type: str | None = None,
        product_id: str | None = None,
    ) -> dict:
        self.ensure_store(db, user, store_id)
        meta_out: list[dict] = []
        gen_out: list[dict] = []
        if source in (None, "meta", "all"):
            q = select(MetaCreative).where(MetaCreative.store_id == store_id)
            metas = db.scalars(q.order_by(desc(MetaCreative.updated_at)).limit(100)).all()
            perf = _latest_perf_by_meta(db, store_id)
            dnas = _dna_by_meta(db, store_id)
            for m in metas:
                meta_out.append(_meta_card(m, perf.get(m.id), dnas.get(m.id)))
        if source in (None, "generated", "all"):
            q = select(CreativeAsset).where(CreativeAsset.store_id == store_id)
            if status:
                q = q.where(CreativeAsset.status == status.upper())
            if type:
                q = q.where(CreativeAsset.type == type.upper())
            if product_id:
                q = q.where(CreativeAsset.product_id == product_id)
            assets = db.scalars(q.order_by(desc(CreativeAsset.created_at)).limit(100)).all()
            gen_out = [_asset_card(a) for a in assets]
        return {"meta": meta_out, "generated": gen_out}

    def get_creative(self, db: Session, user: User, store_id: str, creative_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        asset = db.get(CreativeAsset, creative_id)
        if asset and asset.store_id == store_id:
            return {"kind": "generated", **_asset_card(asset, detail=True)}
        meta = db.get(MetaCreative, creative_id)
        if meta and meta.store_id == store_id:
            perf = _latest_perf_by_meta(db, store_id).get(meta.id)
            dna = _dna_by_meta(db, store_id).get(meta.id)
            return {"kind": "meta", **_meta_card(meta, perf, dna, detail=True)}
        raise HTTPException(status_code=404, detail="Creative not found")

    def set_status(
        self, db: Session, user: User, store_id: str, creative_id: str, status: str
    ) -> dict:
        self.ensure_store(db, user, store_id)
        asset = db.get(CreativeAsset, creative_id)
        if not asset or asset.store_id != store_id:
            raise HTTPException(status_code=404, detail="Creative not found")
        asset.status = status
        db.commit()
        db.refresh(asset)
        return _asset_card(asset)

    def regenerate(self, db: Session, user: User, store_id: str, creative_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        asset = db.get(CreativeAsset, creative_id)
        if not asset or asset.store_id != store_id:
            raise HTTPException(status_code=404, detail="Creative not found")
        if not asset.product_id:
            raise HTTPException(status_code=400, detail="Creative has no product to regenerate from")
        body = {
            "product_id": asset.product_id,
            "image_count": 1 if asset.type == "IMAGE" else 0,
            "video_count": 1 if asset.type == "VIDEO" else 0,
            "styles": [asset.type],
        }
        return self.create_generation_job(db, user, store_id, body)

    def performance(self, db: Session, user: User, store_id: str) -> dict:
        self.ensure_store(db, user, store_id)
        snaps = db.scalars(
            select(CreativePerformanceSnapshot)
            .where(CreativePerformanceSnapshot.store_id == store_id)
            .order_by(desc(CreativePerformanceSnapshot.created_at))
            .limit(200)
        ).all()
        seen: set[str] = set()
        latest: list[dict] = []
        for s in snaps:
            key = s.meta_creative_row_id or s.generated_asset_id or s.id
            if key in seen:
                continue
            seen.add(key)
            latest.append(_perf_card(s))
        return {"snapshots": latest, "count": len(latest)}

    def recommendations(self, db: Session, user: User, store_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        rows = db.scalars(
            select(AIRecommendation)
            .where(AIRecommendation.store_id == store_id)
            .order_by(desc(AIRecommendation.created_at))
            .limit(50)
        ).all()
        return [_rec_card(r) for r in rows]

    def list_avatars(self, db: Session, user: User, store_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        rows = db.scalars(select(BrandAvatar).where(BrandAvatar.store_id == store_id)).all()
        return [_avatar_card(a) for a in rows]

    def upsert_avatar(self, db: Session, user: User, store_id: str, body: dict) -> dict:
        self.ensure_store(db, user, store_id)
        avatar_id = body.get("id")
        row = db.get(BrandAvatar, avatar_id) if avatar_id else None
        if row and row.store_id != store_id:
            raise HTTPException(status_code=404, detail="Avatar not found")
        if not row:
            row = BrandAvatar(store_id=store_id)
            db.add(row)
        row.name = str(body.get("name") or row.name or "")
        row.image_url = body.get("image_url") or row.image_url
        row.description = str(body.get("description") or row.description or "")
        row.usage_rules = str(body.get("usage_rules") or row.usage_rules or "")
        if "active" in body:
            row.active = bool(body["active"])
        db.commit()
        db.refresh(row)
        return _avatar_card(row)

    async def publish(self, db: Session, user: User, store_id: str, creative_id: str, body: dict) -> dict:
        store = self.ensure_store(db, user, store_id)
        asset = db.get(CreativeAsset, creative_id)
        if not asset or asset.store_id != store_id:
            raise HTTPException(status_code=404, detail="Creative not found")
        if asset.status != "APPROVED":
            raise HTTPException(status_code=400, detail="Approve the creative before publishing")
        settings_row = self.get_or_create_settings(db, store_id)
        orch = self._orch(db, user, store)
        meta = orch.meta_client()
        if not meta:
            raise HTTPException(status_code=400, detail="Connect Meta Ads first")
        publisher = MetaCreativePublisher(meta)
        adset_id = str(body.get("adset_id") or "")
        if not adset_id:
            raise HTTPException(status_code=400, detail="adset_id is required")
        activate = bool(body.get("activate")) and bool(settings.ai_ad_auto_publish) and settings_row.auto_publish
        try:
            created = await publisher.publish_ad(
                asset,
                adset_id=adset_id,
                settings_row=settings_row,
                page_id=body.get("page_id"),
                activate=activate,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        asset.meta_ad_id = str(created.get("id") or "") or None
        asset.status = "PUBLISHED" if activate else "PAUSED"
        db.commit()
        return {"ok": True, "meta": created, "creative": _asset_card(asset)}


def _latest_perf_by_meta(db: Session, store_id: str) -> dict[str, CreativePerformanceSnapshot]:
    snaps = db.scalars(
        select(CreativePerformanceSnapshot)
        .where(CreativePerformanceSnapshot.store_id == store_id)
        .order_by(desc(CreativePerformanceSnapshot.created_at))
    ).all()
    out: dict[str, CreativePerformanceSnapshot] = {}
    for s in snaps:
        if s.meta_creative_row_id and s.meta_creative_row_id not in out:
            out[s.meta_creative_row_id] = s
    return out


def _dna_by_meta(db: Session, store_id: str) -> dict[str, CreativeDNA]:
    rows = db.scalars(select(CreativeDNA).where(CreativeDNA.store_id == store_id)).all()
    return {r.meta_creative_row_id: r for r in rows if r.meta_creative_row_id}


def _preview(path: str | None, fallback: str | None = None) -> str | None:
    if path:
        return f"/uploads/{path.lstrip('/')}" if not path.startswith("/") and not path.startswith("http") else path
    return fallback


def _storyboard_preview(a: CreativeAsset) -> dict | None:
    if a.type != "VIDEO" or not a.video_spec_json:
        return None
    try:
        payload = json.loads(a.video_spec_json)
    except json.JSONDecodeError:
        return None
    spec = payload.get("spec") if isinstance(payload, dict) else None
    if not isinstance(spec, dict):
        return None
    scenes = spec.get("scenes") or []
    return {
        "hook": spec.get("hook"),
        "duration": spec.get("duration"),
        "format": spec.get("format"),
        "cta": spec.get("cta"),
        "scenes": [
            {
                "duration": scene.get("duration"),
                "visual": scene.get("visual"),
                "text_overlay": scene.get("text_overlay"),
            }
            for scene in scenes[:6]
            if isinstance(scene, dict)
        ],
    }


def _meta_card(
    m: MetaCreative,
    perf: CreativePerformanceSnapshot | None,
    dna: CreativeDNA | None,
    detail: bool = False,
) -> dict:
    card = {
        "id": m.id,
        "source": "META",
        "campaign_name": m.campaign_name,
        "ad_name": m.ad_name,
        "ad_id": m.ad_id,
        "format": m.format,
        "headline": m.headline,
        "primary_text": m.primary_text,
        "cta": m.cta,
        "preview_url": _preview(m.local_asset_path or m.local_thumbnail_path, m.image_url or m.video_thumbnail),
        "performance": _perf_card(perf) if perf else {"insufficient_data": True},
        "dna": {
            "visual": json.loads(dna.visual_dna_json) if dna else {},
            "copy": json.loads(dna.copy_dna_json) if dna else {},
            "format": json.loads(dna.format_dna_json) if dna else {},
            "performance": json.loads(dna.performance_dna_json) if dna else {},
            "analysis_basis": dna.analysis_basis if dna else None,
        },
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
    if detail:
        card["description"] = m.description
        card["destination_url"] = m.destination_url
        card["campaign_id"] = m.campaign_id
        card["adset_name"] = m.adset_name
        card["video_id"] = m.video_id
        card["analysis"] = json.loads(dna.analysis_json) if dna else {}
    return card


def _asset_card(a: CreativeAsset | None, detail: bool = False) -> dict:
    if not a:
        return {}
    card = {
        "id": a.id,
        "source": "AI_GENERATED",
        "type": a.type,
        "status": a.status,
        "product_id": a.product_id,
        "hook": a.hook,
        "headline": a.headline,
        "primary_text": a.primary_text,
        "cta": a.cta,
        "preview_url": _preview(a.local_path, a.preview_url),
        "ai_score": a.ai_score,
        "score_label": "AI Creative Evaluation",
        "score_breakdown": json.loads(a.score_breakdown_json or "{}"),
        "source_strategy_id": a.source_strategy_id,
        "source_creative_ids": json.loads(a.source_creative_ids_json or "[]"),
        "rationale": a.rationale,
        "visual_direction": a.visual_direction,
        "aspect_ratio": a.aspect_ratio,
        "placement": a.placement,
        "width": a.width,
        "height": a.height,
        "storyboard": _storyboard_preview(a),
        "failure_reason": a.failure_reason,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    if detail:
        card["video_spec"] = json.loads(a.video_spec_json) if a.video_spec_json else None
        card["concept_id"] = a.concept_id
        card["job_id"] = a.job_id
        card["meta_ad_id"] = a.meta_ad_id
    return card


def _strategy_card(s: AIAdStrategy | None) -> dict:
    if not s:
        return {}
    body = json.loads(s.strategy_json or "{}")
    report = json.loads(s.intelligence_report_json or "{}")
    return {
        "id": s.id,
        "product_id": s.product_id,
        "summary": s.summary,
        "target_audience": s.target_audience,
        "confidence": s.confidence,
        "strategy": body,
        "intelligence_report": report,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "model_used": s.model_used,
    }


def _rec_card(r: AIRecommendation) -> dict:
    return {
        "id": r.id,
        "title": r.title,
        "explanation": r.explanation,
        "supporting_creative_ids": json.loads(r.supporting_creative_ids_json or "[]"),
        "supporting_metrics": json.loads(r.supporting_metrics_json or "{}"),
        "confidence": r.confidence,
        "recommended_action": r.recommended_action,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _job_card(j: CreativeGenerationJob) -> dict:
    return {
        "job_id": j.id,
        "id": j.id,
        "status": j.status,
        "product_id": j.product_id,
        "progress_message": j.progress_message,
        "total_items": j.total_items,
        "completed_items": j.completed_items,
        "failed_items": j.failed_items,
        "error_message": j.error_message,
        "strategy_id": j.strategy_id,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


def _perf_card(s: CreativePerformanceSnapshot | None) -> dict:
    if not s:
        return {"insufficient_data": True}
    return {
        "impressions": s.impressions,
        "reach": s.reach,
        "clicks": s.clicks,
        "spend": s.spend,
        "ctr": s.ctr,
        "cpc": s.cpc,
        "cpm": s.cpm,
        "purchases": s.purchases,
        "cpa": s.cpa,
        "conversion_value": s.conversion_value,
        "roas": s.roas,
        "video_views": s.video_views,
        "frequency": s.frequency,
        "date_range_start": s.date_range_start,
        "date_range_end": s.date_range_end,
        "insufficient_data": s.insufficient_data,
        "ad_id": s.ad_id,
    }


def _avatar_card(a: BrandAvatar) -> dict:
    return {
        "id": a.id,
        "name": a.name,
        "image_url": a.image_url,
        "description": a.description,
        "usage_rules": a.usage_rules,
        "active": a.active,
    }
