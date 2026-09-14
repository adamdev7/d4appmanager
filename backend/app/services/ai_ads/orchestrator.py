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
    build_video_prompt,
    resolve_generation_counts,
    compact_product,
    format_appearance_lock,
    heuristic_score,
    product_appearance_notes,
    product_reference_urls,
    video_spec_from_concept,
    winning_style_notes,
)
from app.services.ai_ads.exceptions import (
    AIAdsError,
    GenerationCancelled,
    ImageGenerationError,
    VideoProviderError,
)
from app.services.ai_ads.creative_intelligence import CreativeIntelligenceAnalyzer
from app.services.ai_ads.creative_planner import CreativePlanner
from app.services.ai_ads.job_progress import append_job_progress
from app.services.ai_ads.meta_importer import MetaCreativeImporter
from app.services.ai_ads.media_io import fetch_product_images, prepare_video_still
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.product_context import normalize_product
from app.services.ai_ads.prompts import PRODUCT_APPEARANCE
from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
from app.services.ai_ads.providers.openai_video import OpenAIVideoProvider, resolve_video_size
from app.services.ai_ads.recommendation_engine import RecommendationEngine
from app.services.ai_ads.schemas import (
    CreativeIntelligenceReport,
    ImageGenerationRequest,
    ProductAppearanceLock,
    ProductContext,
)
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
                await analyzer.analyze_one(self.db, c, perf.get(c.id), force=True)
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
        self._raise_if_cancelled(job)
        job.status = "RUNNING"
        job.started_at = datetime.now(UTC)
        self._progress(
            job,
            step="product",
            title="Loading product from Shopify",
            detail="Reading title, description, and product photos so ads stay factually accurate.",
            pct=8,
        )
        try:
            request = json.loads(job.request_json or "{}")
            product = await self.load_product(job.product_id or request.get("product_id"))
            image_count, video_count = resolve_generation_counts(
                request.get("image_count"),
                request.get("video_count"),
                default_images=settings.ai_ad_image_count,
                default_videos=settings.ai_ad_video_count,
            )
            if image_count + video_count < 1:
                raise AIAdsError("No images or videos were requested.")
            styles = list(request.get("styles") or ["UGC", "PRODUCT_DEMO", "LIFESTYLE"])
            audience = str(request.get("audience") or "")
            objective = str(request.get("objective") or "conversions")
            placement = str(request.get("placement") or "feed")
            aspect = str(request.get("aspect_ratio") or "4:5")
            brand_style = str(request.get("brand_style") or "")
            avatar_id = request.get("avatar_id")
            mix = request.get("portfolio_mix")

            job.total_items = image_count + video_count
            self._progress(
                job,
                step="product",
                title="Locking the real product look",
                detail=f"Studying Shopify photos of {product.title} so generated ads show this SKU, not a stand-in.",
                pct=12,
            )
            appearance_lock = await self._lock_product_appearance(product)
            catalog_urls = product_reference_urls(product)
            product_refs = await fetch_product_images(catalog_urls, limit=4)
            if catalog_urls and not product_refs:
                raise AIAdsError(
                    f"Could not download Shopify photos for {product.title}. "
                    "Stopped so Astra does not invent a different product."
                )
            if not product_refs:
                raise AIAdsError(
                    f"{product.title} has no Shopify photos. Add product images, then generate again."
                )
            self._progress(
                job,
                step="product",
                title="Product look locked",
                detail=(
                    f"Loaded {len(product_refs)} real photo(s) of {product.title}. "
                    f"Ads must show this exact item: {appearance_lock[:180] or product.title}."
                ),
                pct=14,
            )

            self._progress(
                job,
                step="learn",
                title="Analyzing Meta campaign performance",
                detail="Ranking existing ads by ROAS and CTR, then looking at the actual creatives to see how the offer is shown.",
                pct=18,
            )

            meta_count = (
                self.db.scalar(
                    select(MetaCreative.id).where(MetaCreative.store_id == self.store.id).limit(1)
                )
                is not None
            )
            if not meta_count:
                self._progress(
                    job,
                    step="sync",
                    title="Syncing Meta ads",
                    detail="No imported creatives yet. Downloading campaign ads so the engine has winners to learn from.",
                    pct=22,
                )
                try:
                    await self.sync_meta()
                except Exception as exc:
                    logger.warning("ai_ads job sync skipped store_id=%s err=%s", self.store.id, exc)
                    self._progress(
                        job,
                        step="sync",
                        title="Meta sync skipped",
                        detail=f"Continuing with whatever is already imported. ({str(exc)[:160]})",
                        pct=24,
                    )

            analyzer = CreativeIntelligenceAnalyzer(self.client, self.store.id)
            listed = analyzer.listed_creatives(self.db, limit=80)
            missing = analyzer.creatives_missing_dna(listed, limit=8)
            perf = analyzer.latest_performance_map(self.db)
            if missing:
                self._progress(
                    job,
                    step="learn",
                    title="Looking at winning Meta ads",
                    detail=f"Reading {len(missing)} ad image(s) to see how the offer is framed — product, setting, camera — not just the copy.",
                    pct=26,
                )
                for creative in missing:
                    self._raise_if_cancelled(job)
                    try:
                        await analyzer.analyze_one(self.db, creative, perf.get(creative.id), force=True)
                    except Exception as exc:
                        logger.warning(
                            "ai_ads job dna skipped store_id=%s id=%s err=%s",
                            self.store.id,
                            creative.id,
                            exc,
                        )
            brief = analyzer.campaign_brief(self.db)
            brief["winning_images"] = analyzer.winning_preview_images(self.db, limit=2)
            winning_notes = winning_style_notes(brief.get("winning") or [])
            winning_motion = winning_style_notes(brief.get("winning") or [], sku_safe=True)
            winners = brief.get("winning") or []
            losers = brief.get("losing") or []
            learn_detail = (
                f"Found {len(winners)} stronger ads and {len(losers)} weaker ads. "
                + (
                    f"Offer look associated with stronger ads: {winning_notes[:220]}."
                    if winning_notes
                    else "Not enough spend/ROAS split yet — using product photos and your selected styles."
                )
            )
            self._progress(job, step="learn", title="Learning from winning Meta ads", detail=learn_detail, pct=32)

            avatar = None
            if avatar_id:
                avatar = self.db.get(BrandAvatar, avatar_id)
                if avatar and avatar.store_id != self.store.id:
                    avatar = None

            self._progress(
                job,
                step="plan",
                title="Planning brand-new creatives",
                detail=(
                    f"Drafting {image_count} distinct image scene(s) and {video_count} distinct video storyboard(s) "
                    f"in styles {', '.join(styles) or 'default'} that feature the real {product.title} in brand-new situations."
                ),
                pct=42,
            )
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
                user_id=self.user.id,
            )
            job.strategy_id = strategy.id
            self._progress(
                job,
                step="plan",
                title="Creative plan is ready",
                detail=(strategy.summary or "Concepts drafted.")[:280],
                pct=52,
            )

            image_provider = OpenAIImageProvider(self.client, self.assets)
            video_provider = OpenAIVideoProvider(self.client, self.assets)
            total = max(len(paired), 1)
            image_total = sum(1 for c, _ in paired if (c.type or "IMAGE").upper() != "VIDEO")
            video_total = sum(1 for c, _ in paired if (c.type or "").upper() == "VIDEO")
            image_n = 0
            video_n = 0

            for index, (concept, brief_model) in enumerate(paired):
                self._raise_if_cancelled(job)
                kind = (concept.type or "IMAGE").upper()
                if kind == "VIDEO" and video_count <= 0:
                    continue
                if kind != "VIDEO" and image_count <= 0:
                    continue
                base = 55
                span = 40
                pct = base + int((index / total) * span)
                if kind == "VIDEO":
                    video_slot = video_n
                    video_n += 1
                    self._progress(
                        job,
                        step="video",
                        title=f"Astra rendering video {video_slot + 1} of {max(video_total, 1)}",
                        detail=(
                            f"Astra is animating a real MP4 of your {product.title} "
                            f"for “{concept.concept_name or concept.hook}”."
                        ),
                        pct=pct,
                    )
                else:
                    image_slot = image_n
                    image_n += 1
                    self._progress(
                        job,
                        step="image",
                        title=f"Astra rendering image {image_slot + 1} of {max(image_total, 1)}",
                        detail=(
                            f"Astra is placing your real {product.title} into a new still for "
                            f"“{concept.concept_name or concept.hook}”."
                        ),
                        pct=pct,
                    )
                asset = CreativeAsset(
                    store_id=self.store.id,
                    user_id=self.user.id,
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
                        prompt = build_video_prompt(
                            product=product,
                            spec=spec,
                            brand_style=brand_style,
                            winning_notes=winning_motion,
                            variation_index=video_slot,
                            variation_count=max(video_total, 1),
                            styles=styles,
                        )
                        payload = spec.model_dump()
                        payload["prompt"] = prompt
                        # Sora uses input_reference as the first frame. Letterbox the real
                        # Shopify photo so the whole SKU stays visible at 720x1280.
                        _, video_w, video_h = resolve_video_size("9:16")
                        if not product_refs:
                            raise VideoProviderError(
                                f"No Shopify photo of {product.title} to lock into the video."
                            )
                        try:
                            identity_still = prepare_video_still(product_refs, video_w, video_h)
                        except Exception as exc:
                            logger.warning(
                                "ai_ads video still failed store_id=%s err=%s",
                                self.store.id,
                                str(exc)[:300],
                            )
                            raise VideoProviderError(
                                f"Could not prepare the {product.title} photo for video."
                            ) from exc
                        payload["input_reference"] = identity_still
                        poster = self.assets.save_bytes(
                            identity_still[0],
                            mime_type=identity_still[1],
                            prefix="poster",
                        )
                        asset.preview_url = poster["public_url"]
                        rendered = await video_provider.generate_video(
                            payload,
                            cancel_check=lambda: self._raise_if_cancelled(job),
                        )
                        mp4_path = str(rendered.get("local_path") or "")
                        if not mp4_path.lower().endswith(".mp4"):
                            raise VideoProviderError("Video render did not produce an MP4")
                        asset.local_path = mp4_path
                        asset.width = rendered.get("width") or 720
                        asset.height = rendered.get("height") or 1280
                        asset.video_spec_json = json.dumps(
                            {"spec": spec.model_dump(), "provider": {k: v for k, v in rendered.items() if k != "input_reference"}, "rendered": True}
                        )
                        has_media = True
                    else:
                        prompt = build_image_prompt(
                            product=product,
                            visual_direction=concept.visual_direction,
                            image_prompt=getattr(brief_model, "image_prompt", "") or "",
                            brand_style=brand_style,
                            winning_notes=winning_notes,
                            aspect_ratio=aspect,
                            placement=placement,
                            variation_index=image_slot,
                            variation_count=max(image_total, 1),
                            styles=styles,
                        )
                        result = await image_provider.generate(
                            ImageGenerationRequest(
                                prompt=prompt,
                                aspect_ratio=aspect,
                                placement=placement,
                            ),
                            identity_images=product_refs,
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
                    if not has_media:
                        raise ImageGenerationError(
                            "Complete creative requires a rendered image or MP4 — text-only concepts are not saved as ready ads."
                        )
                    asset.status = "READY"
                    concept.status = "READY"
                    job.completed_items += 1
                    done_pct = 55 + int(((index + 1) / total) * 40)
                    self._progress(
                        job,
                        step="image" if kind != "VIDEO" else "video",
                        title=f"Finished {concept.concept_name or kind.lower()}",
                        detail=f"{job.completed_items} of {job.total_items} creatives ready.",
                        pct=done_pct,
                    )
                except GenerationCancelled:
                    raise
                except (ImageGenerationError, VideoProviderError) as exc:
                    asset.status = "FAILED"
                    asset.failure_reason = exc.message
                    concept.status = "FAILED"
                    job.failed_items += 1
                    self._progress(
                        job,
                        step="error",
                        title=f"Could not finish {concept.concept_name or kind.lower()}",
                        detail=exc.message[:280],
                        pct=job.progress_pct or pct,
                    )
                except Exception as exc:
                    asset.status = "FAILED"
                    asset.failure_reason = str(exc)[:500]
                    concept.status = "FAILED"
                    job.failed_items += 1
                    self._progress(
                        job,
                        step="error",
                        title=f"Could not finish {concept.concept_name or kind.lower()}",
                        detail=str(exc)[:280],
                        pct=job.progress_pct or pct,
                    )
                self.db.commit()

            self._raise_if_cancelled(job)
            if job.failed_items and job.completed_items:
                job.status = "PARTIAL"
            elif job.failed_items and not job.completed_items:
                job.status = "FAILED"
                job.error_message = "All creatives failed"
            else:
                job.status = "COMPLETED"
            job.finished_at = datetime.now(UTC)
            self._progress(
                job,
                step="done" if job.status != "FAILED" else "error",
                title="Generation complete" if job.status != "FAILED" else "Generation failed",
                detail=(
                    f"{job.completed_items} ready"
                    + (f", {job.failed_items} failed" if job.failed_items else "")
                    + ". Open Library to review."
                ),
                pct=100 if job.status != "FAILED" else max(job.progress_pct or 0, 90),
            )
        except GenerationCancelled:
            return
        except Exception as exc:
            logger.exception("ai_ads generation job failed store_id=%s job=%s", self.store.id, job.id)
            job.status = "FAILED"
            job.error_message = str(exc)[:800]
            job.finished_at = datetime.now(UTC)
            self._progress(
                job,
                step="error",
                title="Generation stopped",
                detail=str(exc)[:280],
                pct=max(job.progress_pct or 0, 8),
            )

    def _raise_if_cancelled(self, job: CreativeGenerationJob) -> None:
        from app.services.ai_ads.job_runner import is_cancel_requested

        if not is_cancel_requested(job.id):
            return
        job.status = "CANCELLED"
        job.finished_at = datetime.now(UTC)
        job.error_message = "Stopped from the workplace console."
        append_job_progress(
            job,
            step="error",
            title="Generation halted",
            detail="Operator stopped this run. Ready creatives were kept.",
            pct=job.progress_pct or 0,
        )
        self.db.commit()
        raise GenerationCancelled(job.error_message)

    def _progress(
        self,
        job: CreativeGenerationJob,
        *,
        step: str,
        title: str,
        detail: str = "",
        pct: int | None = None,
    ) -> None:
        self._raise_if_cancelled(job)
        append_job_progress(job, step=step, title=title, detail=detail, pct=pct)
        self.db.commit()

    async def _lock_product_appearance(self, product: ProductContext) -> str:
        """Vision-lock the Shopify catalog photos so later renders cannot invent a different SKU."""
        fallback = product_appearance_notes(product)
        urls = product_reference_urls(product)
        text = fallback
        if urls:
            try:
                lock = await self.client.complete_json(
                    system=PRODUCT_APPEARANCE,
                    user=(
                        "Describe the exact product in the attached photos. "
                        "This lock must prevent an image model from generating a different bracelet or SKU.\n"
                        f"{json.dumps(compact_product(product), default=str)[:4000]}"
                    ),
                    schema=ProductAppearanceLock,
                    model=settings.resolved_ai_analysis_model,
                    images=[{"url": src} for src in urls[:3]],
                    operation="product_appearance",
                )
                text = format_appearance_lock(lock) or fallback
            except Exception as exc:
                logger.warning("ai_ads product appearance lock failed store_id=%s err=%s", self.store.id, exc)
                text = fallback
        product.brand_context = dict(product.brand_context or {})
        product.brand_context["appearance_lock"] = text
        return text

