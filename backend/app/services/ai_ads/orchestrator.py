from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value
from app.db.models import (
    AIAdStrategy,
    BrandAvatar,
    CreativeAsset,
    CreativeGenerationJob,
    MetaCreative,
    Store,
    StoreAIAdsSettings,
    StoreAnalyticsSettings,
    User,
)
from app.integrations.meta.client import MetaAdsClient
from app.integrations.shopify.client import ShopifyClient
from app.services.ai_ads.complete_creative import (
    build_image_prompt,
    clamp_generation_counts,
    heuristic_score,
    video_spec_from_concept,
    winning_style_notes,
)
from app.services.ai_ads.creative_intelligence import CreativeIntelligenceAnalyzer
from app.services.ai_ads.creative_planner import CreativePlanner
from app.services.ai_ads.exceptions import AIAdsError, ImageGenerationError
from app.services.ai_ads.meta_importer import MetaCreativeImporter
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.product_context import normalize_product
from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
from app.services.ai_ads.providers.video_provider import UnconfiguredVideoProvider
from app.services.ai_ads.recommendation_engine import RecommendationEngine
from app.services.ai_ads.schemas import CreativeIntelligenceReport, ImageGenerationRequest, ProductContext, VideoSpec
from app.services.ai_ads.strategy import CreativeStrategyEngine
from app.services.ai_ads.asset_store import CreativeAssetStore

logger = logging.getLogger(__name__)


class AdsAIOrchestrator:
    """Coordinates Shopify + Meta + multimodal analysis + generation. Modular steps."""

    def __init__(self, db: Session, user: User, store: Store, api_key: str) -> None:
        self.db = db
        self.user = user
        self.store = store
        self.api_key = api_key
        self.client = AdsOpenAIClient(api_key, store_id=store.id)
        self.assets = CreativeAssetStore(store.id)

    def meta_client(self) -> MetaAdsClient | None:
        analytics = self.db.scalar(
            select(StoreAnalyticsSettings).where(StoreAnalyticsSettings.store_id == self.store.id)
        )
        if not analytics or not analytics.meta_access_token_encrypted or not analytics.meta_ad_account_id:
            return None
        try:
            token = decrypt_value(analytics.meta_access_token_encrypted)
        except Exception:
            return None
        return MetaAdsClient(token, analytics.meta_ad_account_id)

    def shopify_client(self) -> ShopifyClient | None:
        if not self.store.access_token_encrypted:
            return None
        try:
            token = decrypt_value(self.store.access_token_encrypted)
        except Exception:
            return None
        return ShopifyClient(self.store.shop_domain, token)

    async def load_product(self, product_id: str) -> ProductContext:
        client = self.shopify_client()
        if not client:
            raise AIAdsError("Connect a Shopify store first")
        raw = await client.get_product(product_id)
        return normalize_product(
            raw,
            shop_domain=self.store.shop_domain,
            currency=self.store.currency,
            brand_name=self.store.name,
        )

    async def sync_meta(self, *, since: str | None = None, until: str | None = None) -> dict[str, Any]:
        meta = self.meta_client()
        if not meta:
            raise AIAdsError("Connect Meta Ads (token + ad account) in Ads or Analytics settings")
        importer = MetaCreativeImporter(meta, self.store.id)
        result = await importer.sync(self.db, since=since, until=until)
        ads_settings = self.db.scalar(
            select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == self.store.id)
        )
        if ads_settings:
            ads_settings.last_sync_at = datetime.now(UTC)
            self.db.commit()
        return result

    async def analyze_creatives(self, *, limit: int = 8) -> CreativeIntelligenceReport:
        analyzer = CreativeIntelligenceAnalyzer(self.client, self.store.id)
        items = analyzer.listed_creatives(self.db, limit=80)
        missing = analyzer.creatives_missing_dna(items, limit=min(limit, 8))
        perf = analyzer.latest_performance_map(self.db)
        for c in missing:
            try:
                await analyzer.analyze_one(self.db, c, perf.get(c.id))
            except Exception as exc:
                logger.warning("ai_ads analyze one failed store_id=%s id=%s err=%s", self.store.id, c.id, exc)
        report = await analyzer.build_report(self.db, limit=40)
        recs = RecommendationEngine(self.client, self.store.id)
        await recs.generate(self.db, report=report)
        ads_settings = self.db.scalar(
            select(StoreAIAdsSettings).where(StoreAIAdsSettings.store_id == self.store.id)
        )
        if ads_settings:
            ads_settings.last_analyze_at = datetime.now(UTC)
            self.db.commit()
        return report

    async def create_strategy(
        self,
        *,
        product: ProductContext,
        report: CreativeIntelligenceReport | None = None,
        brand_style: str = "",
        audience: str = "",
        objective: str = "conversions",
    ) -> AIAdStrategy:
        if report is None:
            analyzer = CreativeIntelligenceAnalyzer(self.client, self.store.id)
            report = await analyzer.build_report(self.db)
        engine = CreativeStrategyEngine(self.client, self.store.id)
        return await engine.generate(
            self.db,
            product=product,
            report=report,
            brand_style=brand_style,
            audience=audience,
            objective=objective,
        )

    async def run_generation_job(self, job: CreativeGenerationJob) -> None:
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        job.progress_message = "Loading product context"
        self.db.commit()
        try:
            request = json.loads(job.request_json or "{}")
            product = await self.load_product(job.product_id or request.get("product_id"))
            image_count, video_count = clamp_generation_counts(
                int(request.get("image_count") or settings.ai_ad_image_count),
                int(request.get("video_count") or settings.ai_ad_video_count),
            )
            styles = list(request.get("styles") or ["UGC", "PRODUCT_DEMO", "LIFESTYLE"])
            audience = str(request.get("audience") or "")
            objective = str(request.get("objective") or "conversions")
            placement = str(request.get("placement") or "feed")
            aspect = str(request.get("aspect_ratio") or "4:5")
            brand_style = str(request.get("brand_style") or "")
            avatar_id = request.get("avatar_id")
            mix = request.get("portfolio_mix")

            job.total_items = image_count + video_count
            job.progress_message = "Learning from Meta campaign performance"
            self.db.commit()

            meta_count = (
                self.db.scalar(
                    select(MetaCreative.id).where(MetaCreative.store_id == self.store.id).limit(1)
                )
                is not None
            )
            if not meta_count:
                job.progress_message = "Syncing Meta creatives"
                self.db.commit()
                try:
                    await self.sync_meta()
                except Exception as exc:
                    logger.warning("ai_ads job sync skipped store_id=%s err=%s", self.store.id, exc)

            analyzer = CreativeIntelligenceAnalyzer(self.client, self.store.id)
            brief = analyzer.campaign_brief(self.db)
            winning_notes = winning_style_notes(brief.get("winning") or [])

            avatar = None
            if avatar_id:
                avatar = self.db.get(BrandAvatar, avatar_id)
                if avatar and avatar.store_id != self.store.id:
                    avatar = None

            job.progress_message = "Planning complete image and video ads"
            self.db.commit()
            planner = CreativePlanner(self.client, self.store.id)
            strategy, paired = await planner.plan_complete(
                self.db,
                product=product,
                brief=brief,
                image_count=image_count,
                video_count=video_count,
                styles=styles,
                audience=audience,
                objective=objective,
                brand_style=brand_style,
                mix=mix,
                avatar=avatar,
                job_id=job.id,
            )
            job.strategy_id = strategy.id
            self.db.commit()

            image_provider = OpenAIImageProvider(self.client, self.assets)
            video_provider = UnconfiguredVideoProvider()

            for concept, brief_model in paired:
                kind = (concept.type or "IMAGE").upper()
                job.progress_message = (
                    f"Rendering {'video poster' if kind == 'VIDEO' else 'image'}: {concept.concept_name}"
                )
                self.db.commit()
                asset = CreativeAsset(
                    store_id=self.store.id,
                    product_id=product.product_id,
                    concept_id=concept.id,
                    job_id=job.id,
                    source_strategy_id=strategy.id,
                    source_creative_ids_json=concept.source_creative_ids_json,
                    source_product_id=product.product_id,
                    type="VIDEO" if kind == "VIDEO" else "IMAGE",
                    status="GENERATING",
                    hook=concept.hook,
                    headline=concept.headline,
                    primary_text=concept.primary_text,
                    cta=concept.cta,
                    visual_direction=concept.visual_direction,
                    rationale=concept.rationale,
                    aspect_ratio="9:16" if kind == "VIDEO" else aspect,
                    placement=placement,
                )
                self.db.add(asset)
                self.db.commit()
                try:
                    if kind == "VIDEO":
                        spec = video_spec_from_concept(brief_model, product, aspect_ratio="9:16")
                        provider_result = await video_provider.generate_video(spec.model_dump())
                        asset.video_spec_json = json.dumps(
                            {"spec": spec.model_dump(), "provider": provider_result}
                        )
                        await self._attach_video_poster(asset, product, spec, image_provider)
                        has_media = bool(asset.preview_url)
                    else:
                        prompt = build_image_prompt(
                            product=product,
                            visual_direction=concept.visual_direction,
                            image_prompt=getattr(brief_model, "image_prompt", "") or "",
                            brand_style=brand_style,
                            winning_notes=winning_notes,
                            aspect_ratio=aspect,
                            placement=placement,
                        )
                        result = await image_provider.generate(
                            ImageGenerationRequest(
                                prompt=prompt,
                                aspect_ratio=aspect,
                                placement=placement,
                            )
                        )
                        asset.local_path = result.local_path
                        asset.preview_url = result.preview_url
                        asset.width = result.width
                        asset.height = result.height
                        has_media = bool(result.preview_url)
                        if not has_media:
                            raise ImageGenerationError("Image generation returned no file")
                    score = heuristic_score(
                        has_media=has_media,
                        hook=concept.hook or "",
                        headline=concept.headline or "",
                        primary_text=concept.primary_text or "",
                        visual=concept.visual_direction or "",
                        winning_notes=winning_notes,
                        portfolio_bucket=concept.portfolio_bucket or "",
                        product_title=product.title,
                    )
                    asset.ai_score = float(score.total)
                    asset.score_breakdown_json = score.breakdown.model_dump_json()
                    if kind == "IMAGE" and not has_media:
                        raise ImageGenerationError("Complete image creative requires a generated file")
                    asset.status = "READY"
                    concept.status = "READY"
                    job.completed_items += 1
                except ImageGenerationError as exc:
                    asset.status = "FAILED"
                    asset.failure_reason = exc.message
                    concept.status = "FAILED"
                    job.failed_items += 1
                except Exception as exc:
                    asset.status = "FAILED"
                    asset.failure_reason = str(exc)[:500]
                    concept.status = "FAILED"
                    job.failed_items += 1
                self.db.commit()

            if job.failed_items and job.completed_items:
                job.status = "PARTIAL"
            elif job.failed_items and not job.completed_items:
                job.status = "FAILED"
                job.error_message = "All creatives failed"
            else:
                job.status = "COMPLETED"
            job.progress_message = "Done"
            job.finished_at = datetime.now(UTC)
            self.db.commit()
        except Exception as exc:
            logger.exception("ai_ads generation job failed store_id=%s job=%s", self.store.id, job.id)
            job.status = "FAILED"
            job.error_message = str(exc)[:800]
            job.progress_message = "Failed"
            job.finished_at = datetime.now(UTC)
            self.db.commit()

    async def _attach_video_poster(
        self,
        asset: CreativeAsset,
        product: ProductContext,
        spec: VideoSpec,
        image_provider: OpenAIImageProvider,
    ) -> None:
        """Save a still frame so Library can preview video concepts (no rendered MP4)."""
        first = spec.scenes[0] if spec.scenes else None
        visual = (first.visual if first else "") or spec.hook or product.title
        prompt = build_image_prompt(
            product=product,
            visual_direction=visual,
            image_prompt=visual,
            aspect_ratio="9:16",
            placement="stories",
        )
        try:
            result = await image_provider.generate(
                ImageGenerationRequest(prompt=prompt, aspect_ratio="9:16", placement="stories")
            )
            asset.local_path = result.local_path
            asset.preview_url = result.preview_url
            asset.width = result.width
            asset.height = result.height
        except Exception as exc:
            logger.info("ai_ads video poster skipped store_id=%s err=%s", self.store.id, exc)
