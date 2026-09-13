from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CreativePerformanceSnapshot, MetaCreative
from app.integrations.meta.client import (
    MetaAdsClient,
    parse_meta_cpa,
    parse_meta_float,
    parse_meta_link_clicks,
    parse_meta_link_cpc,
    parse_meta_link_ctr,
    parse_meta_purchase_roas,
    parse_meta_purchase_value,
    parse_meta_purchases,
    parse_meta_video_3s_plays,
)
from app.services.ai_ads.asset_store import CreativeAssetStore, aspect_ratio_label
from app.services.ai_ads.performance_analyzer import normalize_insight_row, percentile_ranks
from app.services.ai_ads.schemas import NormalizedMetaCreative, PerformanceSummary

logger = logging.getLogger(__name__)


def normalize_meta_ad(ad: dict[str, Any], *, campaigns: dict[str, str], adsets: dict[str, str]) -> NormalizedMetaCreative:
    creative = ad.get("creative") if isinstance(ad.get("creative"), dict) else {}
    story = creative.get("object_story_spec") if isinstance(creative.get("object_story_spec"), dict) else {}
    link = story.get("link_data") if isinstance(story.get("link_data"), dict) else {}
    video = story.get("video_data") if isinstance(story.get("video_data"), dict) else {}
    feed = creative.get("asset_feed_spec") if isinstance(creative.get("asset_feed_spec"), dict) else {}

    primary = _first_str(
        link.get("message"),
        video.get("message"),
        creative.get("body"),
        _feed_first(feed, "bodies", "text"),
    )
    headline = _first_str(
        link.get("name"),
        video.get("title"),
        creative.get("title"),
        _feed_first(feed, "titles", "text"),
    )
    description = _first_str(
        link.get("description"),
        creative.get("description"),
        _feed_first(feed, "descriptions", "text"),
    )
    dest = _first_str(
        link.get("link"),
        creative.get("link_url"),
        _feed_first(feed, "link_urls", "website_url"),
    )
    cta = _cta(
        link.get("call_to_action"),
        video.get("call_to_action"),
        creative.get("call_to_action_type"),
        _feed_first(feed, "call_to_action_types"),
    )
    image_url = _first_str(
        creative.get("image_url"),
        link.get("picture"),
        video.get("image_url"),
        _feed_image(feed),
    )
    thumb = _first_str(creative.get("thumbnail_url"), creative.get("image_url"))
    video_id = _first_str(creative.get("video_id"), video.get("video_id"), _feed_video(feed))
    fmt = infer_format(creative, video_id=video_id, image_url=image_url, feed=feed)
    width = _int(link.get("image_crops") and None)
    fingerprint = fingerprint_creative(
        {
            "creative_id": creative.get("id"),
            "image_url": image_url,
            "video_id": video_id,
            "primary": primary,
            "headline": headline,
            "cta": cta,
            "image_hash": creative.get("image_hash"),
        }
    )
    campaign_id = _first_str(ad.get("campaign_id"))
    adset_id = _first_str(ad.get("adset_id"))
    return NormalizedMetaCreative(
        campaign_id=campaign_id,
        campaign_name=campaigns.get(campaign_id or "") or None,
        adset_id=adset_id,
        adset_name=adsets.get(adset_id or "") or None,
        ad_id=_first_str(ad.get("id")),
        ad_name=_first_str(ad.get("name")),
        creative_id=_first_str(creative.get("id")),
        image_url=image_url,
        thumbnail_url=thumb,
        video_id=video_id,
        video_thumbnail=None,
        primary_text=primary,
        headline=headline,
        description=description,
        cta=cta,
        destination_url=dest,
        format=fmt,
        width=width,
        height=None,
        aspect_ratio=None,
        placement=_feed_placements(feed),
        creation_date=_first_str(ad.get("created_time"), creative.get("created_time")),
        creative_fingerprint=fingerprint,
    )


def infer_format(creative: dict, *, video_id: str | None, image_url: str | None, feed: dict) -> str:
    obj = str(creative.get("object_type") or "").upper()
    if feed.get("videos") or (isinstance(feed.get("asset_customization_rules"), list) and video_id):
        if feed.get("images") and feed.get("videos"):
            return "CAROUSEL"
    if feed.get("bodies") and (feed.get("images") or feed.get("videos")) and len(feed.get("images") or []) > 1:
        return "CAROUSEL"
    if "CAROUSEL" in obj or feed.get("child_attachments"):
        return "CAROUSEL"
    if video_id or "VIDEO" in obj:
        return "VIDEO"
    if image_url or "PHOTO" in obj or "IMAGE" in obj or creative.get("image_hash"):
        return "IMAGE"
    if feed:
        return "CAROUSEL" if len(feed.get("images") or []) > 1 else "OTHER"
    return "OTHER"


def fingerprint_creative(parts: dict[str, Any]) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class MetaCreativeImporter:
    def __init__(self, client: MetaAdsClient, store_id: str) -> None:
        self.client = client
        self.store_id = store_id
        self.assets = CreativeAssetStore(store_id)

    async def sync(self, db: Session, *, since: str | None = None, until: str | None = None) -> dict[str, int]:
        campaigns_raw = await self.client.list_campaigns()
        adsets_raw = await self.client.list_adsets()
        campaigns = {str(c.get("id")): str(c.get("name") or "") for c in campaigns_raw}
        adsets = {str(a.get("id")): str(a.get("name") or "") for a in adsets_raw}
        ads = await self.client.list_ads_with_creatives()

        created = 0
        updated = 0
        skipped_download = 0
        now = datetime.now(UTC)

        rows_by_ad: dict[str, MetaCreative] = {}
        existing = db.scalars(select(MetaCreative).where(MetaCreative.store_id == self.store_id)).all()
        for row in existing:
            if row.ad_id:
                rows_by_ad[row.ad_id] = row

        for ad in ads:
            norm = normalize_meta_ad(ad, campaigns=campaigns, adsets=adsets)
            if not norm.ad_id:
                continue
            row = rows_by_ad.get(norm.ad_id)
            unchanged = bool(row and row.creative_hash and row.creative_hash == norm.creative_fingerprint)
            if row is None:
                row = MetaCreative(store_id=self.store_id, ad_id=norm.ad_id)
                db.add(row)
                created += 1
            else:
                updated += 1
            self._apply_norm(row, norm)
            row.last_synced_at = now
            if unchanged and row.local_asset_path:
                skipped_download += 1
            else:
                await self._ingest_assets(row, norm)

        insights = await self.client.get_ad_insights(since=since, until=until, date_preset=None if since else "last_30d")
        self._upsert_performance(db, insights, since=since, until=until)
        db.commit()
        return {
            "campaigns": len(campaigns),
            "adsets": len(adsets),
            "ads": len(ads),
            "creatives_created": created,
            "creatives_updated": updated,
            "assets_skipped": skipped_download,
            "insights": len(insights),
        }

    def _apply_norm(self, row: MetaCreative, norm: NormalizedMetaCreative) -> None:
        row.campaign_id = norm.campaign_id
        row.campaign_name = norm.campaign_name
        row.adset_id = norm.adset_id
        row.adset_name = norm.adset_name
        row.ad_id = norm.ad_id
        row.ad_name = norm.ad_name
        row.meta_creative_id = norm.creative_id
        row.image_url = norm.image_url
        row.thumbnail_url = norm.thumbnail_url
        row.video_id = norm.video_id
        row.primary_text = norm.primary_text
        row.headline = norm.headline
        row.description = norm.description
        row.cta = norm.cta
        row.destination_url = norm.destination_url
        row.format = norm.format
        row.meta_created_at = norm.creation_date
        row.creative_hash = norm.creative_fingerprint
        row.placement_json = json.dumps(norm.placement or [])
        extra = json.loads(row.extra_json or "{}") if row.extra_json else {}
        extra["fingerprint"] = norm.creative_fingerprint
        row.extra_json = json.dumps(extra)

    async def _ingest_assets(self, row: MetaCreative, norm: NormalizedMetaCreative) -> None:
        if row.format == "VIDEO" and row.video_id:
            meta = await self.client.get_video_meta(row.video_id)
            picture = _first_str(meta.get("picture"))
            thumbs = meta.get("thumbnails") or {}
            data = thumbs.get("data") if isinstance(thumbs, dict) else None
            if isinstance(data, list) and data:
                picture = _first_str(data[0].get("uri"), picture)
            row.video_thumbnail = picture or row.video_thumbnail
            url = picture or row.thumbnail_url
            if url:
                raw = await self.client.download_url(url)
                if raw:
                    saved = self.assets.save_bytes(raw, mime_type="image/jpeg", prefix="vthumb")
                    row.local_thumbnail_path = saved["relative_path"]
                    row.creative_hash = saved["hash"]
            return

        url = row.image_url or row.thumbnail_url
        if not url:
            return
        raw = await self.client.download_url(url)
        if not raw:
            logger.info("ai_ads meta asset expired or blocked store_id=%s ad_id=%s", self.store_id, row.ad_id)
            return
        saved = self.assets.save_bytes(raw, mime_type="image/jpeg", prefix="meta")
        row.local_asset_path = saved["relative_path"]
        row.local_thumbnail_path = saved["relative_path"]
        row.creative_hash = saved["hash"]

    def _upsert_performance(
        self,
        db: Session,
        insights: list[dict],
        *,
        since: str | None,
        until: str | None,
    ) -> None:
        by_ad = {
            r.ad_id: r
            for r in db.scalars(select(MetaCreative).where(MetaCreative.store_id == self.store_id)).all()
            if r.ad_id
        }
        summaries: list[tuple[str, PerformanceSummary]] = []
        for row in insights:
            ad_id = str(row.get("ad_id") or "")
            if not ad_id:
                continue
            summary = normalize_insight_row(row, since=since, until=until)
            summaries.append((ad_id, summary))
            creative = by_ad.get(ad_id)
            snap = CreativePerformanceSnapshot(
                store_id=self.store_id,
                meta_creative_row_id=creative.id if creative else None,
                ad_id=ad_id,
                impressions=summary.impressions,
                reach=summary.reach,
                clicks=summary.clicks,
                spend=summary.spend,
                ctr=summary.ctr,
                cpc=summary.cpc,
                cpm=summary.cpm,
                purchases=summary.purchases,
                cpa=summary.cpa,
                conversion_value=summary.conversion_value,
                roas=summary.roas,
                video_views=summary.video_views,
                video_watch_json=json.dumps(summary.video_watch or {}),
                frequency=summary.frequency,
                date_range_start=summary.date_range_start,
                date_range_end=summary.date_range_end,
                insufficient_data=summary.insufficient_data,
            )
            db.add(snap)

        ranks = percentile_ranks([s for _, s in summaries])
        extra_by_ad = {ad_id: ranks.get(i, {}) for i, (ad_id, _) in enumerate(summaries)}
        for ad_id, extra in extra_by_ad.items():
            creative = by_ad.get(ad_id)
            if not creative:
                continue
            payload = json.loads(creative.extra_json or "{}")
            payload["performance_percentiles"] = extra
            creative.extra_json = json.dumps(payload)


def _first_str(*values: Any) -> str | None:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def _int(v: Any) -> int | None:
    try:
        return int(v) if v is not None and v != "" else None
    except (TypeError, ValueError):
        return None


def _cta(*values: Any) -> str | None:
    for v in values:
        if isinstance(v, dict):
            t = v.get("type") or (v.get("value") or {}).get("type")
            if t:
                return str(t)
        elif isinstance(v, str) and v.strip():
            return v.strip()
        elif isinstance(v, list) and v:
            return _cta(v[0])
    return None


def _feed_first(feed: dict, key: str, field: str | None = None) -> str | None:
    items = feed.get(key)
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        if field:
            return _first_str(first.get(field))
        return _first_str(first.get("text"), first.get("type"))
    return _first_str(first)


def _feed_image(feed: dict) -> str | None:
    images = feed.get("images")
    if isinstance(images, list) and images and isinstance(images[0], dict):
        return _first_str(images[0].get("url"), images[0].get("hash"))
    return None


def _feed_video(feed: dict) -> str | None:
    videos = feed.get("videos")
    if isinstance(videos, list) and videos and isinstance(videos[0], dict):
        return _first_str(videos[0].get("video_id"), videos[0].get("id"))
    return None


def _feed_placements(feed: dict) -> list[str] | None:
    rules = feed.get("asset_customization_rules")
    if not isinstance(rules, list):
        return None
    out: list[str] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        custom = rule.get("customization_spec") or {}
        for p in custom.get("publisher_platforms") or []:
            if p not in out:
                out.append(str(p))
    return out or None


# Re-export parsers so tests can monkeypatch a single module
__all__ = [
    "MetaCreativeImporter",
    "normalize_meta_ad",
    "infer_format",
    "fingerprint_creative",
    "parse_meta_cpa",
    "parse_meta_float",
    "parse_meta_link_clicks",
    "parse_meta_link_cpc",
    "parse_meta_link_ctr",
    "parse_meta_purchase_roas",
    "parse_meta_purchase_value",
    "parse_meta_purchases",
    "parse_meta_video_3s_plays",
    "aspect_ratio_label",
]
