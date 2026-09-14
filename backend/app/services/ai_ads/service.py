from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, desc, func, or_, select
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
from app.services.ai_ads.complete_creative import clamp_generation_counts, resolve_generation_counts
from app.services.ai_ads.job_progress import append_job_progress, parse_job_log
from app.services.ai_ads.job_runner import enqueue_generation_job, is_job_running, request_cancel
from app.services.ai_ads.orchestrator import AdsAIOrchestrator
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.product_catalog import ShopifyProductCatalog, enqueue_catalog_sync
from app.services.ai_ads.publisher import MetaCreativePublisher


class AIAdsService:
    def ensure_store(self, db: Session, user: User, store_id: str) -> Store:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=404, detail="Store not found")
        return store

    def _owned_asset(self, db: Session, user: User, store_id: str, creative_id: str) -> CreativeAsset:
        self.ensure_store(db, user, store_id)
        asset = db.get(CreativeAsset, creative_id)
        if not asset or asset.store_id != store_id:
            raise HTTPException(status_code=404, detail="Creative not found")
        if asset.user_id and asset.user_id != user.id:
            raise HTTPException(status_code=404, detail="Creative not found")
        return asset

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
            "image_count": clamp_generation_counts(row.image_count, 0)[0],
            "video_count": clamp_generation_counts(0, row.video_count)[1],
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
            "video_model": settings.resolved_ai_video_model,
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
                _owned_assets(user.id),
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
            .where(
                CreativeAsset.store_id == store_id,
                _owned_assets(user.id),
                CreativeAsset.ai_score.is_not(None),
            )
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
        if running:
            self._kick_if_stuck(db, user, running)
            db.refresh(running)
        workplace = db.scalar(
            select(CreativeGenerationJob)
            .where(CreativeGenerationJob.store_id == store_id)
            .order_by(desc(CreativeGenerationJob.created_at))
        )
        if workplace and workplace.status in ("QUEUED", "RUNNING"):
            self._kick_if_stuck(db, user, workplace)
            db.refresh(workplace)
        recent = db.scalars(
            select(CreativeGenerationJob)
            .where(CreativeGenerationJob.store_id == store_id)
            .order_by(desc(CreativeGenerationJob.created_at))
            .limit(8)
        ).all()
        settings_row = self.get_or_create_settings(db, store_id)
        return {
            "generated_this_week": {"images": images, "videos": videos},
            "imported_meta_creatives": imported,
            "analyzed_creatives": analyzed,
            "top_creative": _asset_card(top) if top else None,
            "current_strategy": _strategy_card(strategy) if strategy else None,
            "recommendations": [_rec_card(r) for r in recs],
            "active_job": _job_card(running) if running else None,
            "workplace_job": _job_card(workplace) if workplace else None,
            "recent_jobs": [_job_card(j) for j in recent],
            "last_sync_at": settings_row.last_sync_at.isoformat() if settings_row.last_sync_at else None,
            "last_analyze_at": settings_row.last_analyze_at.isoformat() if settings_row.last_analyze_at else None,
            "openai_configured": is_openai_configured(user),
        }

    async def list_products(self, db: Session, user: User, store_id: str) -> list[dict]:
        store = self.ensure_store(db, user, store_id)
        if not store.access_token_encrypted:
            raise HTTPException(status_code=400, detail="Connect a Shopify store first")
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        cached = catalog.list_picker_cards()
        enqueue_catalog_sync(store.id)
        if cached:
            return cached
        try:
            token = decrypt_value(store.access_token_encrypted)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not read Shopify credentials") from exc
        client = ShopifyClient(store.shop_domain, token)
        try:
            products = await asyncio.wait_for(
                client.list_products(limit=50, max_items=50),
                timeout=12,
            )
        except Exception as err:
            raise HTTPException(
                status_code=504,
                detail="Shopify took too long to list products. Try Generate again in a few seconds.",
            ) from err
        for raw in products:
            catalog.upsert_product_row(raw)
        db.commit()
        enqueue_catalog_sync(store.id)
        return catalog.list_picker_cards()

    def upload_product_photos(
        self,
        db: Session,
        user: User,
        store_id: str,
        product_id: str,
        blobs: list[bytes],
    ) -> dict:
        store = self.ensure_store(db, user, store_id)
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        try:
            card = catalog.store_manual_photos(product_id, blobs)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        if not card.get("photos_cached"):
            raise HTTPException(
                status_code=400,
                detail="Could not use those pictures. PNG is converted automatically — try another file if this one is damaged.",
            )
        return card

    async def product_photo(
        self,
        db: Session,
        store_id: str,
        product_id: str,
        image_key: str,
    ) -> tuple[bytes, str]:
        """Serve one stored product photo, rebuilding it from Shopify if the cache is cold.

        Unauthenticated on purpose: browsers cannot send a bearer token on an <img> tag, and the
        paths are unguessable (store uuid + Shopify ids). Exposes only the product photos the
        merchant already publishes on their storefront.
        """
        store = db.get(Store, store_id)
        if not store:
            raise HTTPException(status_code=404, detail="Photo not found")
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        got = await catalog.photo_for_key(product_id, image_key)
        if not got:
            raise HTTPException(status_code=404, detail="Photo not found")
        return got

    def clear_product_photos(self, db: Session, user: User, store_id: str, product_id: str) -> dict:
        store = self.ensure_store(db, user, store_id)
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        card = catalog.clear_product_photos(product_id)
        if not card:
            raise HTTPException(status_code=404, detail="Product not found")
        return card

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
        store = self.ensure_store(db, user, store_id)
        if not resolve_openai_api_key(user):
            raise HTTPException(
                status_code=400,
                detail="Add your OpenAI API key in AI Email Assistant → Business context first",
            )
        product_id = str(body.get("product_id") or "")
        if not product_id:
            raise HTTPException(status_code=400, detail="product_id is required")
        catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
        # Matches the picker's photos_cached: bytes on hand, or a Shopify source the job can refetch.
        if not catalog.has_usable_photos(product_id):
            raise HTTPException(
                status_code=400,
                detail="Add product pictures first. Save them on Generate, then run again.",
            )
        settings_row = self.get_or_create_settings(db, store_id)
        images, videos = resolve_generation_counts(
            body.get("image_count"),
            body.get("video_count"),
            default_images=settings_row.image_count if settings_row.image_count is not None else 3,
            default_videos=settings_row.video_count if settings_row.video_count is not None else 2,
        )
        if images + videos < 1:
            raise HTTPException(
                status_code=400,
                detail="Set images or videos above 0. Astra will not generate a type you set to 0.",
            )
        payload = {
            "product_id": product_id,
            "image_count": images,
            "video_count": videos,
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
            progress_message="Queued — starting worker",
            progress_step="queued",
            progress_pct=2,
            total_items=int(payload["image_count"]) + int(payload["video_count"]),
        )
        append_job_progress(
            job,
            step="queued",
            title="Queued — starting worker",
            detail="Job saved. The AI worker will load your product, learn from Meta ads, then generate creatives.",
            pct=2,
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
        self._kick_if_stuck(db, user, job)
        db.refresh(job)
        card = _job_card(job)
        assets = db.scalars(
            select(CreativeAsset)
            .where(
                CreativeAsset.store_id == store_id,
                CreativeAsset.job_id == job.id,
                _owned_assets(user.id),
            )
            .order_by(CreativeAsset.created_at.asc())
        ).all()
        card["creatives"] = [_asset_card(a) for a in assets]
        return card

    def list_jobs(self, db: Session, user: User, store_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        jobs = db.scalars(
            select(CreativeGenerationJob)
            .where(CreativeGenerationJob.store_id == store_id)
            .order_by(desc(CreativeGenerationJob.created_at))
            .limit(50)
        ).all()
        for j in jobs:
            if j.status in ("QUEUED", "RUNNING"):
                self._kick_if_stuck(db, user, j)
                db.refresh(j)
        return [_job_card(j) for j in jobs]

    def _kick_if_stuck(self, db: Session, user: User, job: CreativeGenerationJob) -> None:
        """Re-start a queued or abandoned running job if the worker is not alive."""
        if job.status not in ("QUEUED", "RUNNING"):
            return
        if is_job_running(job.id):
            return
        if job.status == "RUNNING":
            job.status = "QUEUED"
            job.error_message = None
            db.commit()
        enqueue_generation_job(job.id, resolve_openai_api_key(user) or "")

    def _require_job(self, db: Session, user: User, store_id: str, job_id: str) -> CreativeGenerationJob:
        self.ensure_store(db, user, store_id)
        job = db.get(CreativeGenerationJob, job_id)
        if not job or job.store_id != store_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    def stop_generation_job(self, db: Session, user: User, store_id: str, job_id: str) -> dict:
        job = self._require_job(db, user, store_id, job_id)
        request_cancel(job.id)
        if job.status in ("QUEUED", "RUNNING"):
            job.status = "CANCELLED"
            job.finished_at = datetime.now(UTC)
            job.error_message = "Stopped from the workplace console."
            append_job_progress(
                job,
                step="error",
                title="Generation halted",
                detail="Operator stopped this run. Ready creatives were kept. Use Replay to start a fresh job.",
                pct=job.progress_pct or 0,
            )
            db.commit()
            db.refresh(job)
        return _job_card(job)

    def restart_generation_job(self, db: Session, user: User, store_id: str, job_id: str) -> dict:
        job = self._require_job(db, user, store_id, job_id)
        if job.status in ("QUEUED", "RUNNING"):
            self.stop_generation_job(db, user, store_id, job_id)
            db.refresh(job)
        try:
            body = json.loads(job.request_json or "{}")
        except json.JSONDecodeError:
            body = {}
        if not isinstance(body, dict) or not body.get("product_id"):
            raise HTTPException(status_code=400, detail="This job has no saved brief to replay.")
        return self.create_generation_job(db, user, store_id, body)

    def nudge_generation_job(self, db: Session, user: User, store_id: str, job_id: str) -> dict:
        job = self._require_job(db, user, store_id, job_id)
        if job.status not in ("QUEUED", "RUNNING"):
            raise HTTPException(
                status_code=400,
                detail="Nudge only wakes a queued or running job. Use Replay to start a new run.",
            )
        if is_job_running(job.id):
            card = _job_card(job)
            card["nudge"] = "already_alive"
            return card
        if job.status == "RUNNING":
            job.status = "QUEUED"
            job.error_message = None
            append_job_progress(
                job,
                step="queued",
                title="Worker nudged",
                detail="Signal lost — re-queuing this job so a new worker can pick it up.",
                pct=max(job.progress_pct or 0, 4),
            )
            db.commit()
            db.refresh(job)
        else:
            append_job_progress(
                job,
                step="queued",
                title="Worker nudged",
                detail="Re-sent this job to the generation worker.",
                pct=max(job.progress_pct or 0, 4),
            )
            db.commit()
        enqueue_generation_job(job.id, resolve_openai_api_key(user) or "")
        card = _job_card(job)
        card["nudge"] = "enqueued"
        return card

    def sweep_generation_job(self, db: Session, user: User, store_id: str, job_id: str) -> dict:
        job = self._require_job(db, user, store_id, job_id)
        leftovers = db.scalars(
            select(CreativeAsset)
            .where(
                CreativeAsset.store_id == store_id,
                CreativeAsset.job_id == job.id,
                _owned_assets(user.id),
                CreativeAsset.status.in_(("GENERATING", "FAILED", "QUEUED", "DRAFT")),
            )
        ).all()
        swept = 0
        for asset in list(leftovers):
            try:
                self.delete_creative(db, user, store_id, asset.id)
                swept += 1
            except HTTPException:
                continue
        card = self.get_job(db, user, store_id, job.id)
        card["swept_count"] = swept
        return card

    def job_creatives(self, db: Session, user: User, store_id: str, job_id: str) -> list[dict]:
        self.ensure_store(db, user, store_id)
        job = db.get(CreativeGenerationJob, job_id)
        if not job or job.store_id != store_id:
            raise HTTPException(status_code=404, detail="Job not found")
        assets = db.scalars(
            select(CreativeAsset)
            .where(
                CreativeAsset.store_id == store_id,
                CreativeAsset.job_id == job_id,
                _owned_assets(user.id),
            )
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
            q = select(CreativeAsset).where(
                CreativeAsset.store_id == store_id,
                _owned_assets(user.id),
            )
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
        try:
            asset = self._owned_asset(db, user, store_id, creative_id)
        except HTTPException:
            asset = None
        if asset:
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
        asset = self._owned_asset(db, user, store_id, creative_id)
        asset.status = status
        db.commit()
        db.refresh(asset)
        return _asset_card(asset)

    def regenerate(self, db: Session, user: User, store_id: str, creative_id: str) -> dict:
        asset = self._owned_asset(db, user, store_id, creative_id)
        if not asset.product_id:
            raise HTTPException(status_code=400, detail="Creative has no product to regenerate from")
        settings_row = self.get_or_create_settings(db, store_id)
        try:
            styles = json.loads(settings_row.creative_styles_json or "[]")
        except json.JSONDecodeError:
            styles = []
        if not isinstance(styles, list) or not styles:
            styles = ["UGC", "PRODUCT_DEMO", "LIFESTYLE"]
        kind = (asset.type or "IMAGE").upper()
        body = {
            "product_id": asset.product_id,
            "image_count": 1 if kind != "VIDEO" else 0,
            "video_count": 1 if kind == "VIDEO" else 0,
            "styles": [str(s) for s in styles if s],
            "placement": asset.placement or settings_row.default_placement,
            "aspect_ratio": asset.aspect_ratio or settings_row.default_aspect_ratio,
            "brand_style": settings_row.brand_style or "",
        }
        return self.create_generation_job(db, user, store_id, body)

    def delete_creative(self, db: Session, user: User, store_id: str, creative_id: str) -> dict:
        asset = self._owned_asset(db, user, store_id, creative_id)
        concept_id = asset.concept_id
        CreativeAssetStore(store_id).delete_local(asset.local_path)
        if asset.preview_url and asset.preview_url != asset.local_path:
            CreativeAssetStore(store_id).delete_local(asset.preview_url)
        db.execute(
            delete(CreativePerformanceSnapshot).where(
                CreativePerformanceSnapshot.generated_asset_id == asset.id
            )
        )
        db.delete(asset)
        db.flush()
        if concept_id:
            remaining = db.scalar(
                select(func.count())
                .select_from(CreativeAsset)
                .where(CreativeAsset.concept_id == concept_id)
            ) or 0
            if remaining == 0:
                concept = db.get(CreativeConcept, concept_id)
                if concept and concept.store_id == store_id:
                    if not concept.user_id or concept.user_id == user.id:
                        db.delete(concept)
        db.commit()
        return {"ok": True, "deleted_id": creative_id}

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
        asset = self._owned_asset(db, user, store_id, creative_id)
        if asset.status != "APPROVED":
            raise HTTPException(status_code=400, detail="Approve the creative before publishing")
        settings_row = self.get_or_create_settings(db, store_id)
        orch = self._orch(db, user, store)
        meta = orch.meta_client()
        if not meta:
            raise HTTPException(status_code=400, detail="Connect Meta Ads first")
        if not asset.local_path and not asset.preview_url:
            raise HTTPException(
                status_code=400,
                detail="This creative has no rendered image or video. Generate again before publishing.",
            )
        publisher = MetaCreativePublisher(meta, store_id)
        adset_id = str(body.get("adset_id") or "")
        if not adset_id:
            raise HTTPException(status_code=400, detail="adset_id is required")
        activate = bool(body.get("activate"))
        destination = _store_destination_url(store)
        try:
            created = await publisher.publish_ad(
                asset,
                adset_id=adset_id,
                settings_row=settings_row,
                page_id=body.get("page_id"),
                activate=activate,
                destination_url=destination,
            )
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        asset.meta_ad_id = str(created.get("id") or "") or None
        asset.meta_published_creative_id = str(created.get("creative_id") or "") or None
        asset.status = "PUBLISHED" if activate else "PAUSED"
        db.commit()
        return {"ok": True, "activated": activate, "meta": created, "creative": _asset_card(asset)}

    async def list_adsets(self, db: Session, user: User, store_id: str) -> list[dict]:
        store = self.ensure_store(db, user, store_id)
        orch = self._orch(db, user, store)
        meta = orch.meta_client()
        if not meta:
            raise HTTPException(status_code=400, detail="Connect Meta Ads first")
        try:
            rows = await meta.list_adsets()
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)[:400]) from exc
        out = []
        for row in rows:
            if not row.get("id"):
                continue
            out.append(
                {
                    "id": row.get("id"),
                    "name": row.get("name") or row.get("id"),
                    "status": row.get("effective_status") or row.get("status"),
                    "campaign_id": row.get("campaign_id"),
                }
            )
        return out


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


def _owned_assets(user_id: str):
    return or_(CreativeAsset.user_id == user_id, CreativeAsset.user_id.is_(None))


def _store_destination_url(store: Store) -> str | None:
    domain = (getattr(store, "shop_domain", None) or "").strip()
    if not domain:
        return None
    domain = domain.replace("https://", "").replace("http://", "").strip("/")
    return f"https://{domain}" if domain else None


def _normalize_preview(raw: str | None) -> str | None:
    path = (raw or "").strip()
    if not path:
        return None
    if path.startswith(("http://", "https://", "data:")):
        return path
    if path.startswith("/uploads/"):
        return path
    if path.startswith("uploads/"):
        return f"/{path}"
    return f"/uploads/{path.lstrip('/')}"


def _preview(path: str | None, fallback: str | None = None) -> str | None:
    return _normalize_preview(path) or _normalize_preview(fallback)


def _is_video_file(path: str | None) -> bool:
    return bool(path) and str(path).lower().endswith((".mp4", ".mov", ".webm"))


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
                "voiceover": scene.get("voiceover"),
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
        "user_id": a.user_id,
        "type": a.type,
        "status": a.status,
        "product_id": a.product_id,
        "hook": a.hook,
        "headline": a.headline,
        "primary_text": a.primary_text,
        "cta": a.cta,
        "preview_url": _preview(None if _is_video_file(a.local_path) else a.local_path, a.preview_url),
        "video_url": _preview(a.local_path) if _is_video_file(a.local_path) else None,
        "has_rendered_media": bool(a.local_path or a.preview_url),
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
        "meta_ad_id": a.meta_ad_id,
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
    log = parse_job_log(j)
    latest = log[-1] if log else {}
    pct = int(getattr(j, "progress_pct", 0) or 0)
    if pct <= 0 and j.total_items:
        pct = int(((j.completed_items or 0) / max(j.total_items, 1)) * 100)
    req: dict = {}
    try:
        parsed = json.loads(j.request_json or "{}")
        if isinstance(parsed, dict):
            req = parsed
    except Exception:
        req = {}
    return {
        "job_id": j.id,
        "id": j.id,
        "status": j.status,
        "product_id": j.product_id,
        "progress_message": j.progress_message or (latest.get("title") if isinstance(latest, dict) else "") or "",
        "progress_step": getattr(j, "progress_step", None) or (latest.get("step") if isinstance(latest, dict) else "") or "",
        "progress_pct": pct,
        "progress_log": log,
        "thinking": (latest.get("detail") if isinstance(latest, dict) else "") or "",
        "total_items": j.total_items,
        "completed_items": j.completed_items,
        "failed_items": j.failed_items,
        "error_message": j.error_message,
        "strategy_id": j.strategy_id,
        "image_count": req.get("image_count"),
        "video_count": req.get("video_count"),
        "placement": req.get("placement"),
        "aspect_ratio": req.get("aspect_ratio"),
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "started_at": j.started_at.isoformat() if j.started_at else None,
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        "worker_alive": is_job_running(j.id),
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
