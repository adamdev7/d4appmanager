from __future__ import annotations

from app.db.models import CreativeConcept
from app.services.ai_ads.complete_creative import build_image_prompt
from app.services.ai_ads.copy_generator import CopyGenerator
from app.services.ai_ads.exceptions import ImageGenerationError
from app.services.ai_ads.providers.image_provider import ImageGenerationProvider
from app.services.ai_ads.schemas import ImageGenerationRequest, ImageGenerationResult, ProductContext


class ImageAdGenerator:
    def __init__(self, provider: ImageGenerationProvider, copy: CopyGenerator | None = None) -> None:
        self.provider = provider
        self.copy = copy

    async def generate(
        self,
        *,
        product: ProductContext,
        concept: CreativeConcept,
        aspect_ratio: str,
        placement: str,
        brand_style: str = "",
        winning_notes: str = "",
        image_prompt: str = "",
    ) -> ImageGenerationResult:
        prompt = build_image_prompt(
            product=product,
            visual_direction=concept.visual_direction,
            image_prompt=image_prompt,
            brand_style=brand_style,
            winning_notes=winning_notes,
            aspect_ratio=aspect_ratio,
            placement=placement,
        )
        try:
            return await self.provider.generate(
                ImageGenerationRequest(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    placement=placement,
                )
            )
        except ImageGenerationError:
            raise
        except Exception as exc:
            raise ImageGenerationError(str(exc), retryable=True) from exc
