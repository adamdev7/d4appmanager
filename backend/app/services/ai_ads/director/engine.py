"""Director engine: ideation -> guardrails + novelty -> critique -> selection, brief, alerts, challenge.

The model proposes and critiques; this module enforces the hard rules (stock, exclusions,
margin floor, never-do list, offers, testimonial and claim safety) so a clever-sounding idea
can never slip past them.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from typing import Any

from app.services.ai_ads.ad_types import AD_TYPES, clamp_media, get_ad_type, registry_payload
from app.services.ai_ads.director.costs import estimate_generation_usd
from app.services.ai_ads.director.memory import DUPLICATE_THRESHOLD, novelty, similarity
from app.services.ai_ads.director.prompts import CHALLENGE, CRITIQUE, IDEATION
from app.services.ai_ads.director.schemas import (
    ChallengeResult,
    CritiqueResult,
    DirectorConcept,
    IdeationResult,
)

logger = logging.getLogger(__name__)

AGGRESSIVENESS = {
    # temperature, wildcards on the board, weights (performance, brand, novelty, cost, risk penalty)
    "safe": {"temperature": 0.6, "wildcards": 1, "weights": (0.45, 0.25, 0.10, 0.10, 0.25)},
    "balanced": {"temperature": 0.85, "wildcards": 1, "weights": (0.35, 0.20, 0.20, 0.10, 0.15)},
    "bold": {"temperature": 1.05, "wildcards": 2, "weights": (0.25, 0.15, 0.35, 0.10, 0.08)},
}
BOARD_MIN = 6
BOARD_MAX = 10
PER_TYPE_CAP = 3
PER_PRODUCT_CAP = 3
TEST_VARIABLES = ("hook", "angle", "visual", "format", "audience", "offer", "emotion")

_TESTIMONIAL = re.compile(
    r"(i'?ve (worn|had|owned|been wearing)|my honest review|\b\d(\.\d)? ?stars?\b|★|customers (say|love)|"
    r"real (customer|review)|verified (buyer|purchase)|j'?le porte depuis|mon avis honnête|les clientes? (disent|adorent))",
    re.IGNORECASE,
)
_OFFER_WORDS = re.compile(
    r"(\d+ ?% ?(off|de rabais)|\bsale\b|\bsolde|free shipping|livraison gratuite|\bfree gift\b|cadeau gratuit|"
    r"gift wrap|emballage cadeau|engrav|gravure|bundle|\bbogo\b|coupon|promo code|code promo|discount|rabais)",
    re.IGNORECASE,
)
_UNSUPPORTED = re.compile(
    r"(\bships? in\b|delivered in|livré en|warranty|garantie|hypoallergenic|hypoallergénique|tarnish|"
    r"ne ternit|waterproof|imperméable|\b1[048]k\b|sterling|argent sterling|solid gold|or massif|"
    r"#1|number one|numéro un|best[- ]?seller|meilleur vendeur|thousands of|des milliers)",
    re.IGNORECASE,
)


def aggressiveness_config(level: str | None) -> dict[str, Any]:
    return AGGRESSIVENESS.get(str(level or "balanced").lower(), AGGRESSIVENESS["balanced"])


# ------------------------------------------------------------------ guardrails


def _concept_text(concept: dict[str, Any]) -> str:
    script = concept.get("script") or {}
    lines = " ".join(script.get("lines") or []) if isinstance(script, dict) else ""
    first = script.get("first_two_seconds", "") if isinstance(script, dict) else ""
    return " ".join(
        str(concept.get(k) or "") for k in ("concept_name", "hook", "angle", "setting")
    ) + f" {first} {lines}"


def guard_concept(
    concept: dict[str, Any],
    context: dict[str, Any],
    product_texts: dict[str, str],
) -> tuple[str | None, list[dict[str, str]]]:
    """(blocked_reason, flags). Blocked concepts never reach the board."""
    flags: list[dict[str, str]] = []
    products = {p["id"]: p for p in context.get("products") or []}
    product = products.get(str(concept.get("product_id") or ""))
    if not product:
        return "Product not found in the catalog.", flags
    if product.get("excluded"):
        return f"{product['title']} is on your exclude list.", flags
    if product.get("stock") == "out":
        return f"{product['title']} is out of stock.", flags
    if product.get("stock") == "low":
        return f"{product['title']} is low on stock ({product.get('inventory')} left).", flags
    if product.get("below_margin_floor"):
        return f"{product['title']} is below your margin floor ({product.get('margin_pct')}%).", flags
    if not product.get("has_photos"):
        flags.append({"code": "needs_photos", "message": "Add product photos on Generate before this can render."})

    text = _concept_text(concept)
    lowered = text.lower()
    for rule in (context.get("brand") or {}).get("never_do") or []:
        rule_l = rule.lower().strip()
        if rule_l and (rule_l in lowered or similarity(rule_l, text) >= 0.5):
            return f"Matches your never-do rule: “{rule}”.", flags

    if _TESTIMONIAL.search(text):
        return "Reads like a real customer testimonial; the AI character cannot pose as a customer.", flags

    confirmed = {str(o.get("id")): o for o in context.get("confirmed_offers") or []}
    confirmed_text = " ".join(f"{o.get('label', '')} {o.get('details', '')}" for o in confirmed.values()).lower()
    for oid in concept.get("offer_ids") or []:
        if str(oid) not in confirmed:
            flags.append({"code": "requires_confirmation", "message": f"Uses an offer ({oid}) you have not confirmed."})
    for match in {m.group(0).lower() for m in _OFFER_WORDS.finditer(text)}:
        if match not in confirmed_text:
            flags.append(
                {"code": "requires_confirmation", "message": f"Mentions “{match}” — requires your confirmation that this offer exists."}
            )

    facts = (product_texts.get(product["id"]) or "").lower()
    claims = [str(c) for c in concept.get("claims") or []]
    for match in {m.group(0).lower() for m in _UNSUPPORTED.finditer(text + " " + " ".join(claims))}:
        supported = match in facts
        if match.startswith(("best", "meilleur", "#1", "number one", "numéro")):
            top_units = sorted((p.get("units_90d") or 0 for p in products.values()), reverse=True)[:3]
            supported = bool(top_units and (product.get("units_90d") or 0) >= top_units[-1] > 0)
        if not supported:
            flags.append({"code": "unsupported_claim", "message": f"“{match}” is not backed by product or sales data; remove it or confirm."})
    return None, flags


def _clean_concept(raw: DirectorConcept | dict[str, Any]) -> dict[str, Any]:
    data = raw.model_dump() if isinstance(raw, DirectorConcept) else dict(raw)
    ad_type = get_ad_type(data.get("ad_type"))
    data["ad_type"] = ad_type.id
    data["image_count"], data["video_count"] = clamp_media(ad_type, data.get("image_count"), data.get("video_count"))
    data["funnel"] = "retargeting" if str(data.get("funnel") or "").lower().startswith("retarget") else "prospecting"
    data["kind"] = data.get("kind") if data.get("kind") in ("new", "refresh", "clone") else "new"
    variable = str(data.get("test_variable") or "").lower()
    data["test_variable"] = variable if variable in TEST_VARIABLES else "angle"
    data["estimated_cost_usd"] = estimate_generation_usd(data["image_count"], data["video_count"])
    return data


def screen_candidates(
    ideas: list[DirectorConcept | dict[str, Any]],
    context: dict[str, Any],
    memory: list[dict[str, Any]],
    product_texts: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Guardrails + "don't repeat" check. Returns (candidates, rejected with reasons)."""
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in ideas:
        concept = _clean_concept(raw)
        blocked, flags = guard_concept(concept, context, product_texts)
        if blocked:
            rejected.append({"concept_name": concept.get("concept_name"), "reason": blocked})
            continue
        score, closest = novelty(concept, memory)
        if score < 1 - DUPLICATE_THRESHOLD:
            rejected.append(
                {
                    "concept_name": concept.get("concept_name"),
                    "reason": f"Too close to a past ad: “{(closest or {}).get('hook') or (closest or {}).get('concept')}”.",
                }
            )
            continue
        for other in candidates:
            if similarity(concept.get("hook"), other.get("hook")) >= DUPLICATE_THRESHOLD:
                blocked = "Duplicate of another idea in this batch."
                break
        if blocked:
            rejected.append({"concept_name": concept.get("concept_name"), "reason": blocked})
            continue
        concept["novelty"] = score
        concept["flags"] = flags
        candidates.append(concept)
    return candidates, rejected


# ------------------------------------------------------------------ scoring & selection


def score_concept(review: dict[str, Any], aggressiveness: str) -> float:
    perf_w, brand_w, novelty_w, cost_w, risk_w = aggressiveness_config(aggressiveness)["weights"]

    def _v(key: str, default: int = 3) -> float:
        try:
            return max(1, min(5, int(review.get(key, default)))) / 5
        except (TypeError, ValueError):
            return default / 5

    return round(
        perf_w * _v("predicted_performance")
        + brand_w * _v("brand_fit")
        + novelty_w * _v("novelty")
        + cost_w * _v("production_cost")
        - risk_w * _v("risk", 2),
        4,
    )


def apply_reviews(candidates: list[dict[str, Any]], critique: CritiqueResult | None, aggressiveness: str) -> list[dict[str, Any]]:
    reviews = {r.index: r.model_dump() for r in (critique.reviews if critique else [])}
    kept: list[dict[str, Any]] = []
    for idx, concept in enumerate(candidates):
        review = reviews.get(idx) or {"novelty": round(1 + 4 * concept.get("novelty", 0.5))}
        if review.get("keep") is False:
            continue
        # Measured novelty (vs past ads) and the model's opinion are averaged.
        measured = 1 + 4 * float(concept.get("novelty") or 0.5)
        review["novelty"] = round((float(review.get("novelty", 3)) + measured) / 2, 1)
        if review.get("improved_hook"):
            concept["original_hook"] = concept.get("hook")
            concept["hook"] = review["improved_hook"]
        concept["review"] = review
        concept["score"] = score_concept(review, aggressiveness)
        concept["index"] = idx
        kept.append(concept)
    kept.sort(key=lambda c: -c["score"])
    return kept


def select_board(scored: list[dict[str, Any]], aggressiveness: str) -> list[dict[str, Any]]:
    """6-10 ideas, diverse by ad type and product, with the configured number of wild cards."""
    wild_target = aggressiveness_config(aggressiveness)["wildcards"]
    board: list[dict[str, Any]] = []
    types: Counter[str] = Counter()
    products: Counter[str] = Counter()

    def _fits(c: dict[str, Any]) -> bool:
        return types[c["ad_type"]] < PER_TYPE_CAP and products[c.get("product_id") or ""] < PER_PRODUCT_CAP

    def _add(c: dict[str, Any]) -> None:
        board.append(c)
        types[c["ad_type"]] += 1
        products[c.get("product_id") or ""] += 1

    wilds = [c for c in scored if c.get("is_wildcard")]
    for c in wilds[:wild_target]:
        if _fits(c):
            _add(c)
    for c in scored:
        if len(board) >= BOARD_MAX:
            break
        if c in board or c.get("is_wildcard"):
            continue
        if _fits(c):
            _add(c)
    for c in scored:
        if len(board) >= BOARD_MIN:
            break
        if c not in board and not c.get("is_wildcard"):
            _add(c)
    return board


def build_brief(
    board: list[dict[str, Any]],
    critique: CritiqueResult | None,
    *,
    remaining_usd: float | None,
    max_images: int,
    max_videos: int,
) -> dict[str, Any]:
    """Items to produce this week: the critic's picks first, then best scores, within budget."""
    by_index = {c["index"]: c for c in board}
    picks = [(p.index, p.reason) for p in (critique.brief.picks if critique else []) if p.index in by_index]
    picked = {i for i, _ in picks}
    # Wild cards stay on the idea board for the owner unless the critic put them in the brief.
    ordered = picks + [(c["index"], "") for c in board if c["index"] not in picked and not c.get("is_wildcard")]
    items: list[dict[str, Any]] = []
    spent = 0.0
    images = videos = 0
    for idx, reason in ordered:
        concept = by_index[idx]
        if any(f["code"] in ("requires_confirmation", "needs_photos", "unsupported_claim") for f in concept.get("flags") or []):
            continue
        img, vid = concept["image_count"], concept["video_count"]
        if images + img > max_images:
            img = max(0, max_images - images)
        if videos + vid > max_videos:
            vid = max(0, max_videos - videos)
        if img + vid == 0:
            continue
        cost = estimate_generation_usd(img, vid)
        if remaining_usd is not None and spent + cost > remaining_usd:
            continue
        spent += cost
        images += img
        videos += vid
        items.append({"index": idx, "image_count": img, "video_count": vid, "reason": reason or concept.get("why", ""), "estimated_cost_usd": cost})
    brief = critique.brief if critique else None
    return {
        "headline": (brief.headline if brief else "") or (f"Make {len(items)} concepts this week" if items else "Nothing to produce this week"),
        "summary": (brief.summary if brief else "") or "",
        "testing_plan": (brief.testing_plan if brief else "") or "",
        "naming_convention": (brief.naming_convention if brief else "") or "LUX | {week} | {product} | {ad type} | {variable}-{A/B}",
        "budget_note": (brief.budget_note if brief else "") or "",
        "items": items,
        "total_images": images,
        "total_videos": videos,
        "estimated_cost_usd": round(spent, 2),
    }


# ------------------------------------------------------------------ alerts & checks


def build_alerts(context: dict[str, Any]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    meta = context.get("meta") or {}
    for f in meta.get("fatigue") or []:
        alerts.append({"type": "fatigue", "level": "warning", "title": "Creative fatigue", "message": f["reason"], "creative_id": f["creative_id"]})
    for c in meta.get("clone_candidates") or []:
        alerts.append(
            {
                "type": "winner",
                "level": "info",
                "title": "Winner worth cloning",
                "message": f"“{c.get('headline') or c.get('ad_name')}” — ROAS {c.get('roas')}, CTR {c.get('ctr')}%. New hooks, scenes, and formats on the same angle.",
                "creative_id": c.get("id"),
            }
        )
    sellers = sorted(context.get("products") or [], key=lambda p: -(p.get("units_90d") or 0))[:8]
    for p in sellers:
        if p.get("units_90d") and p.get("stock") in ("low", "out"):
            alerts.append(
                {
                    "type": "stock",
                    "level": "warning",
                    "title": "Best seller low on stock" if p["stock"] == "low" else "Best seller out of stock",
                    "message": f"{p['title']}: {p.get('inventory')} left, {p['units_90d']} sold in 90 days. Not promoted until restocked.",
                    "product_id": p["id"],
                }
            )
    for occ in (context.get("calendar") or {}).get("upcoming") or []:
        if occ["window"] in ("prep_now", "in_market"):
            alerts.append(
                {
                    "type": "occasion",
                    "level": "info",
                    "title": f"{occ['name']} in {occ['days_until']} days" if occ["days_until"] else f"{occ['name']} is live",
                    "message": "Produce now so ads are learning before the peak." if occ["window"] == "prep_now" else "In market: last-minute and countdown angles.",
                    "occasion": occ["key"],
                }
            )
    return alerts


def request_checks(request: dict[str, Any], context: dict[str, Any], memory: list[dict[str, Any]]) -> list[str]:
    """Deterministic, data-backed notes about a manual request."""
    notes: list[str] = []
    products = {p["id"]: p for p in context.get("products") or []}
    product = products.get(str(request.get("product_id") or ""))
    if product:
        if product.get("stock") == "out":
            notes.append(f"{product['title']} is out of stock in Shopify.")
        elif product.get("stock") == "low":
            notes.append(f"{product['title']} is low on stock ({product.get('inventory')} left).")
        if product.get("excluded"):
            notes.append(f"{product['title']} is on your Director exclude list.")
        if product.get("below_margin_floor"):
            notes.append(f"{product['title']} margin is {product.get('margin_pct')}%, under your floor.")
    by_style = (context.get("meta") or {}).get("by_style") or {}
    ranked = [(name, s) for name, s in by_style.items() if s.get("roas") and (s.get("spend") or 0) > 0]
    if ranked:
        best_name, best = max(ranked, key=lambda kv: kv[1]["roas"])
        for style in request.get("styles") or []:
            match = next((s for name, s in ranked if name.lower().replace(" ", "_").startswith(str(style).lower()[:5])), None)
            if match and best_name.lower()[:5] != str(style).lower()[:5] and best["roas"] >= 2 * match["roas"]:
                notes.append(f"{best_name} ads are beating {style} about {best['roas'] / match['roas']:.1f}:1 on ROAS (spend-weighted).")
    hook_text = " ".join(str(request.get(k) or "") for k in ("audience", "brand_style"))
    if hook_text.strip():
        weak = [
            m for m in memory
            if similarity(hook_text, f"{m.get('hook')} {m.get('angle')}") >= 0.35
            and (m.get("performance") or {}).get("ctr") is not None
        ]
        ctr_all = [m["performance"]["ctr"] for m in memory if (m.get("performance") or {}).get("ctr")]
        if len(weak) >= 3 and ctr_all:
            avg = sum(m["performance"]["ctr"] for m in weak) / len(weak)
            med = sorted(ctr_all)[len(ctr_all) // 2]
            if avg < med * 0.75:
                notes.append(f"A similar angle ran {len(weak)} times with CTR {avg:.2f}% vs {med:.2f}% median.")
    return notes


# ------------------------------------------------------------------ model calls


class DirectorEngine:
    def __init__(self, client: Any, *, model: str, critique_model: str | None = None) -> None:
        self.client = client
        self.model = model
        self.critique_model = critique_model or model

    async def ideate(self, view: dict[str, Any], *, count: int, aggressiveness: str) -> IdeationResult:
        cfg = aggressiveness_config(aggressiveness)
        payload = {
            "ad_types": registry_payload(),
            "experimentation": aggressiveness,
            "count": count,
            **view,
        }
        user = (
            f"Return {count} concepts, diverse across ad types, products, angles, emotions, and funnels. "
            f"Experimentation level: {aggressiveness} (safe = proven patterns, bold = more unexplored ideas).\n\n"
            f"{json.dumps(payload, default=str)[:30000]}"
        )
        result = await self.client.complete_json(
            system=IDEATION,
            user=user,
            schema=IdeationResult,
            model=self.model,
            temperature=cfg["temperature"],
            operation="director_ideation",
        )
        assert isinstance(result, IdeationResult)
        return result

    async def critique(
        self, view: dict[str, Any], candidates: list[dict[str, Any]], budget: dict[str, Any]
    ) -> CritiqueResult:
        slim = [
            {
                "index": i,
                **{k: c.get(k) for k in (
                    "concept_name", "kind", "ad_type", "product_id", "image_count", "video_count", "hook",
                    "hook_type", "angle", "emotion", "funnel", "occasion", "why", "hypothesis",
                    "test_variable", "is_wildcard", "estimated_cost_usd", "novelty", "flags",
                )},
            }
            for i, c in enumerate(candidates)
        ]
        payload = {
            "candidates": slim,
            "budget": budget,
            "playbook": view.get("playbook"),
            "feedback": view.get("feedback"),
            "meta": {k: (view.get("meta") or {}).get(k) for k in ("winners", "losers", "by_style", "by_hook_type", "by_format", "fatigue")},
            "calendar": view.get("calendar"),
            "brand": view.get("brand"),
            "store_metrics": view.get("store_metrics"),
            "currency": (view.get("store") or {}).get("currency"),
        }
        result = await self.client.complete_json(
            system=CRITIQUE,
            user=f"Review every candidate, then write the brief.\n\n{json.dumps(payload, default=str)[:30000]}",
            schema=CritiqueResult,
            model=self.critique_model,
            temperature=0.2,
            operation="director_critique",
        )
        assert isinstance(result, CritiqueResult)
        return result

    async def challenge(
        self, view: dict[str, Any], request: dict[str, Any], checks: list[str]
    ) -> ChallengeResult:
        products = {p["id"]: p for p in view.get("products") or []}
        payload = {
            "request": request,
            "requested_product": products.get(str(request.get("product_id") or "")),
            "checks": checks,
            "ad_types": [t.id for t in AD_TYPES.values()],
            "meta": {k: (view.get("meta") or {}).get(k) for k in ("winners", "losers", "by_style", "by_hook_type", "by_format")},
            "top_products": (view.get("products") or [])[:10],
            "calendar": (view.get("calendar") or {}).get("upcoming"),
            "playbook": view.get("playbook"),
            "feedback": view.get("feedback"),
            "memory": (view.get("memory") or [])[:20],
            "brand": view.get("brand"),
        }
        result = await self.client.complete_json(
            system=CHALLENGE,
            user=json.dumps(payload, default=str)[:20000],
            schema=ChallengeResult,
            model=self.critique_model,
            temperature=0.2,
            operation="director_challenge",
        )
        assert isinstance(result, ChallengeResult)
        return result
