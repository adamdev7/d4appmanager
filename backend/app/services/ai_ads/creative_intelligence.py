from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import CreativeDNA, CreativePerformanceSnapshot, MetaCreative
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.exceptions import InvalidAIOutput
from app.services.ai_ads.openai_client import AdsOpenAIClient
from app.services.ai_ads.performance_analyzer import percentile_ranks, split_performance_groups
from app.services.ai_ads.prompts import CREATIVE_DNA, CREATIVE_INTELLIGENCE
from app.services.ai_ads.schemas import (
    CreativeDNAModel,
    CreativeIntelligenceReport,
    PerformanceDNA,
    PerformanceSummary,
)

logger = logging.getLogger(__name__)


class CreativeIntelligenceAnalyzer:
    def __init__(self, client: AdsOpenAIClient, store_id: str) -> None:
        self.client = client
        self.store_id = store_id
        self.assets = CreativeAssetStore(store_id)
        self.model = settings.resolved_ai_analysis_model

    def latest_performance_map(self, db: Session) -> dict[str, CreativePerformanceSnapshot]:
        snaps = db.scalars(
            select(CreativePerformanceSnapshot)
            .where(CreativePerformanceSnapshot.store_id == self.store_id)
            .order_by(CreativePerformanceSnapshot.created_at.desc())
        ).all()
        out: dict[str, CreativePerformanceSnapshot] = {}
        for snap in snaps:
            if snap.meta_creative_row_id and snap.meta_creative_row_id not in out:
                out[snap.meta_creative_row_id] = snap
        return out

    def attach_percentiles(self, items: list[dict[str, Any]]) -> None:
        summaries: list[PerformanceSummary] = []
        for item in items:
            p = item.get("performance") or {}
            summaries.append(PerformanceSummary.model_validate(p) if isinstance(p, dict) else PerformanceSummary())
        ranks = percentile_ranks(summaries)
        for i, item in enumerate(items):
            extra = ranks.get(i) or {}
            item["performance_percentiles"] = extra or None

    async def analyze_one(
        self,
        db: Session,
        creative: MetaCreative,
        snap: CreativePerformanceSnapshot | None,
        *,
        force: bool = False,
        allow_vision: bool = True,
    ) -> CreativeDNA:
        existing = db.scalar(
            select(CreativeDNA).where(
                CreativeDNA.store_id == self.store_id,
                CreativeDNA.meta_creative_row_id == creative.id,
            )
        )
        if existing and not force:
            return existing

        images: list[dict[str, str]] = []
        basis = "copy_only"
        path = creative.local_asset_path or creative.local_thumbnail_path
        if allow_vision and path:
            data_url = self.assets.file_to_data_url(path)
            if data_url:
                images.append({"url": data_url})
                basis = "thumbnail" if creative.format == "VIDEO" and not creative.local_asset_path else "image"
        elif creative.format == "VIDEO":
            basis = "thumbnail" if (creative.video_thumbnail or creative.thumbnail_url) else "copy_only"

        percentiles = {}
        extra = json.loads(creative.extra_json or "{}")
        if isinstance(extra.get("performance_percentiles"), dict):
            percentiles = extra["performance_percentiles"]

        payload = {
            "creative_id": creative.id,
            "format": creative.format,
            "analysis_basis_hint": basis,
            "copy": {
                "primary_text": creative.primary_text,
                "headline": creative.headline,
                "description": creative.description,
                "cta": creative.cta,
            },
            "performance": _snap_dict(snap),
            "performance_percentiles": percentiles or None,
        }
        user = (
            "Analyze this Meta creative. If an image is attached, describe what is actually visible. "
            f"If analysis_basis_hint is thumbnail, you only have a still/thumbnail.\n\n{json.dumps(payload, default=str)[:8000]}"
        )
        try:
            dna = await self.client.complete_json(
                system=CREATIVE_DNA,
                user=user,
                schema=CreativeDNAModel,
                model=self.model,
                images=images or None,
                operation="creative_dna",
            )
            assert isinstance(dna, CreativeDNAModel)
        except Exception as exc:
            logger.warning("ai_ads dna failed store_id=%s creative=%s err=%s", self.store_id, creative.id, exc)
            dna = CreativeDNAModel(
                analysis_basis=basis,
                observed=["Creative DNA extraction failed; copy/performance stored without visual analysis."],
                interpretation=[],
            )

        dna.analysis_basis = basis
        if percentiles:
            try:
                dna.performance_dna = PerformanceDNA.model_validate(percentiles)
            except Exception:
                pass

        row = db.scalar(
            select(CreativeDNA).where(
                CreativeDNA.store_id == self.store_id,
                CreativeDNA.meta_creative_row_id == creative.id,
            )
        )
        if row is None:
            row = CreativeDNA(store_id=self.store_id, meta_creative_row_id=creative.id)
            db.add(row)
        row.visual_dna_json = dna.visual_dna.model_dump_json()
        row.copy_dna_json = dna.copy_dna.model_dump_json()
        row.format_dna_json = dna.format_dna.model_dump_json()
        row.performance_dna_json = dna.performance_dna.model_dump_json()
        row.analysis_json = json.dumps(
            {"observed": dna.observed, "interpretation": dna.interpretation}
        )
        row.analysis_basis = dna.analysis_basis
        row.model_used = self.model
        db.commit()
        db.refresh(row)
        return row

    async def build_report(self, db: Session, *, limit: int = 40) -> CreativeIntelligenceReport:
        creatives = db.scalars(
            select(MetaCreative)
            .where(MetaCreative.store_id == self.store_id)
            .order_by(MetaCreative.updated_at.desc())
            .limit(limit)
        ).all()
        perf_map = self.latest_performance_map(db)
        items: list[dict[str, Any]] = []
        for c in creatives:
            snap = perf_map.get(c.id)
            dna = db.scalar(
                select(CreativeDNA).where(
                    CreativeDNA.store_id == self.store_id,
                    CreativeDNA.meta_creative_row_id == c.id,
                )
            )
            items.append(
                {
                    "id": c.id,
                    "ad_name": c.ad_name,
                    "format": c.format,
                    "copy": {
                        "primary_text": c.primary_text,
                        "headline": c.headline,
                        "cta": c.cta,
                    },
                    "dna": {
                        "visual": json.loads(dna.visual_dna_json) if dna else {},
                        "copy": json.loads(dna.copy_dna_json) if dna else {},
                        "format": json.loads(dna.format_dna_json) if dna else {},
                    },
                    "performance": _snap_dict(snap),
                }
            )
        self.attach_percentiles(items)
        groups = split_performance_groups(items)
        payload = {
            "groups": {
                "winning": groups["winning"],
                "average": groups["average"],
                "losing": groups["losing"],
            },
            "insufficient_split": groups.get("insufficient"),
            "all": items[:limit],
        }
        user = (
            "Build a CreativeIntelligenceReport from this dataset. "
            "Compare winners, average, and losers. Do not claim causation.\n\n"
            f"{json.dumps(payload, default=str)[:18000]}"
        )
        try:
            report = await self.client.complete_json(
                system=CREATIVE_INTELLIGENCE,
                user=user,
                schema=CreativeIntelligenceReport,
                model=self.model,
                operation="creative_intelligence",
            )
            assert isinstance(report, CreativeIntelligenceReport)
        except (InvalidAIOutput, Exception) as exc:
            logger.warning("ai_ads intelligence report failed store_id=%s err=%s", self.store_id, exc)
            report = CreativeIntelligenceReport(
                winning_creatives=[i["id"] for i in groups["winning"]],
                average_creatives=[i["id"] for i in groups["average"]],
                losing_creatives=[i["id"] for i in groups["losing"]],
                data_quality={"insufficient_data": bool(groups.get("insufficient")), "error": str(exc)[:200]},
                confidence=0.1 if groups.get("insufficient") else 0.3,
            )
        report.winning_creatives = report.winning_creatives or [i["id"] for i in groups["winning"]]
        report.average_creatives = report.average_creatives or [i["id"] for i in groups["average"]]
        report.losing_creatives = report.losing_creatives or [i["id"] for i in groups["losing"]]
        report.data_quality = {
            **(report.data_quality or {}),
            "creatives": len(items),
            "insufficient_split": bool(groups.get("insufficient")),
        }
        return report

    def listed_creatives(self, db: Session, *, limit: int = 80) -> list[dict[str, Any]]:
        creatives = db.scalars(
            select(MetaCreative)
            .where(MetaCreative.store_id == self.store_id)
            .order_by(MetaCreative.updated_at.desc())
            .limit(limit)
        ).all()
        perf_map = self.latest_performance_map(db)
        items: list[dict[str, Any]] = []
        for c in creatives:
            snap = perf_map.get(c.id)
            dna = db.scalar(
                select(CreativeDNA).where(
                    CreativeDNA.store_id == self.store_id,
                    CreativeDNA.meta_creative_row_id == c.id,
                )
            )
            items.append(
                {
                    "id": c.id,
                    "row": c,
                    "ad_name": c.ad_name,
                    "campaign_name": c.campaign_name,
                    "format": c.format,
                    "headline": c.headline,
                    "cta": c.cta,
                    "copy": {
                        "primary_text": c.primary_text,
                        "headline": c.headline,
                        "cta": c.cta,
                    },
                    "dna": {
                        "visual": json.loads(dna.visual_dna_json) if dna else {},
                        "copy": json.loads(dna.copy_dna_json) if dna else {},
                        "format": json.loads(dna.format_dna_json) if dna else {},
                    },
                    "has_dna": dna is not None,
                    "performance": _snap_dict(snap),
                }
            )
        self.attach_percentiles(items)
        return items

    def campaign_brief(self, db: Session) -> dict[str, Any]:
        """Rank Meta ads by performance. Reuses stored DNA; does not call OpenAI."""
        from app.services.ai_ads.complete_creative import compact_meta_item

        items = self.listed_creatives(db)
        groups = split_performance_groups(items)
        winning = [compact_meta_item(i) for i in groups["winning"][:6]]
        losing = [compact_meta_item(i) for i in groups["losing"][:4]]
        return {
            "winning": winning,
            "losing": losing,
            "average_count": len(groups.get("average") or []),
            "insufficient": bool(groups.get("insufficient")),
            "winning_ids": [i["id"] for i in groups["winning"][:6]],
            "losing_ids": [i["id"] for i in groups["losing"][:4]],
        }

    def creatives_missing_dna(self, items: list[dict[str, Any]], *, limit: int = 8) -> list[MetaCreative]:
        groups = split_performance_groups(items)
        ordered = (groups.get("winning") or []) + (groups.get("losing") or []) + (groups.get("average") or [])
        if groups.get("insufficient"):
            ordered = items
        out: list[MetaCreative] = []
        seen: set[str] = set()
        for item in ordered:
            row = item.get("row")
            cid = item.get("id")
            if not row or cid in seen or item.get("has_dna"):
                continue
            seen.add(cid)
            out.append(row)
            if len(out) >= limit:
                break
        return out


def _snap_dict(snap: CreativePerformanceSnapshot | None) -> dict[str, Any]:
    if not snap:
        return {"insufficient_data": True}
    return {
        "impressions": snap.impressions,
        "reach": snap.reach,
        "clicks": snap.clicks,
        "spend": snap.spend,
        "ctr": snap.ctr,
        "cpc": snap.cpc,
        "cpm": snap.cpm,
        "purchases": snap.purchases,
        "cpa": snap.cpa,
        "conversion_value": snap.conversion_value,
        "roas": snap.roas,
        "video_views": snap.video_views,
        "frequency": snap.frequency,
        "date_range_start": snap.date_range_start,
        "date_range_end": snap.date_range_end,
        "insufficient_data": snap.insufficient_data,
    }
