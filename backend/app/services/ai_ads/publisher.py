from __future__ import annotations

import logging
from typing import Any

from app.db.models import CreativeAsset, StoreAIAdsSettings
from app.integrations.meta.client import MetaAdsClient
from app.services.ai_ads.exceptions import MetaImportError

logger = logging.getLogger(__name__)


class MetaCreativePublisher:
    """Prepare / publish approved creatives. Never auto-spend unless explicitly enabled."""

    def __init__(self, client: MetaAdsClient) -> None:
        self.client = client

    async def create_creative(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.client.create_ad_creative(payload)
        except Exception as exc:
            raise MetaImportError(f"Meta create_creative failed: {exc}", retryable=True) from exc

    async def create_ad(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return await self.client.create_ad(payload)
        except Exception as exc:
            raise MetaImportError(f"Meta create_ad failed: {exc}", retryable=True) from exc

    async def publish_ad(
        self,
        asset: CreativeAsset,
        *,
        adset_id: str,
        settings_row: StoreAIAdsSettings,
        page_id: str | None = None,
        activate: bool = False,
    ) -> dict[str, Any]:
        if asset.status != "APPROVED":
            raise MetaImportError("Creative must be APPROVED before publishing")
        if not page_id and not settings_row.meta_page_id:
            raise MetaImportError("Connect a Meta Page ID in AI Ads settings before publishing")
        if not activate:
            # Default: create paused so no spend starts.
            status = "PAUSED"
        else:
            status = "ACTIVE"
        payload = {
            "name": (asset.headline or "AI creative")[:256],
            "adset_id": adset_id,
            "status": status,
            "creative": {
                "object_story_spec": {
                    "page_id": page_id or settings_row.meta_page_id,
                    "link_data": {
                        "message": asset.primary_text or asset.hook or "",
                        "name": asset.headline or "",
                        "link": asset.preview_url or "",
                        "call_to_action": {"type": (asset.cta or "SHOP_NOW").upper()},
                    },
                }
            },
        }
        created = await self.create_ad(payload)
        return created

    async def pause_ad(self, ad_id: str) -> dict[str, Any]:
        return await self.client.update_ad_status(ad_id, "PAUSED")
