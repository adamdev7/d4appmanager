from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AIAdStrategy
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import CREATIVE_STRATEGY
from app.services.ai_ads.schemas import CreativeIntelligenceReport, CreativeStrategyModel, ProductContext

logger = logging.getLogger(__name__)


class CreativeStrategyEngine:
    def __init__(self, client: AdsOpenAIClient, store_id: str) -> None:
        self.client = client
        self.store_id = store_id
        self.model = settings.resolved_ai_strategy_model

    async def generate(
        self,
        db: Session,
        *,
        product: ProductContext,
        report: CreativeIntelligenceReport,
        brand_style: str = "",
        audience: str = "",
        objective: str = "conversions",
    ) -> AIAdStrategy:
        payload = {
            "product": product.model_dump(),
            "intelligence_report": report.model_dump(),
            "brand_style": brand_style or None,
            "requested_audience": audience or None,
            "objective": objective,
        }
        user = (
            "Create a CreativeStrategy grounded in this product + intelligence report. "
            "Do not invent product claims.\n\n"
            f"{json.dumps(payload, default=str)[:16000]}"
        )
        try:
            strategy = await self.client.complete_json(
                system=CREATIVE_STRATEGY,
                user=user,
                schema=CreativeStrategyModel,
                model=self.model,
                operation="creative_strategy",
            )
            assert isinstance(strategy, CreativeStrategyModel)
        except (InvalidAIOutput, Exception) as exc:
            logger.warning("ai_ads strategy failed store_id=%s err=%s", self.store_id, exc)
            strategy = CreativeStrategyModel(
                summary="Strategy generation failed; use observed winning patterns from the intelligence report.",
                target_audience=audience,
                winning_patterns=[p.statement for p in report.visual_patterns[:5]],
                hypotheses=report.hypotheses_to_test[:5],
                confidence=min(report.confidence, 0.3),
            )
        row = AIAdStrategy(
            store_id=self.store_id,
            product_id=product.product_id,
            summary=strategy.summary,
            target_audience=strategy.target_audience or audience,
            strategy_json=strategy.model_dump_json(),
            intelligence_report_json=report.model_dump_json(),
            confidence=strategy.confidence,
            model_used=self.model,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row
