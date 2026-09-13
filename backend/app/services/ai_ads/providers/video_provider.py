from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class VideoGenerationProvider(ABC):
    """Provider-agnostic video adapter. Strategy/planning must not depend on a vendor."""

    @abstractmethod
    async def generate_video(self, spec: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def get_generation_status(self, job_id: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def download_video(self, job_id: str) -> bytes | None:
        raise NotImplementedError


class UnconfiguredVideoProvider(VideoGenerationProvider):
    """Default: video specs are stored; no vendor is called."""

    async def generate_video(self, spec: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "planned",
            "provider": None,
            "message": "No video generation provider is configured. The storyboard was saved.",
            "spec": spec,
        }

    async def get_generation_status(self, job_id: str) -> dict[str, Any]:
        return {"status": "planned", "job_id": job_id}

    async def download_video(self, job_id: str) -> bytes | None:
        return None
