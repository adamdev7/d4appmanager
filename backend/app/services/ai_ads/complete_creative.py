from __future__ import annotations

from typing import Any

from app.services.ai_ads.schemas import (
    AICreativeScore,
    AIScoreBreakdown,
    CreativeConceptModel,
    ProductContext,
    VideoScene,
    VideoSpec,
)

MAX_IMAGE_ADS = 8
MAX_VIDEO_ADS = 4


def clamp_generation_counts(images: int, videos: int) -> tuple[int, int]:
    return max(0, min(int(images or 0), MAX_IMAGE_ADS)), max(0, min(int(videos or 0), MAX_VIDEO_ADS))


def compact_product(product: ProductContext) -> dict[str, Any]:
    image = product.images[0].src if product.images else None
    return {
        "title": product.title,
        "description": (product.description or "")[:500],
        "price": product.price,
        "currency": product.currency,
        "url": product.product_url,
        "image": image,
        "restrictions": (product.restrictions or [])[:6],
    }


def compact_meta_item(item: dict[str, Any]) -> dict[str, Any]:
    copy = item.get("copy") or {}
    dna = item.get("dna") or {}
    visual = dna.get("visual") or {}
    copy_dna = dna.get("copy") or {}
    perf = item.get("performance") or {}
    return {
        "id": item.get("id"),
        "campaign": item.get("campaign_name") or item.get("ad_name"),
        "format": item.get("format"),
        "headline": (copy.get("headline") or item.get("headline") or "")[:160],
        "primary_text": (copy.get("primary_text") or "")[:280],
        "cta": copy.get("cta") or item.get("cta"),
        "style": visual.get("style") or visual.get("overall_style"),
        "composition": visual.get("composition"),
        "hook_type": copy_dna.get("hook_type"),
        "tone": copy_dna.get("tone"),
        "roas": perf.get("roas"),
        "ctr": perf.get("ctr"),
        "cpa": perf.get("cpa"),
        "spend": perf.get("spend"),
        "purchases": perf.get("purchases"),
    }


def product_reference_urls(product: ProductContext) -> list[str]:
    return [img.src for img in (product.images or []) if getattr(img, "src", None)][:1]


def winning_style_notes(winners: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in winners[:6]:
        for key in ("style", "composition", "hook_type", "headline"):
            value = item.get(key)
            if value and str(value) not in parts:
                parts.append(str(value)[:120])
    return "; ".join(parts[:8])


def build_image_prompt(
    *,
    product: ProductContext,
    visual_direction: str,
    image_prompt: str = "",
    brand_style: str = "",
    winning_notes: str = "",
    aspect_ratio: str = "4:5",
    placement: str = "feed",
) -> str:
    prompt = (image_prompt or visual_direction or "").strip()
    if not prompt:
        prompt = f"Photorealistic advertising photo of {product.title}, product clearly visible."
    extras = [
        f"Product: {product.title}.",
        f"Keep product appearance faithful to '{product.title}'. Do not invent materials or logos.",
    ]
    desc = (product.description or "").strip()
    if desc:
        extras.append(f"Known product facts only: {desc[:240]}")
    if winning_notes:
        extras.append(f"Improve styles associated with stronger Meta ads: {winning_notes[:400]}")
    if brand_style:
        extras.append(f"Brand look: {brand_style[:160]}")
    extras.append(
        f"Finished Meta {placement} advertisement still, aspect {aspect_ratio}. "
        "Photorealistic product hero, generous safe margins for headline overlay, "
        "single product, no fake UI, no fake reviews, no watermarks, no extra logos, "
        "no unreadable text baked into the image."
    )
    return f"{prompt}\n\n" + " ".join(extras)


def build_video_prompt(
    *,
    product: ProductContext,
    spec: VideoSpec,
    brand_style: str = "",
    winning_notes: str = "",
) -> str:
    scenes = []
    for scene in spec.scenes[:6]:
        bit = (scene.visual or "").strip()
        if bit:
            scenes.append(bit[:180])
    shot_list = " Then ".join(scenes) if scenes else (spec.hook or product.title)
    parts = [
        f"Vertical Meta Reels / Stories advertisement, photorealistic, product is {product.title}.",
        f"Hook: {spec.hook or product.title}.",
        f"Shot list: {shot_list}.",
        "Keep the real product recognizable. Smooth camera, natural light, no fake UI, no watermarks.",
        f"End on a clear product shot and the call to action {(spec.cta or 'SHOP NOW').replace('_', ' ')}.",
    ]
    desc = (product.description or "").strip()
    if desc:
        parts.append(f"Known product facts only: {desc[:220]}")
    if winning_notes:
        parts.append(f"Match stronger Meta ad styles: {winning_notes[:240]}")
    if brand_style:
        parts.append(f"Brand look: {brand_style[:140]}")
    if spec.voice_direction:
        parts.append(f"Voice: {spec.voice_direction[:120]}")
    if spec.music_direction:
        parts.append(f"Music: {spec.music_direction[:120]}")
    return " ".join(parts)


def video_spec_from_concept(
    concept: CreativeConceptModel,
    product: ProductContext,
    *,
    aspect_ratio: str = "9:16",
) -> VideoSpec:
    scenes = list(concept.scenes or [])
    if not scenes:
        scenes = [
            VideoScene(
                duration=3,
                visual=f"Open on {product.title}. {(concept.visual_direction or '')[:160]}",
                voiceover=concept.hook or product.title,
                text_overlay=concept.hook or product.title,
            ),
            VideoScene(
                duration=8,
                visual=concept.visual_direction or f"Show {product.title} in use.",
                voiceover=(concept.primary_text or product.description or product.title)[:180],
                text_overlay=concept.headline or product.title,
            ),
            VideoScene(
                duration=4,
                visual=f"Clear product shot of {product.title} and call to action.",
                voiceover=(concept.cta or "Shop now").replace("_", " "),
                text_overlay=(concept.cta or "SHOP NOW").replace("_", " "),
            ),
        ]
    duration = sum(max(0.5, float(s.duration or 2)) for s in scenes) or 15
    return VideoSpec(
        duration=duration,
        format=aspect_ratio,
        hook=concept.hook or product.title,
        scenes=scenes,
        voice_direction=concept.voice_direction or "Natural, confident, not hypey.",
        music_direction=concept.music_direction or "Light, modern, unobtrusive.",
        cta=concept.cta or "SHOP_NOW",
    )


def heuristic_score(
    *,
    has_media: bool,
    hook: str,
    headline: str,
    primary_text: str,
    visual: str,
    winning_notes: str,
    portfolio_bucket: str,
    product_title: str,
) -> AICreativeScore:
    """Local evaluation so generation does not spend a model call per creative."""
    breakdown = AIScoreBreakdown()
    breakdown.visual_clarity = 82 if has_media else 28
    breakdown.hook_strength = min(90, 30 + min(len(hook or ""), 80) // 2)
    copy_len = len((headline or "") + (primary_text or ""))
    breakdown.product_relevance = 70
    title = (product_title or "").lower()
    blob = f"{hook} {headline} {primary_text} {visual}".lower()
    if title and title.split()[0] in blob:
        breakdown.product_relevance = 88
    breakdown.strategy_alignment = {
        "winner_variation": 86,
        "combination": 74,
        "exploration": 62,
        "experimental": 54,
    }.get(portfolio_bucket, 60)
    notes = (winning_notes or "").lower()
    overlap = 0
    if notes:
        overlap = sum(1 for token in notes.replace(";", " ").split() if len(token) > 4 and token in blob)
    breakdown.creative_diversity = 55 if portfolio_bucket == "winner_variation" else 78
    breakdown.audience_relevance = min(90, 58 + overlap * 4)
    breakdown.objective_alignment = 72 if copy_len > 40 else 50
    parts = [
        breakdown.strategy_alignment,
        breakdown.product_relevance,
        breakdown.hook_strength,
        breakdown.creative_diversity,
        breakdown.visual_clarity,
        breakdown.audience_relevance,
        breakdown.objective_alignment,
    ]
    total = int(round(sum(parts) / len(parts)))
    return AICreativeScore(total=total, breakdown=breakdown, label="AI Creative Evaluation")
