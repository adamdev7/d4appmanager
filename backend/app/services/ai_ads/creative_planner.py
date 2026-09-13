from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AIAdStrategy, BrandAvatar, CreativeConcept, MetaCreative
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import CREATIVE_CONCEPT, GENERATION_PLAN
from app.services.ai_ads.schemas import (
    ConceptBatch,
    CreativeConceptModel,
    CreativeIntelligenceReport,
    CreativeStrategyModel,
    GenerationPlan,
    ProductContext,
)

logger = logging.getLogger(__name__)

DEFAULT_MIX = {
    "winner_variation": 0.4,
    "combination": 0.3,
    "exploration": 0.2,
    "experimental": 0.1,
}


def allocate_portfolio(
    n: int,
    mix: dict[str, float] | None = None,
) -> list[str]:
    weights = mix or DEFAULT_MIX
    keys = ["winner_variation", "combination", "exploration", "experimental"]
    raw = [max(0.0, float(weights.get(k, DEFAULT_MIX[k]))) for k in keys]
    total = sum(raw) or 1.0
    raw = [x / total for x in raw]
    counts = [int(n * x) for x in raw]
    while sum(counts) < n:
        remainders = [(i, raw[i] * n - counts[i]) for i in range(4)]
        remainders.sort(key=lambda x: x[1], reverse=True)
        counts[remainders[0][0]] += 1
    while sum(counts) > n:
        i = max(range(4), key=lambda i: counts[i])
        counts[i] -= 1
    buckets: list[str] = []
    for k, c in zip(keys, counts):
        buckets.extend([k] * c)
    return buckets[:n]


class CreativePlanner:
    def __init__(self, client: AdsOpenAIClient, store_id: str) -> None:
        self.client = client
        self.store_id = store_id
        self.model = settings.resolved_ai_creative_model

    async def generate_concepts(
        self,
        db: Session,
        *,
        product: ProductContext,
        strategy: AIAdStrategy,
        report: CreativeIntelligenceReport,
        meta_creatives: list[MetaCreative],
        count: int,
        media_type: str,
        styles: list[str],
        audience: str,
        objective: str,
        mix: dict[str, float] | None = None,
        avatar: BrandAvatar | None = None,
        job_id: str | None = None,
        user_id: str | None = None,
    ) -> list[CreativeConcept]:
        buckets = allocate_portfolio(count, mix)
        refs = [_creative_ref(c) for c in meta_creatives[:12]]
        payload: dict[str, Any] = {
            "product": product.model_dump(),
            "strategy": json.loads(strategy.strategy_json or "{}"),
            "intelligence": report.model_dump(),
            "existing_creatives": refs,
            "requested_count": count,
            "media_type": media_type,
            "styles": styles,
            "audience": audience,
            "objective": objective,
            "portfolio_buckets": buckets,
            "avatar": None,
        }
        if avatar and avatar.active:
            payload["avatar"] = {
                "name": avatar.name,
                "description": avatar.description,
                "usage_rules": avatar.usage_rules,
            }
        user = (
            "Generate exactly the requested number of DISTINCT concepts. "
            "Assign each concept.portfolio_bucket from the provided list in order. "
            f"media_type={media_type}.\n\n{json.dumps(payload, default=str)[:18000]}"
        )
        try:
            batch = await self.client.complete_json(
                system=CREATIVE_CONCEPT,
                user=user,
                schema=ConceptBatch,
                model=self.model,
                temperature=0.7,
                operation="creative_concepts",
            )
            assert isinstance(batch, ConceptBatch)
            models = batch.concepts[:count]
        except (InvalidAIOutput, Exception) as exc:
            logger.warning("ai_ads concepts failed store_id=%s err=%s", self.store_id, exc)
            models = []

        while len(models) < count:
            i = len(models)
            bucket = buckets[i] if i < len(buckets) else "exploration"
            models.append(
                ConceptBatch.model_validate(
                    {
                        "concepts": [
                            {
                                "type": media_type,
                                "concept_name": f"{product.title} {bucket.replace('_', ' ')} {i + 1}",
                                "angle": bucket,
                                "hook": product.title,
                                "headline": product.title,
                                "primary_text": (product.description or product.title)[:200],
                                "cta": "SHOP_NOW",
                                "visual_direction": "Show the actual product clearly.",
                                "audience": audience,
                                "objective": objective,
                                "rationale": "Fallback concept after AI validation failure.",
                                "source_creative_ids": report.winning_creatives[:2],
                                "expected_strength": "unknown",
                                "portfolio_bucket": bucket,
                            }
                        ]
                    }
                ).concepts[0]
            )

        rows: list[CreativeConcept] = []
        for i, concept in enumerate(models[:count]):
            bucket = buckets[i] if i < len(buckets) else concept.portfolio_bucket
            row = CreativeConcept(
                store_id=self.store_id,
                user_id=user_id,
                product_id=product.product_id,
                job_id=job_id,
                type=concept.type or media_type,
                concept_name=concept.concept_name,
                angle=concept.angle,
                hook=concept.hook,
                headline=concept.headline,
                primary_text=concept.primary_text,
                cta=concept.cta,
                visual_direction=concept.visual_direction,
                audience=concept.audience or audience,
                objective=concept.objective or objective,
                rationale=concept.rationale,
                source_strategy_id=strategy.id,
                source_creative_ids_json=json.dumps(concept.source_creative_ids or []),
                expected_strength=concept.expected_strength,
                portfolio_bucket=bucket,
                status="DRAFT",
            )
            db.add(row)
            rows.append(row)
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows

    async def plan_complete(
        self,
        db: Session,
        *,
        product: ProductContext,
        brief: dict[str, Any],
        image_count: int,
        video_count: int,
        styles: list[str],
        audience: str,
        objective: str,
        brand_style: str,
        mix: dict[str, float] | None = None,
        avatar: BrandAvatar | None = None,
        job_id: str | None = None,
        user_id: str | None = None,
    ) -> tuple[AIAdStrategy, list[tuple[CreativeConcept, Any]]]:
        """One model call: strategy + complete image and video ads."""
        from app.services.ai_ads.complete_creative import compact_product

        total = image_count + video_count
        image_buckets = allocate_portfolio(image_count, mix)
        video_buckets = allocate_portfolio(video_count, mix)
        payload: dict[str, Any] = {
            "product": compact_product(product),
            "winning_meta_ads": brief.get("winning") or [],
            "losing_meta_ads": brief.get("losing") or [],
            "insufficient_performance_split": bool(brief.get("insufficient")),
            "image_count": image_count,
            "video_count": video_count,
            "image_portfolio_buckets": image_buckets,
            "video_portfolio_buckets": video_buckets,
            "styles": styles,
            "audience": audience or None,
            "objective": objective,
            "brand_style": brand_style or None,
            "avatar": None,
        }
        if avatar and avatar.active:
            payload["avatar"] = {
                "name": avatar.name,
                "description": avatar.description,
                "usage_rules": avatar.usage_rules,
            }
        user = (
            f"Return {image_count} IMAGE and {video_count} VIDEO complete ads. "
            "Improve styles associated with stronger Meta ads. "
            f"Assign IMAGE portfolio_bucket from image_portfolio_buckets in order, VIDEO from video_portfolio_buckets.\n\n"
            f"{json.dumps(payload, default=str)[:12000]}"
        )
        try:
            plan = await self.client.complete_json(
                system=GENERATION_PLAN,
                user=user,
                schema=GenerationPlan,
                model=self.model,
                operation="generation_plan",
            )
            assert isinstance(plan, GenerationPlan)
            strategy_model = plan.strategy
            models = list(plan.concepts)
        except (InvalidAIOutput, Exception) as exc:
            logger.warning("ai_ads generation plan failed store_id=%s err=%s", self.store_id, exc)
            strategy_model = CreativeStrategyModel(
                summary="Use observed winning Meta patterns; generation plan fallback.",
                target_audience=audience,
                winning_patterns=[
                    str(w.get("style") or w.get("headline") or "")
                    for w in (brief.get("winning") or [])[:4]
                    if w.get("style") or w.get("headline")
                ],
                avoid=["Copy weaker ads that spent with weak CTR/ROAS"],
                confidence=0.2,
            )
            models = []

        images = [c for c in models if (c.type or "IMAGE").upper() != "VIDEO"][:image_count]
        videos = [c for c in models if (c.type or "").upper() == "VIDEO"][:video_count]
        while len(images) < image_count:
            i = len(images)
            bucket = image_buckets[i] if i < len(image_buckets) else "exploration"
            images.append(_fallback_concept(product, "IMAGE", bucket, audience, objective, brief, i))
        while len(videos) < video_count:
            i = len(videos)
            bucket = video_buckets[i] if i < len(video_buckets) else "exploration"
            videos.append(_fallback_concept(product, "VIDEO", bucket, audience, objective, brief, i))
        for i, concept in enumerate(images):
            concept.type = "IMAGE"
            if i < len(image_buckets):
                concept.portfolio_bucket = image_buckets[i]
        for i, concept in enumerate(videos):
            concept.type = "VIDEO"
            if i < len(video_buckets):
                concept.portfolio_bucket = video_buckets[i]

        strategy_row = AIAdStrategy(
            store_id=self.store_id,
            product_id=product.product_id,
            summary=strategy_model.summary or "Improve winning Meta creative styles for this product.",
            target_audience=strategy_model.target_audience or audience,
            strategy_json=strategy_model.model_dump_json(),
            intelligence_report_json=json.dumps(
                {
                    "winning_creatives": brief.get("winning_ids") or [],
                    "losing_creatives": brief.get("losing_ids") or [],
                    "insufficient": brief.get("insufficient"),
                }
            ),
            confidence=strategy_model.confidence,
            model_used=self.model,
        )
        db.add(strategy_row)
        db.commit()
        db.refresh(strategy_row)

        paired: list[tuple[CreativeConcept, Any]] = []
        for concept in images + videos:
            row = CreativeConcept(
                store_id=self.store_id,
                user_id=user_id,
                product_id=product.product_id,
                job_id=job_id,
                type=concept.type or "IMAGE",
                concept_name=concept.concept_name,
                angle=concept.angle,
                hook=concept.hook,
                headline=concept.headline,
                primary_text=concept.primary_text,
                cta=concept.cta,
                visual_direction=concept.visual_direction or concept.image_prompt,
                audience=concept.audience or audience,
                objective=concept.objective or objective,
                rationale=concept.rationale,
                source_strategy_id=strategy_row.id,
                source_creative_ids_json=json.dumps(concept.source_creative_ids or []),
                expected_strength=concept.expected_strength,
                portfolio_bucket=concept.portfolio_bucket,
                status="DRAFT",
            )
            db.add(row)
            paired.append((row, concept))
        db.commit()
        for row, _ in paired:
            db.refresh(row)
        if total:
            logger.info(
                "ai_ads plan_complete store_id=%s images=%s videos=%s",
                self.store_id,
                image_count,
                video_count,
            )
        return strategy_row, paired


def _fallback_concept(
    product: ProductContext,
    media_type: str,
    bucket: str,
    audience: str,
    objective: str,
    brief: dict[str, Any],
    index: int,
) -> Any:
    winners = brief.get("winning_ids") or []
    return CreativeConceptModel(
        type=media_type,
        concept_name=f"{product.title} {bucket.replace('_', ' ')} {index + 1}",
        angle=bucket,
        hook=product.title,
        headline=product.title,
        primary_text=(product.description or product.title)[:200],
        cta="SHOP_NOW",
        visual_direction=f"Show the actual product clearly: {product.title}.",
        image_prompt=f"Photorealistic advertising photo of {product.title}, product hero, clean background.",
        audience=audience,
        objective=objective,
        rationale="Fallback complete concept after AI validation failure.",
        source_creative_ids=winners[:2],
        expected_strength="unknown",
        portfolio_bucket=bucket,
    )


def _creative_ref(c: MetaCreative) -> dict[str, Any]:
    return {
        "id": c.id,
        "ad_name": c.ad_name,
        "format": c.format,
        "headline": c.headline,
        "primary_text": (c.primary_text or "")[:400],
        "cta": c.cta,
        "has_image": bool(c.local_asset_path or c.image_url),
    }
