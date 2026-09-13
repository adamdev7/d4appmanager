from __future__ import annotations

from app.db.models import CreativeConcept
from app.services.ai_ads.copy_generator import CopyGenerator
from app.services.ai_ads.exceptions import ImageGenerationError
from app.services.ai_ads.providers.image_provider import ImageGenerationProvider
from app.services.ai_ads.schemas import ImageGenerationRequest, ImageGenerationResult, ProductContext


class ImageAdGenerator:
    def __init__(self, provider: ImageGenerationProvider, copy: CopyGenerator) -> None:
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
    ) -> ImageGenerationResult:
        prompt = await self.copy.image_prompt(
            product=product,
            concept=concept,
            aspect_ratio=aspect_ratio,
            placement=placement,
            brand_style=brand_style,
            winning_notes=winning_notes,
        )
        refs = [img.src for img in product.images if img.src][:3]
        try:
            return await self.provider.generate(
                ImageGenerationRequest(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    placement=placement,
                    reference_image_urls=refs,
                )
            )
        except ImageGenerationError:
            raise
        except Exception as exc:
            raise ImageGenerationError(str(exc), retryable=True) from exc
