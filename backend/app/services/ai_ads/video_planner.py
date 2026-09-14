from __future__ import annotations

import json

from app.config import settings
from app.db.models import BrandAvatar, CreativeConcept
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.prompts import VIDEO_SCRIPT
from app.services.ai_ads.providers.video_provider import VideoGenerationProvider
from app.services.ai_ads.complete_creative import DEFAULT_MUSIC, DEFAULT_VOICE
from app.services.ai_ads.schemas import ProductContext, VideoSpec


class VideoCreativePlanner:
    def __init__(self, client: AdsOpenAIClient, provider: VideoGenerationProvider) -> None:
        self.client = client
        self.provider = provider
        self.model = settings.resolved_ai_creative_model

    async def plan(
        self,
        *,
        product: ProductContext,
        concept: CreativeConcept,
        aspect_ratio: str = "9:16",
        avatar: BrandAvatar | None = None,
    ) -> VideoSpec:
        payload = {
            "product": product.model_dump(),
            "concept": {
                "name": concept.concept_name,
                "hook": concept.hook,
                "headline": concept.headline,
                "primary_text": concept.primary_text,
                "cta": concept.cta,
                "visual_direction": concept.visual_direction,
                "type": concept.type,
            },
            "format": aspect_ratio,
            "avatar": None,
        }
        if avatar and avatar.active:
            payload["avatar"] = {
                "name": avatar.name,
                "description": avatar.description,
                "usage_rules": avatar.usage_rules,
            }
        try:
            spec = await self.client.complete_json(
                system=VIDEO_SCRIPT,
                user=json.dumps(payload, default=str)[:8000],
                schema=VideoSpec,
                model=self.model,
                operation="video_script",
            )
            assert isinstance(spec, VideoSpec)
            spec.format = spec.format or aspect_ratio
            return spec
        except (InvalidAIOutput, Exception):
            return VideoSpec(
                duration=8,
                format=aspect_ratio,
                hook=concept.hook or product.title,
                scenes=[
                    {
                        "duration": 2,
                        "visual": f"Open on the product: {product.title}. No text.",
                        "voiceover": "",
                        "text_overlay": "",
                    },
                    {
                        "duration": 4,
                        "visual": concept.visual_direction or "Demonstrate the product in use. No captions.",
                        "voiceover": "",
                        "text_overlay": "",
                    },
                    {
                        "duration": 2,
                        "visual": "Clean product hold. No call-to-action text.",
                        "voiceover": "",
                        "text_overlay": "",
                    },
                ],
                voice_direction=DEFAULT_VOICE,
                music_direction=DEFAULT_MUSIC,
                cta=concept.cta or "SHOP_NOW",
            )

    async def maybe_generate(self, spec: VideoSpec) -> dict:
        return await self.provider.generate_video(spec.model_dump())
