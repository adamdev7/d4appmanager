from __future__ import annotations

import logging
from typing import Any

from app.db.models import CreativeAsset, StoreAIAdsSettings
from app.integrations.meta.client import MetaAdsClient
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.exceptions import MetaImportError

logger = logging.getLogger(__name__)

_META_CTAS = {
    "SHOP_NOW",
    "LEARN_MORE",
    "SIGN_UP",
    "SUBSCRIBE",
    "DOWNLOAD",
    "GET_OFFER",
    "CONTACT_US",
    "APPLY_NOW",
    "BUY_NOW",
    "ORDER_NOW",
    "BOOK_TRAVEL",
    "GET_QUOTE",
}


def _meta_cta(raw: str | None) -> str:
    token = (raw or "SHOP_NOW").strip().upper().replace(" ", "_")
    return token if token in _META_CTAS else "SHOP_NOW"


def _is_video_asset(asset: CreativeAsset) -> bool:
    path = (asset.local_path or "").lower()
    return asset.type == "VIDEO" or path.endswith((".mp4", ".mov", ".webm"))


class MetaCreativePublisher:
    """Upload the rendered file to Meta, then create a paused or active ad."""

    def __init__(self, client: MetaAdsClient, store_id: str) -> None:
        self.client = client
        self.store = CreativeAssetStore(store_id)

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
        destination_url: str | None = None,
    ) -> dict[str, Any]:
        if asset.status != "APPROVED":
            raise MetaImportError("Creative must be APPROVED before publishing")
        page = page_id or settings_row.meta_page_id
        if not page:
            raise MetaImportError("Connect a Meta Page ID in AI Ads settings before publishing")
        link = (destination_url or "").strip()
        if not link:
            raise MetaImportError("A product or store URL is required before publishing")
        media = await self._upload_media(asset)
        if not media.get("image_hash") and not media.get("video_id"):
            raise MetaImportError("This creative has no rendered image or MP4 to upload to Meta")
        story = self._story_spec(asset, page=page, link=link, media=media)
        creative = await self.create_creative(
            {"name": (asset.headline or "AI creative")[:256], "object_story_spec": story}
        )
        creative_id = str(creative.get("id") or "")
        if not creative_id:
            raise MetaImportError("Meta did not return a creative id")
        created = await self.create_ad(
            {
                "name": (asset.headline or "AI creative")[:256],
                "adset_id": adset_id,
                "status": "ACTIVE" if activate else "PAUSED",
                "creative": {"creative_id": creative_id},
            }
        )
        created["creative_id"] = creative_id
        created["image_hash"] = media.get("image_hash")
        created["video_id"] = media.get("video_id")
        return created

    async def _upload_media(self, asset: CreativeAsset) -> dict[str, str]:
        out: dict[str, str] = {}
        if _is_video_asset(asset):
            video = self.store.read_bytes(asset.local_path)
            if not video:
                raise MetaImportError("Rendered MP4 is missing from disk — regenerate before publishing")
            raw, _mime = video
            uploaded = await self.client.upload_ad_video(raw, filename="ai-ad.mp4")
            video_id = str(uploaded.get("id") or "")
            if video_id:
                try:
                    await self.client.wait_for_video(video_id)
                except Exception as exc:
                    logger.info("ai_ads meta video wait skipped video_id=%s err=%s", video_id, exc)
            out["video_id"] = video_id
            poster = self.store.read_bytes(asset.preview_url) or self.store.read_bytes(asset.local_path)
            if poster and not poster[1].startswith("video/"):
                image = await self.client.upload_ad_image(poster[0], filename="ai-ad-poster.png")
                out["image_hash"] = str(image.get("hash") or "")
            return out
        image_file = self.store.read_bytes(asset.local_path) or self.store.read_bytes(asset.preview_url)
        if not image_file:
            raise MetaImportError("Rendered image is missing from disk — regenerate before publishing")
        raw, mime = image_file
        if mime.startswith("video/"):
            raise MetaImportError("This image ad is pointing at a video file")
        ext = "png" if "png" in mime else "jpg"
        uploaded = await self.client.upload_ad_image(raw, filename=f"ai-ad.{ext}")
        out["image_hash"] = str(uploaded.get("hash") or "")
        return out

    def _story_spec(
        self,
        asset: CreativeAsset,
        *,
        page: str,
        link: str,
        media: dict[str, str],
    ) -> dict[str, Any]:
        cta = {"type": _meta_cta(asset.cta), "value": {"link": link}}
        if media.get("video_id"):
            video_data: dict[str, Any] = {
                "video_id": media["video_id"],
                "title": (asset.headline or asset.hook or "Shop now")[:255],
                "message": asset.primary_text or asset.hook or "",
                "call_to_action": cta,
            }
            if media.get("image_hash"):
                video_data["image_hash"] = media["image_hash"]
            return {"page_id": page, "video_data": video_data}
        return {
            "page_id": page,
            "link_data": {
                "message": asset.primary_text or asset.hook or "",
                "name": asset.headline or asset.hook or "",
                "link": link,
                "image_hash": media.get("image_hash"),
                "call_to_action": {"type": _meta_cta(asset.cta)},
            },
        }

    async def pause_ad(self, ad_id: str) -> dict[str, Any]:
        return await self.client.update_ad_status(ad_id, "PAUSED")
