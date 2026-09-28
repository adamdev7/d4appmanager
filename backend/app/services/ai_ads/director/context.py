"""Context snapshot the Director reads before any brief, idea board, or challenge.

Every number here comes from Shopify, Meta, or the store's own rows. When a signal is not
available (e.g. Shopify storefront traffic is not in the Admin REST API), it is listed in
``data_gaps`` instead of being guessed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.crypto import decrypt_value
from app.db.models import (
    AIAdsPlaybookEntry,
    AIDirectorSettings,
    AIDirectorSuggestion,
    CreativeAsset,
    CreativeDNA,
    CreativePerformanceSnapshot,
    MetaCreative,
    ProductCost,
    ShopifyCatalogProduct,
    Store,
    StoreAIAdsSettings,
)
from app.integrations.shopify.client import ShopifyClient
from app.services.ai_ads.asset_store import CreativeAssetStore
from app.services.ai_ads.director.calendar import EVERGREEN, upcoming_occasions
from app.services.ai_ads.director.memory import build_memory, memory_digest
from app.services.ai_ads.product_catalog import ShopifyProductCatalog, numeric_shopify_id

logger = logging.getLogger(__name__)

SALES_WINDOW_DAYS = 90
RECENT_WINDOW_DAYS = 30
NEW_ARRIVAL_DAYS = 45
_PRODUCTS_TIMEOUT = 25
_ORDERS_TIMEOUT = 45
_HANDLE = re.compile(r"/products/([a-z0-9\-_%]+)", re.IGNORECASE)


def _loads(raw: str | None, default: Any) -> Any:
    try:
        value = json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _aware(value: datetime | None) -> datetime | None:
    if value and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def director_lists(director: AIDirectorSettings | None) -> dict[str, list]:
    if not director:
        return {"priority": [], "excluded": [], "offers": [], "never_do": []}
    return {
        "priority": [str(x) for x in _loads(director.priority_product_ids_json, [])],
        "excluded": [str(x) for x in _loads(director.excluded_product_ids_json, [])],
        "offers": [o for o in _loads(director.offers_json, []) if isinstance(o, dict) and o.get("label")],
        "never_do": [str(x) for x in _loads(director.never_do_json, []) if str(x).strip()],
    }


# ------------------------------------------------------------------ Shopify


def inventory_from_products(raw_products: list[dict]) -> dict[str, int | None]:
    """Total tracked inventory per product. None when Shopify does not track stock for it."""
    out: dict[str, int | None] = {}
    for product in raw_products:
        pid = numeric_shopify_id(product.get("id"))
        tracked = [
            v
            for v in (product.get("variants") or [])
            if v.get("inventory_management") and v.get("inventory_quantity") is not None
        ]
        out[pid] = sum(max(0, int(v.get("inventory_quantity") or 0)) for v in tracked) if tracked else None
    return out


def summarize_orders(orders: list[dict], *, now: datetime) -> dict[str, Any]:
    """Units and revenue per product for the full window and the last 30 days, plus AOV."""
    recent_cut = now - timedelta(days=RECENT_WINDOW_DAYS)
    by_product: dict[str, dict[str, float]] = defaultdict(lambda: {"units": 0, "revenue": 0.0, "units_30d": 0, "revenue_30d": 0.0})
    totals: list[float] = []
    for order in orders:
        if order.get("cancelled_at") or str(order.get("financial_status") or "").lower() in {"refunded", "voided"}:
            continue
        total = _num(order.get("total_price"))
        if total is not None:
            totals.append(total)
        created = order.get("created_at") or ""
        try:
            created_at = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
        except ValueError:
            created_at = None
        recent = bool(created_at and _aware(created_at) >= recent_cut)
        for line in order.get("line_items") or []:
            pid = numeric_shopify_id(line.get("product_id"))
            if not pid:
                continue
            qty = int(line.get("quantity") or 0)
            revenue = (_num(line.get("price")) or 0.0) * qty
            row = by_product[pid]
            row["units"] += qty
            row["revenue"] += revenue
            if recent:
                row["units_30d"] += qty
                row["revenue_30d"] += revenue
    return {
        "orders": len(totals),
        "revenue": round(sum(totals), 2),
        "aov": round(sum(totals) / len(totals), 2) if totals else None,
        "by_product": {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in by_product.items()},
    }


def stock_status(qty: int | None, threshold: int) -> str:
    if qty is None:
        return "unknown"
    if qty <= 0:
        return "out"
    if qty <= threshold:
        return "low"
    return "in_stock"


def margins_by_product(db: Session, store_id: str) -> dict[str, float]:
    """Average unit cost per product from Analytics COGS entries (owner-entered)."""
    costs: dict[str, list[float]] = defaultdict(list)
    for row in db.scalars(select(ProductCost).where(ProductCost.store_id == store_id)).all():
        cost = _num(row.cost_per_unit)
        if cost and cost > 0:
            costs[numeric_shopify_id(row.shopify_product_id)].append(cost)
    return {pid: sum(v) / len(v) for pid, v in costs.items()}


# ------------------------------------------------------------------ Meta


def _snapshots_by_creative(db: Session, store_id: str) -> dict[str, list[CreativePerformanceSnapshot]]:
    rows = db.scalars(
        select(CreativePerformanceSnapshot)
        .where(
            CreativePerformanceSnapshot.store_id == store_id,
            CreativePerformanceSnapshot.meta_creative_row_id.is_not(None),
        )
        .order_by(desc(CreativePerformanceSnapshot.created_at))
    ).all()
    out: dict[str, list[CreativePerformanceSnapshot]] = defaultdict(list)
    for snap in rows:
        bucket = out[snap.meta_creative_row_id or ""]
        if len(bucket) < 2:
            bucket.append(snap)
    return out


def detect_fatigue(
    snaps: dict[str, list[CreativePerformanceSnapshot]],
    *,
    min_spend: float = 20.0,
) -> list[dict[str, Any]]:
    """Frequency rising while CTR falls between the last two syncs, or very high frequency now.

    Each Meta sync stores a trailing-window aggregate, so this compares consecutive windows
    rather than daily points.
    """
    ctrs = [s[0].ctr for s in snaps.values() if s and s[0].ctr]
    ctr_median = median(ctrs) if ctrs else None
    out: list[dict[str, Any]] = []
    for creative_id, pair in snaps.items():
        latest = pair[0] if pair else None
        if not latest or (latest.spend or 0) < min_spend:
            continue
        prev = pair[1] if len(pair) > 1 else None
        reason = ""
        if prev and latest.frequency and prev.frequency and latest.ctr is not None and prev.ctr:
            freq_up = latest.frequency >= prev.frequency * 1.15
            ctr_down = latest.ctr <= prev.ctr * 0.85
            if freq_up and ctr_down:
                reason = (
                    f"Frequency {prev.frequency:.1f} → {latest.frequency:.1f} while CTR "
                    f"{prev.ctr:.2f}% → {latest.ctr:.2f}%"
                )
        if not reason and latest.frequency and latest.frequency >= 3.5 and ctr_median and (latest.ctr or 0) < ctr_median:
            reason = f"Frequency {latest.frequency:.1f} with CTR {latest.ctr or 0:.2f}% below the account median {ctr_median:.2f}%"
        if reason:
            out.append(
                {
                    "creative_id": creative_id,
                    "reason": reason,
                    "frequency": latest.frequency,
                    "ctr": latest.ctr,
                    "roas": latest.roas,
                    "spend": latest.spend,
                }
            )
    out.sort(key=lambda f: -(f.get("spend") or 0))
    return out[:6]


def _group_stats(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = str(row.get(key) or "").strip()
        if label:
            groups[label[:48]].append(row)
    out: dict[str, dict[str, Any]] = {}
    for label, items in groups.items():
        spend = sum(i.get("spend") or 0 for i in items)
        value = sum((i.get("roas") or 0) * (i.get("spend") or 0) for i in items)
        ctrs = [i["ctr"] for i in items if i.get("ctr") is not None]
        out[label] = {
            "ads": len(items),
            "spend": round(spend, 2),
            "roas": round(value / spend, 2) if spend else None,
            "ctr": round(sum(ctrs) / len(ctrs), 2) if ctrs else None,
        }
    return dict(sorted(out.items(), key=lambda kv: -(kv[1]["spend"] or 0))[:8])


def meta_summary(db: Session, store_id: str) -> dict[str, Any]:
    metas = db.scalars(select(MetaCreative).where(MetaCreative.store_id == store_id)).all()
    if not metas:
        return {"connected_data": False}
    snaps = _snapshots_by_creative(db, store_id)
    dna_rows = {
        d.meta_creative_row_id: d
        for d in db.scalars(select(CreativeDNA).where(CreativeDNA.store_id == store_id)).all()
        if d.meta_creative_row_id
    }
    rows: list[dict[str, Any]] = []
    for meta in metas:
        latest = (snaps.get(meta.id) or [None])[0]
        dna = dna_rows.get(meta.id)
        visual = _loads(dna.visual_dna_json, {}) if dna else {}
        copy_dna = _loads(dna.copy_dna_json, {}) if dna else {}
        placements = _loads(meta.placement_json, [])
        rows.append(
            {
                "id": meta.id,
                "ad_name": meta.ad_name,
                "adset": meta.adset_name,
                "campaign": meta.campaign_name,
                "headline": (meta.headline or "")[:120],
                "hook": (meta.primary_text or "").split("\n")[0][:140],
                "format": meta.format,
                "style": visual.get("style") or visual.get("overall_style"),
                "scene": visual.get("setting") or visual.get("background"),
                "hook_type": copy_dna.get("hook_type"),
                "tone": copy_dna.get("tone"),
                "human_presence": visual.get("human_presence"),
                "placement": ",".join(str(p) for p in placements[:2]) if isinstance(placements, list) else "",
                "destination_url": meta.destination_url,
                "spend": latest.spend if latest else None,
                "ctr": latest.ctr if latest else None,
                "roas": latest.roas if latest else None,
                "cpa": latest.cpa if latest else None,
                "frequency": latest.frequency if latest else None,
                "purchases": latest.purchases if latest else None,
                "clicks": latest.clicks if latest else None,
            }
        )
    spent = [r for r in rows if (r.get("spend") or 0) > 0]
    ranked = sorted(spent, key=lambda r: ((r.get("roas") or 0), (r.get("ctr") or 0)), reverse=True)
    spend_total = sum(r["spend"] or 0 for r in spent)
    value_total = sum((r.get("roas") or 0) * (r.get("spend") or 0) for r in spent)
    spend_median = median([r["spend"] for r in spent]) if spent else 0
    winners = [r for r in ranked if (r.get("spend") or 0) >= spend_median][:5]
    losers = [r for r in reversed(ranked) if (r.get("spend") or 0) >= spend_median][:4]

    def _brief(r: dict[str, Any]) -> dict[str, Any]:
        return {k: r.get(k) for k in ("id", "ad_name", "headline", "hook", "format", "style", "scene", "hook_type", "spend", "ctr", "roas", "frequency")}

    return {
        "connected_data": True,
        "ads": len(rows),
        "spend_total": round(spend_total, 2),
        "roas_overall": round(value_total / spend_total, 2) if spend_total else None,
        "winners": [_brief(r) for r in winners],
        "losers": [_brief(r) for r in losers],
        "by_style": _group_stats(spent, "style"),
        "by_hook_type": _group_stats(spent, "hook_type"),
        "by_format": _group_stats(spent, "format"),
        "by_scene": _group_stats(spent, "scene"),
        "by_placement": _group_stats(spent, "placement"),
        "by_adset": _group_stats(spent, "adset"),
        "fatigue": detect_fatigue(snaps),
        "clone_candidates": [_brief(r) for r in winners[:3] if (r.get("roas") or 0) > 0],
        "_rows": rows,
    }


def product_handle_clicks(meta_rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Meta link clicks and spend per product handle, via ad destination URLs."""
    out: dict[str, dict[str, float]] = defaultdict(lambda: {"clicks": 0.0, "spend": 0.0, "ads": 0})
    for row in meta_rows:
        match = _HANDLE.search(str(row.get("destination_url") or ""))
        if not match:
            continue
        handle = match.group(1).lower()
        out[handle]["clicks"] += row.get("clicks") or 0
        out[handle]["spend"] += row.get("spend") or 0
        out[handle]["ads"] += 1
    return out


# ------------------------------------------------------------------ memory, playbook, feedback


def playbook_summary(db: Session, store_id: str) -> dict[str, Any]:
    entries = db.scalars(
        select(AIAdsPlaybookEntry)
        .where(AIAdsPlaybookEntry.store_id == store_id)
        .order_by(desc(AIAdsPlaybookEntry.updated_at))
        .limit(80)
    ).all()
    return {
        "open_hypotheses": [
            {"id": e.id, "statement": e.statement, "evidence": _loads(e.evidence_json, [])[-3:]}
            for e in entries
            if e.kind == "hypothesis" and e.status == "open"
        ][:12],
        "resolved_hypotheses": [
            {"statement": e.statement, "status": e.status}
            for e in entries
            if e.kind == "hypothesis" and e.status in ("supported", "refuted", "inconclusive")
        ][:10],
        "learnings": [e.statement for e in entries if e.kind == "learning"][:10],
        "owner_preferences": [e.statement for e in entries if e.kind == "preference"][:15],
    }


def feedback_summary(db: Session, store_id: str) -> dict[str, Any]:
    rows = db.scalars(
        select(AIDirectorSuggestion)
        .where(AIDirectorSuggestion.store_id == store_id, AIDirectorSuggestion.status.in_(("GENERATED", "DISMISSED")))
        .order_by(desc(AIDirectorSuggestion.decided_at))
        .limit(150)
    ).all()
    by_type: dict[str, dict[str, int]] = defaultdict(lambda: {"accepted": 0, "dismissed": 0})
    for row in rows:
        by_type[row.ad_type]["accepted" if row.status == "GENERATED" else "dismissed"] += 1
    return {
        "by_ad_type": dict(by_type),
        "recent_dismissals": [
            {"concept": r.concept_name, "ad_type": r.ad_type, "angle": r.angle[:80], "reason": r.dismiss_reason[:160]}
            for r in rows
            if r.status == "DISMISSED"
        ][:12],
        "accepted_outcomes": [
            {"concept": r.concept_name, "ad_type": r.ad_type, "hypothesis": r.hypothesis[:140], "outcome": _loads(r.outcome_json, {})}
            for r in rows
            if r.status == "GENERATED" and r.outcome_json not in ("", "{}")
        ][:12],
    }


# ------------------------------------------------------------------ assemble


async def _fetch_shopify(store: Store, *, orders: bool) -> tuple[list[dict], list[dict], list[str]]:
    gaps: list[str] = []
    if not store.access_token_encrypted:
        return [], [], ["Shopify not connected: no sales or inventory data."]
    try:
        client = ShopifyClient(store.shop_domain, decrypt_value(store.access_token_encrypted))
    except Exception:
        return [], [], ["Shopify credentials unreadable: no sales or inventory data."]
    raw_products: list[dict] = []
    raw_orders: list[dict] = []
    try:
        raw_products = await asyncio.wait_for(client.list_products(limit=250, max_items=500), timeout=_PRODUCTS_TIMEOUT)
    except Exception as exc:
        logger.warning("director shopify products failed store=%s err=%s", store.id, exc)
        gaps.append("Shopify products timed out: inventory unknown, cached catalog used.")
    if orders:
        since = (datetime.now(UTC) - timedelta(days=SALES_WINDOW_DAYS)).isoformat()
        try:
            raw_orders = await asyncio.wait_for(
                client.list_all_orders_in_range(created_at_min=since, max_pages=8), timeout=_ORDERS_TIMEOUT
            )
        except Exception as exc:
            logger.warning("director shopify orders failed store=%s err=%s", store.id, exc)
            gaps.append("Shopify orders timed out: best sellers and AOV unavailable this run.")
    return raw_products, raw_orders, gaps


async def build_context(
    db: Session,
    store: Store,
    *,
    ads_settings: StoreAIAdsSettings | None,
    director: AIDirectorSettings | None,
    include_orders: bool = True,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble the snapshot. ``previous`` (last saved digest) fills sales data on fast paths."""
    now = datetime.now(UTC)
    try:
        today = now.astimezone(ZoneInfo(store.timezone or "UTC")).date()
    except Exception:
        today = now.date()
    lists = director_lists(director)
    threshold = director.low_stock_threshold if director else 3
    margin_floor = director.margin_floor_pct if director else None

    raw_products, raw_orders, gaps = await _fetch_shopify(store, orders=include_orders)
    inventory = inventory_from_products(raw_products)
    sales = summarize_orders(raw_orders, now=now) if raw_orders else None
    if sales is None and previous and previous.get("store_metrics"):
        prev_products = {p["id"]: p for p in previous.get("products") or []}
        sales = {
            "orders": previous["store_metrics"].get("orders_90d"),
            "revenue": previous["store_metrics"].get("revenue_90d"),
            "aov": previous["store_metrics"].get("aov_90d"),
            "by_product": {
                pid: {"units": p.get("units_90d") or 0, "revenue": p.get("revenue_90d") or 0, "units_30d": p.get("units_30d") or 0, "revenue_30d": 0}
                for pid, p in prev_products.items()
            },
            "by_type": previous.get("revenue_by_type") or {},
        }
        gaps.append("Sales figures reused from the last Director run.")

    meta = meta_summary(db, store.id)
    meta_rows = meta.pop("_rows", []) if meta.get("connected_data") else []
    clicks_by_handle = product_handle_clicks(meta_rows)
    unit_costs = margins_by_product(db, store.id)
    advertised_ids = {
        str(pid)
        for pid in db.scalars(
            select(CreativeAsset.product_id).where(
                CreativeAsset.store_id == store.id, CreativeAsset.status.in_(("PUBLISHED", "PAUSED"))
            )
        ).all()
        if pid
    }

    catalog = ShopifyProductCatalog(db, store, CreativeAssetStore(store.id))
    cached = {
        row.shopify_product_id: row
        for row in db.scalars(select(ShopifyCatalogProduct).where(ShopifyCatalogProduct.store_id == store.id)).all()
    }
    raw_by_id = {numeric_shopify_id(p.get("id")): p for p in raw_products}
    by_product = (sales or {}).get("by_product") or {}
    products: list[dict[str, Any]] = []
    for pid in list(dict.fromkeys(list(raw_by_id) + list(cached))):
        raw = raw_by_id.get(pid) or {}
        row = cached.get(pid)
        if raw and str(raw.get("status") or "active") != "active":
            continue
        title = raw.get("title") or (row.title if row else "")
        handle = (raw.get("handle") or (row.handle if row else "") or "").lower()
        price = _num(((raw.get("variants") or [{}])[0]).get("price")) if raw else (row.price if row else None)
        created = raw.get("created_at") or (row.created_at.isoformat() if row and row.created_at else None)
        try:
            created_at = _aware(datetime.fromisoformat(str(created).replace("Z", "+00:00"))) if created else None
        except ValueError:
            created_at = None
        qty = inventory.get(pid)
        stats = by_product.get(pid) or {}
        cost = unit_costs.get(pid)
        margin = round((price - cost) / price * 100, 1) if price and cost else None
        clicks = clicks_by_handle.get(handle, {}) if handle else {}
        units = stats.get("units") or 0
        products.append(
            {
                "id": pid,
                "title": title,
                "handle": handle,
                "product_type": raw.get("product_type") or "",
                "tags": str(raw.get("tags") or "")[:120],
                "price": price,
                "inventory": qty,
                "stock": stock_status(qty, threshold),
                "units_90d": units,
                "revenue_90d": stats.get("revenue") or 0,
                "units_30d": stats.get("units_30d") or 0,
                "margin_pct": margin,
                "below_margin_floor": bool(margin is not None and margin_floor is not None and margin < margin_floor),
                "new_arrival": bool(created_at and (now - created_at).days <= NEW_ARRIVAL_DAYS),
                "meta_clicks": round(clicks.get("clicks") or 0),
                "meta_ads": int(clicks.get("ads") or 0),
                "high_clicks_low_orders": bool((clicks.get("clicks") or 0) >= 100 and units <= 1),
                "never_advertised": not clicks and pid not in advertised_ids,
                "has_photos": catalog.has_usable_photos(pid) if row else bool(raw.get("images")),
                "priority": pid in lists["priority"],
                "excluded": pid in lists["excluded"],
            }
        )
    products.sort(key=lambda p: (not p["priority"], -(p["revenue_90d"] or 0), -(p["units_90d"] or 0)))
    revenue_by_type: dict[str, float] = defaultdict(float)
    for p in products:
        if p["product_type"] and p["revenue_90d"]:
            revenue_by_type[p["product_type"]] += p["revenue_90d"]
    if not revenue_by_type:
        revenue_by_type.update((sales or {}).get("by_type") or {})

    if not raw_orders and include_orders and not (previous and previous.get("store_metrics")):
        gaps.append("No orders in the last 90 days (or orders unavailable): best sellers unknown.")
    if not unit_costs:
        gaps.append("No product costs entered in Analytics: margins unknown, margin floor not enforced.")
    if not any(p["inventory"] is not None for p in products):
        gaps.append("Inventory not tracked in Shopify (or unavailable): stock checks could not run.")
    gaps.append("Storefront sessions are not in the Shopify Admin API: 'high traffic, low conversion' uses Meta link clicks vs orders.")
    if not meta.get("connected_data"):
        gaps.append("No Meta ads imported: winners, fatigue, and style performance unavailable.")

    lang = (director.copy_language if director else "auto") or "auto"
    return {
        "generated_at": now.isoformat(),
        "today": today.isoformat(),
        "store": {"name": store.name, "currency": store.currency, "timezone": store.timezone, "market": "Canada / Quebec"},
        "brand": {
            "brand_style": (ads_settings.brand_style if ads_settings else "") or "",
            "default_audience": (ads_settings.default_audience if ads_settings else "") or "",
            "language": lang,
            "never_do": lists["never_do"],
            "aggressiveness": (director.aggressiveness if director else "balanced") or "balanced",
        },
        "confirmed_offers": lists["offers"],
        "store_metrics": {
            "orders_90d": (sales or {}).get("orders"),
            "revenue_90d": (sales or {}).get("revenue"),
            "aov_90d": (sales or {}).get("aov"),
        },
        "revenue_by_type": {k: round(v, 2) for k, v in sorted(revenue_by_type.items(), key=lambda kv: -kv[1])},
        "products": products[:60],
        "meta": meta,
        "calendar": {"upcoming": upcoming_occasions(today), "evergreen": EVERGREEN},
        "playbook": playbook_summary(db, store.id),
        "feedback": feedback_summary(db, store.id),
        "memory": memory_digest(build_memory(db, store.id)),
        "data_gaps": gaps,
    }


def prompt_view(context: dict[str, Any], *, max_products: int = 25) -> dict[str, Any]:
    """Trim the snapshot to what the model needs; excluded / out-of-stock products are marked, not hidden."""
    view = dict(context)
    view["products"] = [
        {k: v for k, v in p.items() if k not in ("handle",)}
        for p in (context.get("products") or [])[:max_products]
    ]
    return view
