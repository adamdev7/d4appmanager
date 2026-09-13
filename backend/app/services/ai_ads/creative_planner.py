from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AIAdStrategy, BrandAvatar, CreativeConcept, MetaCreative
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import CREATIVE_CONCEPT
from app.services.ai_ads.schemas import ConceptBatch, CreativeIntelligenceReport, ProductContext

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
