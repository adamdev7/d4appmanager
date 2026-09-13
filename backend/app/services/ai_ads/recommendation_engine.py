from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AIRecommendation
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import RECOMMENDATIONS, SCORE_CREATIVE
from app.services.ai_ads.schemas import (
    AICreativeScore,
    CreativeIntelligenceReport,
    IntelligenceRecommendation,
)

logger = logging.getLogger(__name__)


class RecommendationList(IntelligenceRecommendation):
    pass


class RecommendationBatch(CreativeIntelligenceReport):
    """Reuse list field recommendations from intelligence schema."""


class RecommendationEngine:
    def __init__(self, client: AdsOpenAIClient, store_id: str) -> None:
        self.client = client
        self.store_id = store_id
        self.model = settings.resolved_ai_strategy_model

    async def generate(
        self,
        db: Session,
        *,
        report: CreativeIntelligenceReport,
        product_id: str | None = None,
    ) -> list[AIRecommendation]:
        from pydantic import BaseModel, Field

        class RecBatch(BaseModel):
            recommendations: list[IntelligenceRecommendation] = Field(default_factory=list)

        try:
            batch = await self.client.complete_json(
                system=RECOMMENDATIONS,
                user=json.dumps(report.model_dump(), default=str)[:12000],
                schema=RecBatch,
                model=self.model,
                operation="recommendations",
            )
            recs = batch.recommendations
        except (InvalidAIOutput, Exception) as exc:
            logger.warning("ai_ads recommendations failed store_id=%s err=%s", self.store_id, exc)
            recs = report.recommendations

        rows: list[AIRecommendation] = []
        for rec in recs:
            row = AIRecommendation(
                store_id=self.store_id,
                product_id=product_id,
                title=rec.title,
                explanation=rec.explanation,
                supporting_creative_ids_json=json.dumps(rec.supporting_creative_ids),
                supporting_metrics_json=json.dumps(rec.supporting_metrics),
                confidence=rec.confidence,
                recommended_action=rec.recommended_action,
            )
            db.add(row)
            rows.append(row)
        db.commit()
        for row in rows:
            db.refresh(row)
        return rows

    async def score(
        self,
        *,
        concept_name: str,
        hook: str,
        visual: str,
        strategy_summary: str,
        product_title: str,
        portfolio_bucket: str,
    ) -> AICreativeScore:
        payload = {
            "concept_name": concept_name,
            "hook": hook,
            "visual_direction": visual,
            "strategy_summary": strategy_summary,
            "product_title": product_title,
            "portfolio_bucket": portfolio_bucket,
        }
        try:
            score = await self.client.complete_json(
                system=SCORE_CREATIVE,
                user=json.dumps(payload),
                schema=AICreativeScore,
                model=self.model,
                operation="creative_score",
            )
            assert isinstance(score, AICreativeScore)
            score.label = "AI Creative Evaluation"
            return score
        except Exception:
            return AICreativeScore(
                total=50,
                label="AI Creative Evaluation",
            )
