from __future__ import annotations

from abc import ABC, abstractmethod

from app.services.ai_ads.schemas import ImageGenerationRequest, ImageGenerationResult


class ImageGenerationProvider(ABC):
    @abstractmethod
    async def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        raise NotImplementedError

    async def get_status(self, provider_id: str) -> str:
        return "completed"

    async def download(self, provider_id: str) -> bytes | None:
        return None
