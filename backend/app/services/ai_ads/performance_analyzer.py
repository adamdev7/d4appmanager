from __future__ import annotations

from typing import Any

from app.integrations.meta.client import (
    parse_meta_cpa,
    parse_meta_float,
    parse_meta_link_clicks,
    parse_meta_link_cpc,
    parse_meta_link_ctr,
    parse_meta_purchase_roas,
    parse_meta_purchase_value,
    parse_meta_purchases,
    parse_meta_video_2s_plays,
    parse_meta_video_3s_plays,
)
from app.services.ai_ads.schemas import PerformanceSummary


def _opt_float(row: dict, key: str) -> float | None:
    if key not in row or row.get(key) in (None, ""):
        return None
    try:
        return float(row.get(key))
    except (TypeError, ValueError):
        return None


def normalize_insight_row(
    row: dict[str, Any],
    *,
    since: str | None = None,
    until: str | None = None,
) -> PerformanceSummary:
    """Normalize Meta insights. Missing metrics stay None. Never invent values."""
    impressions = _opt_float(row, "impressions")
    spend = _opt_float(row, "spend")
    clicks = None
    link_clicks = parse_meta_link_clicks(row) if row else 0.0
    if "inline_link_clicks" in row or "clicks" in row or link_clicks:
        clicks = link_clicks if link_clicks else _opt_float(row, "clicks")

    purchases = parse_meta_purchases(row.get("actions")) if row.get("actions") else None
    if purchases == 0 and not row.get("actions"):
        purchases = None
    conversion_value = parse_meta_purchase_value(row.get("action_values")) if row.get("action_values") else None
    roas = parse_meta_purchase_roas(row.get("purchase_roas")) if row.get("purchase_roas") else None
    if roas == 0 and not row.get("purchase_roas"):
        roas = None

    cpa = None
    if purchases and purchases > 0:
        cpa = parse_meta_cpa(row, purchases)
    elif row.get("cost_per_action_type") or row.get("cost_per_result"):
        parsed = parse_meta_cpa(row, purchases or 0)
        cpa = parsed if parsed else None

    ctr = None
    if impressions and impressions > 0:
        ctr = parse_meta_link_ctr(row, impressions)
    cpc = None
    if spend is not None and clicks:
        cpc = parse_meta_link_cpc(row, spend, clicks)
    elif "cpc" in row:
        cpc = parse_meta_float(row, "cpc") or None

    video_views = None
    plays = parse_meta_video_3s_plays(row)
    if plays or row.get("video_play_actions"):
        video_views = plays

    insufficient = not impressions or impressions <= 0
    tr = row.get("date_start") or since
    te = row.get("date_stop") or until
    return PerformanceSummary(
        impressions=impressions,
        reach=_opt_float(row, "reach"),
        clicks=clicks,
        spend=spend,
        ctr=ctr,
        cpc=cpc,
        cpm=_opt_float(row, "cpm"),
        purchases=purchases,
        cpa=cpa,
        conversion_value=conversion_value,
        roas=roas,
        video_views=video_views,
        video_watch={
            "thruplay": parse_meta_video_2s_plays(row) or None,
            "video_3s": plays or None,
        },
        frequency=_opt_float(row, "frequency"),
        date_range_start=str(tr) if tr else None,
        date_range_end=str(te) if te else None,
        insufficient_data=bool(insufficient),
    )


def percentile_ranks(summaries: list[PerformanceSummary]) -> dict[int, dict[str, float]]:
    """Compute percentiles from actual values only. Omit a metric if fewer than 2 values exist."""

    def rank(values: list[tuple[int, float]], invert: bool = False) -> dict[int, float]:
        if len(values) < 2:
            return {}
        ordered = sorted(values, key=lambda x: x[1], reverse=invert)
        n = len(ordered)
        out: dict[int, float] = {}
        for i, (idx, _) in enumerate(ordered):
            out[idx] = round(i / (n - 1), 4)
        return out

    ctrs = [(i, s.ctr) for i, s in enumerate(summaries) if s.ctr is not None]
    roas = [(i, s.roas) for i, s in enumerate(summaries) if s.roas is not None]
    cpas = [(i, s.cpa) for i, s in enumerate(summaries) if s.cpa is not None]
    spends = [(i, s.spend) for i, s in enumerate(summaries) if s.spend is not None]
    ctr_r = rank(ctrs)
    roas_r = rank(roas)
    cpa_r = rank(cpas, invert=True)  # lower CPA is better
    spend_r = rank(spends)
    out: dict[int, dict[str, float]] = {}
    for i in range(len(summaries)):
        d: dict[str, float] = {}
        if i in ctr_r:
            d["ctr_percentile"] = ctr_r[i]
        if i in roas_r:
            d["roas_percentile"] = roas_r[i]
        if i in cpa_r:
            d["cpa_percentile"] = cpa_r[i]
        if i in spend_r:
            d["spend_percentile"] = spend_r[i]
        if d:
            out[i] = d
    return out


def split_performance_groups(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Split into winning / average / losing using available ROAS then CTR. Requires real data."""
    scored: list[tuple[float, dict]] = []
    for item in items:
        perf = item.get("performance") or {}
        if perf.get("insufficient_data"):
            continue
        roas = perf.get("roas")
        ctr = perf.get("ctr")
        spend = perf.get("spend") or 0
        if spend is not None and spend <= 0:
            continue
        score = None
        if roas is not None:
            score = float(roas)
        elif ctr is not None:
            score = float(ctr)
        if score is None:
            continue
        scored.append((score, item))
    if len(scored) < 3:
        return {"winning": [], "average": [i for _, i in scored], "losing": [], "insufficient": True}
    scored.sort(key=lambda x: x[0], reverse=True)
    n = len(scored)
    top_n = max(1, n // 3)
    winning = [i for _, i in scored[:top_n]]
    losing = [i for _, i in scored[-top_n:]]
    average = [i for _, i in scored[top_n : n - top_n]]
    return {"winning": winning, "average": average, "losing": losing, "insufficient": False}
