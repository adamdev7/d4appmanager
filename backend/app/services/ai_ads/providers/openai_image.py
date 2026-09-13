from __future__ import annotations

from app.config import settings
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.exceptions import ImageGenerationError
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.providers.image_provider import ImageGenerationProvider
from app.services.ai_ads.schemas import ImageGenerationRequest, ImageGenerationResult

_ASPECT_SIZES = {
    "1:1": ("1024x1024", 1024, 1024),
    "4:5": ("1024x1536", 1024, 1280),
    "9:16": ("1024x1536", 1024, 1792),
    "16:9": ("1536x1024", 1792, 1024),
}


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

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        size_key = request.aspect_ratio or "4:5"
        size, width, height = _ASPECT_SIZES.get(size_key, _ASPECT_SIZES["4:5"])
        if request.size:
            size = request.size
        try:
            raw, mime = await self._client.generate_image_b64(
                prompt=request.prompt,
                model=self._model,
                size=size,
            )
        except Exception as exc:
            raise ImageGenerationError(str(exc), retryable=True) from exc
        saved = self._store.save_bytes(raw, mime_type=mime, prefix="gen")
        return ImageGenerationResult(
            status="completed",
            local_path=saved["relative_path"],
            preview_url=saved["public_url"],
            width=width,
            height=height,
            mime_type=mime,
        )
