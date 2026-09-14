from __future__ import annotations

import logging

import httpx

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

    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        size, width, height = resolve_image_size(self._model, request.aspect_ratio)
        if request.size:
            size = request.size
            try:
                w_s, h_s = size.lower().split("x", 1)
                width, height = int(w_s), int(h_s)
            except ValueError:
                pass
        references = await _download_references(request.reference_image_urls)
        try:
            raw, mime = await self._client.generate_image_b64(
                prompt=request.prompt,
                model=self._model,
                size=size,
                references=references or None,
            )
        except Exception as exc:
            fallback = "dall-e-3"
            if self._model == fallback:
                raise ImageGenerationError(str(exc), retryable=True) from exc
            logger.warning("ai_ads image model %s failed, retrying %s: %s", self._model, fallback, exc)
            size, width, height = resolve_image_size(fallback, request.aspect_ratio)
            try:
                raw, mime = await self._client.generate_image_b64(
                    prompt=request.prompt,
                    model=fallback,
                    size=size,
                    references=None,
                )
            except Exception as second:
                raise ImageGenerationError(str(second), retryable=True) from second
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


async def _download_references(urls: list[str] | None) -> list[tuple[bytes, str]]:
    out: list[tuple[bytes, str]] = []
    for url in (urls or [])[:1]:
        src = (url or "").strip()
        if not src.startswith("http"):
            continue
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                resp = await client.get(src)
                resp.raise_for_status()
            data = resp.content
            if not data or len(data) < 32:
                continue
            mime = (resp.headers.get("content-type") or "image/jpeg").split(";")[0].strip()
            if "image" not in mime:
                mime = "image/jpeg"
            out.append((data, mime))
        except Exception as exc:
            logger.info("ai_ads product reference download skipped url=%s err=%s", src[:120], exc)
    return out
