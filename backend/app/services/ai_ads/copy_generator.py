from __future__ import annotations

import json

from app.config import settings
from app.db.models import CreativeConcept
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import COPY_GENERATION, IMAGE_GENERATION
from app.services.ai_ads.schemas import ProductContext


class CopyGenerator:
    def __init__(self, client: AdsOpenAIClient) -> None:
        self.client = client
        self.model = settings.resolved_ai_creative_model

    async def image_prompt(
        self,
        *,
        product: ProductContext,
        concept: CreativeConcept,
        aspect_ratio: str,
        placement: str,
        brand_style: str,
        winning_notes: str,
    ) -> str:
        user = json.dumps(
            {
                "product": product.model_dump(),
                "concept": {
                    "name": concept.concept_name,
                    "angle": concept.angle,
                    "hook": concept.hook,
                    "visual_direction": concept.visual_direction,
                    "type": concept.type,
                },
                "aspect_ratio": aspect_ratio,
                "placement": placement,
                "brand_style": brand_style or None,
                "winning_notes": winning_notes or None,
            },
            default=str,
        )[:8000]
        return await self.client.complete_text(
            system=IMAGE_GENERATION,
            user=user,
            model=self.model,
            operation="image_prompt",
        )

    async def refine_copy(self, *, product: ProductContext, concept: CreativeConcept) -> dict[str, str]:
        from app.services.ai_ads.schemas import CreativeConceptModel

        user = json.dumps(
            {"product": product.model_dump(), "concept": concept.concept_name, "draft": {
                "hook": concept.hook,
                "headline": concept.headline,
                "primary_text": concept.primary_text,
                "cta": concept.cta,
            }},
            default=str,
        )[:6000]
        try:
            result = await self.client.complete_json(
                system=COPY_GENERATION,
                user=user,
                schema=CreativeConceptModel,
                model=self.model,
                operation="copy_generation",
            )
            return {
                "hook": result.hook or concept.hook,
                "headline": result.headline or concept.headline,
                "primary_text": result.primary_text or concept.primary_text,
                "cta": result.cta or concept.cta,
            }
        except Exception:
            return {
                "hook": concept.hook,
                "headline": concept.headline,
                "primary_text": concept.primary_text,
                "cta": concept.cta,
            }
