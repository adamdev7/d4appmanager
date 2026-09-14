from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.exceptions import VideoProviderError
from app.services.ai_ads.media_io import is_mp4
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.providers.video_provider import VideoGenerationProvider

logger = logging.getLogger(__name__)

_POLL_SECONDS = 5
_MAX_WAIT_SECONDS = 8 * 60


def resolve_video_size(aspect_ratio: str | None) -> tuple[str, int, int]:
    key = (aspect_ratio or "9:16").strip()
    if key in ("16:9", "1.91:1"):
        return "1280x720", 1280, 720
    return "720x1280", 720, 1280


def clamp_video_seconds(duration: float | int | None) -> str:
    seconds = float(duration or 8)
    if seconds <= 6:
        return "4"
    if seconds <= 10:
        return "8"
    return "12"


class OpenAIVideoProvider(VideoGenerationProvider):
    """Render a real MP4 through OpenAI Videos (Sora)."""

    def __init__(
        self,
        client: AdsOpenAIClient,
        store: CreativeAssetStore,
        *,
        model: str | None = None,
    ) -> None:
        self._client = client
        self._store = store
        self._model = model or settings.resolved_ai_video_model

    async def generate_video(
        self,
        spec: dict[str, Any],
        *,
        cancel_check: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        prompt = str(spec.get("prompt") or spec.get("hook") or "").strip()
        if not prompt:
            raise VideoProviderError("Video prompt is empty")
        size, width, height = resolve_video_size(str(spec.get("format") or spec.get("aspect_ratio") or "9:16"))
        seconds = clamp_video_seconds(spec.get("duration") or spec.get("seconds"))
        reference = spec.get("input_reference")
        if not (isinstance(reference, tuple) and reference and reference[0]):
            reference = None
        try:
            created = await self._client.create_video(
                prompt=prompt,
                model=self._model,
                size=size,
                seconds=seconds,
                input_reference=reference,
            )
        except Exception as exc:
            raise VideoProviderError(str(exc), retryable=True) from exc
        video_id = str(created.get("id") or "")
        if not video_id:
            raise VideoProviderError("Video job did not return an id")
        job = await self._wait(video_id, cancel_check=cancel_check)
        if str(job.get("status") or "") != "completed":
            err = job.get("error") if isinstance(job.get("error"), dict) else {}
            message = str((err or {}).get("message") or job.get("status") or "Video generation failed")
            raise VideoProviderError(message, retryable=True)
        try:
            raw = await self._client.download_video_bytes(video_id)
        except Exception as exc:
            raise VideoProviderError(str(exc), retryable=True) from exc
        if not is_mp4(raw):
            raise VideoProviderError("Video download was not a playable MP4")
        saved = self._store.save_bytes(raw, mime_type="video/mp4", prefix="vid")
        return {
            "status": "completed",
            "provider": self._model,
            "video_id": video_id,
            "local_path": saved["relative_path"],
            "preview_url": saved["public_url"],
            "width": width,
            "height": height,
            "seconds": seconds,
            "mime_type": "video/mp4",
        }

    async def get_generation_status(self, job_id: str) -> dict[str, Any]:
        return await self._client.get_video(job_id)

    async def download_video(self, job_id: str) -> bytes | None:
        try:
            return await self._client.download_video_bytes(job_id)
        except Exception:
            return None

    async def _wait(
        self,
        video_id: str,
        *,
        cancel_check: Callable[[], None] | None,
    ) -> dict[str, Any]:
        elapsed = 0
        last: dict[str, Any] = {}
        while elapsed <= _MAX_WAIT_SECONDS:
            if cancel_check:
                cancel_check()
            last = await self._client.get_video(video_id)
            status = str(last.get("status") or "")
            if status in ("completed", "failed"):
                return last
            await asyncio.sleep(_POLL_SECONDS)
            elapsed += _POLL_SECONDS
        raise VideoProviderError("Video generation timed out before an MP4 was ready", retryable=True)
