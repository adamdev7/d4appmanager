"""Creative memory: hooks, angles, and scenes already used (generated or live on Meta) with results.

Built from existing rows (concepts, assets, Meta ads, DNA, snapshots) instead of a copy table,
so it never drifts from what was actually made. ``novelty`` compares a new idea against it.
"""

from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.models import (
    CreativeAsset,
    CreativeConcept,
    CreativeDNA,
    CreativePerformanceSnapshot,
    MetaCreative,
)

_WORD = re.compile(r"[a-zà-ÿ0-9']+", re.IGNORECASE)
_STOP = {
    "the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with", "your", "you", "her", "his",
    "is", "it", "this", "that", "our", "my", "le", "la", "les", "un", "une", "des", "de", "du", "et",
    "pour", "votre", "vos", "ton", "ta", "tes", "sa", "son", "ses", "au", "aux", "en", "est",
}
DUPLICATE_THRESHOLD = 0.6


def tokens(text: str | None) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "") if w.lower() not in _STOP and len(w) > 2}


def similarity(a: str | None, b: str | None) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _perf(snap: CreativePerformanceSnapshot | None) -> dict[str, Any] | None:
    if not snap:
        return None
    return {"ctr": snap.ctr, "roas": snap.roas, "spend": snap.spend, "frequency": snap.frequency}


def build_memory(db: Session, store_id: str, *, limit: int = 120) -> list[dict[str, Any]]:
    """Most recent creative elements first. Each item: source, hook, angle, scene, outcome."""
    items: list[dict[str, Any]] = []
    concepts = db.scalars(
        select(CreativeConcept)
        .where(CreativeConcept.store_id == store_id)
        .order_by(desc(CreativeConcept.created_at))
        .limit(limit)
    ).all()
    concept_ids = [c.id for c in concepts]
    assets_by_concept: dict[str, list[CreativeAsset]] = {}
    if concept_ids:
        for asset in db.scalars(select(CreativeAsset).where(CreativeAsset.concept_id.in_(concept_ids))).all():
            assets_by_concept.setdefault(asset.concept_id or "", []).append(asset)
    asset_ids = [a.id for assets in assets_by_concept.values() for a in assets]
    perf_by_asset: dict[str, CreativePerformanceSnapshot] = {}
    if asset_ids:
        for snap in db.scalars(
            select(CreativePerformanceSnapshot)
            .where(CreativePerformanceSnapshot.generated_asset_id.in_(asset_ids))
            .order_by(desc(CreativePerformanceSnapshot.created_at))
        ).all():
            perf_by_asset.setdefault(snap.generated_asset_id or "", snap)
    for concept in concepts:
        assets = assets_by_concept.get(concept.id, [])
        statuses = sorted({(a.status or "").upper() for a in assets})
        perf = next((perf_by_asset.get(a.id) for a in assets if perf_by_asset.get(a.id)), None)
        items.append(
            {
                "source": "generated",
                "id": concept.id,
                "type": concept.type,
                "concept": concept.concept_name,
                "hook": concept.hook,
                "angle": concept.angle,
                "scene": (concept.visual_direction or "")[:160],
                "hypothesis": concept.hypothesis or "",
                "status": statuses,
                "performance": _perf(perf),
            }
        )

    metas = db.scalars(
        select(MetaCreative)
        .where(MetaCreative.store_id == store_id)
        .order_by(desc(MetaCreative.updated_at))
        .limit(limit)
    ).all()
    meta_ids = [m.id for m in metas]
    dna_by_meta: dict[str, CreativeDNA] = {}
    perf_by_meta: dict[str, CreativePerformanceSnapshot] = {}
    if meta_ids:
        for dna in db.scalars(select(CreativeDNA).where(CreativeDNA.meta_creative_row_id.in_(meta_ids))).all():
            dna_by_meta.setdefault(dna.meta_creative_row_id or "", dna)
        for snap in db.scalars(
            select(CreativePerformanceSnapshot)
            .where(CreativePerformanceSnapshot.meta_creative_row_id.in_(meta_ids))
            .order_by(desc(CreativePerformanceSnapshot.created_at))
        ).all():
            perf_by_meta.setdefault(snap.meta_creative_row_id or "", snap)
    for meta in metas:
        dna = dna_by_meta.get(meta.id)
        visual = json.loads(dna.visual_dna_json) if dna and dna.visual_dna_json else {}
        first_line = (meta.primary_text or "").strip().split("\n")[0][:160]
        items.append(
            {
                "source": "meta",
                "id": meta.id,
                "type": meta.format,
                "concept": meta.ad_name or "",
                "hook": first_line or meta.headline or "",
                "angle": meta.headline or "",
                "scene": str(visual.get("setting") or visual.get("visual_hook") or "")[:160],
                "hypothesis": "",
                "status": ["LIVE_ON_META"],
                "performance": _perf(perf_by_meta.get(meta.id)),
            }
        )
    return items


def novelty(idea: dict[str, Any], memory: list[dict[str, Any]]) -> tuple[float, dict[str, Any] | None]:
    """1.0 = nothing like it was made before. Returns the closest past item for the "don't repeat" note."""
    text = " ".join(str(idea.get(k) or "") for k in ("concept_name", "hook", "angle", "setting"))
    best = 0.0
    closest: dict[str, Any] | None = None
    for item in memory:
        past = " ".join(str(item.get(k) or "") for k in ("concept", "hook", "angle", "scene"))
        hook_sim = similarity(idea.get("hook"), item.get("hook"))
        score = max(similarity(text, past), hook_sim)
        if score > best:
            best, closest = score, item
    return round(1.0 - best, 2), closest


def memory_digest(memory: list[dict[str, Any]], *, limit: int = 40) -> list[dict[str, Any]]:
    """Compact list for prompts: what was already said, and how it did."""
    out = []
    for item in memory[:limit]:
        out.append(
            {
                "source": item["source"],
                "hook": (item.get("hook") or "")[:140],
                "angle": (item.get("angle") or "")[:100],
                "scene": (item.get("scene") or "")[:100],
                "status": item.get("status"),
                "performance": item.get("performance"),
            }
        )
    return out
