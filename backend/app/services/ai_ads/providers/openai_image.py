from __future__ import annotations

import logging

from app.config import settings
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.exceptions import ImageGenerationError
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.providers.image_provider import ImageGenerationProvider
from app.services.ai_ads.schemas import ImageGenerationRequest, ImageGenerationResult

logger = logging.getLogger(__name__)

# Standard sizes the GPT Image family always accepts.
_GPT_IMAGE_SIZES = {
    "1:1": ("1024x1024", 1024, 1024),
    "4:5": ("1024x1536", 1024, 1536),
    "9:16": ("1024x1536", 1024, 1536),
    "16:9": ("1536x1024", 1536, 1024),
}

_DALLE3_SIZES = {
    "1:1": ("1024x1024", 1024, 1024),
    "4:5": ("1024x1792", 1024, 1792),
    "9:16": ("1024x1792", 1024, 1792),
    "16:9": ("1792x1024", 1792, 1024),
}


def resolve_image_size(model: str, aspect_ratio: str | None) -> tuple[str, int, int]:
    key = (aspect_ratio or "4:5").strip()
    slug = (model or "").strip().lower()
    table = _DALLE3_SIZES if "dall-e-3" in slug else _GPT_IMAGE_SIZES
    return table.get(key, table["4:5"])


class OpenAIImageProvider(ImageGenerationProvider):
    def __init__(
        self,
        client: AdsOpenAIClient,
        store: CreativeAssetStore,
        *,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._model = model or settings.resolved_ai_image_model

    async def generate(
        self,
        request: ImageGenerationRequest,
        *,
        identity_images: list[tuple[bytes, str]] | None = None,
    ) -> ImageGenerationResult:
        size, width, height = resolve_image_size(self._model, request.aspect_ratio)
        if request.size:
            size = request.size
            try:
                w_s, h_s = size.lower().split("x", 1)
                width, height = int(w_s), int(h_s)
            except ValueError:
                pass
        references = list(identity_images or [])
        if not references:
            raise ImageGenerationError(
                "Shopify product photos could not be loaded. Stopped so we do not invent a different product."
            )
        try:
            raw, mime = await self._client.generate_image_b64(
                prompt=request.prompt,
                model=self._model,
                size=size,
                references=references,
            )
        except Exception as exc:
            raise ImageGenerationError(str(exc), retryable=True) from exc
        if not raw:
            raise ImageGenerationError("Image generation returned no file")
        saved = self._store.save_bytes(raw, mime_type=mime, prefix="gen")
        return ImageGenerationResult(
            status="completed",
            local_path=saved["relative_path"],
            preview_url=saved["public_url"],
            width=width,
            height=height,
            mime_type=mime,
        )
