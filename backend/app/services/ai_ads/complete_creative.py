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

# Forced unique treatments so a batch of N ads cannot collapse into one catalog retouch.
IMAGE_SHOT_RECIPES = [
    "Studio product hero: 3/4 camera, softbox lighting, premium surface, empty top third for overlay.",
    "Lifestyle in-use: real environment, natural window light, product being worn or used, shallow depth of field.",
    "Macro craftsmanship: extreme close-up on texture, clasp, or key detail, dramatic but clean light.",
    "Overhead editorial flat lay: magazine styling, complementary props, generous negative space.",
    "Handheld UGC: slightly imperfect phone framing, authentic room, product clearly in frame.",
    "Daylight outdoor: natural setting that fits the product, sun-lit, no studio backdrop.",
    "Reveal / unboxing: hands presenting the product as it first appears, warm practical light.",
    "Cinematic luxury: dark background, rim light, single hero object, quiet premium mood.",
]

VIDEO_STORY_RECIPES = [
    "Open on a 1-second product close-up hook, pull back to lifestyle in-use, end on a packshot and CTA.",
    "Problem-to-solution: a relatable friction beat, product appears, after-moment, end card.",
    "UGC handheld: talking-to-camera energy without a readable face, quick demo, product hold-up CTA.",
    "Editorial montage: four distinct camera angles of the same product, music-led, no talking head.",
]


def clamp_generation_counts(images: int, videos: int) -> tuple[int, int]:
    return max(0, min(int(images or 0), MAX_IMAGE_ADS)), max(0, min(int(videos or 0), MAX_VIDEO_ADS))


def image_shot_recipe(index: int) -> str:
    return IMAGE_SHOT_RECIPES[int(index) % len(IMAGE_SHOT_RECIPES)]


def video_story_recipe(index: int) -> str:
    return VIDEO_STORY_RECIPES[int(index) % len(VIDEO_STORY_RECIPES)]


def _token_overlap(a: str, b: str) -> float:
    ta = {t for t in (a or "").lower().split() if len(t) > 3}
    tb = {t for t in (b or "").lower().split() if len(t) > 3}
    if not ta or not tb:
        return 1.0
    return len(ta & tb) / max(len(ta | tb), 1)


def diversify_concepts(
    concepts: list[CreativeConceptModel],
    product: ProductContext,
    *,
    media_type: str,
) -> list[CreativeConceptModel]:
    """Guarantee each concept in a batch has a unique visual, even if Astra repeated itself."""
    used: list[str] = []
    kind = (media_type or "IMAGE").upper()
    for i, concept in enumerate(concepts):
        if kind == "VIDEO":
            recipe = video_story_recipe(i)
            lock = (
                f"ORIGINAL VIDEO {i + 1} of {len(concepts)}. Unique storyboard: {recipe} "
                "Do not recreate an existing Meta ad or catalog clip."
            )
            visuals = " ".join((s.visual or "") for s in (concept.scenes or []))
            base = (concept.visual_direction or visuals or "").strip()
            if not base or any(_token_overlap(base, prev) > 0.7 for prev in used):
                concept.visual_direction = f"{recipe} Product is {product.title}."
                if not concept.scenes:
                    concept.scenes = [
                        VideoScene(
                            duration=3,
                            visual=f"Hook: {recipe} Show {product.title}.",
                            voiceover=concept.hook or product.title,
                            text_overlay=concept.hook or product.title,
                        ),
                        VideoScene(
                            duration=6,
                            visual=f"Middle: {recipe} Keep {product.title} recognizable in a new setting.",
                            voiceover=(concept.primary_text or product.description or product.title)[:180],
                            text_overlay=concept.headline or product.title,
                        ),
                        VideoScene(
                            duration=3,
                            visual=f"End on a new packshot of {product.title} and CTA. {lock}",
                            voiceover=(concept.cta or "Shop now").replace("_", " "),
                            text_overlay=(concept.cta or "SHOP NOW").replace("_", " "),
                        ),
                    ]
                else:
                    concept.scenes[0].visual = f"{lock} {concept.scenes[0].visual}".strip()
            else:
                concept.visual_direction = f"{base} {lock}".strip()
                if concept.scenes:
                    concept.scenes[0].visual = f"{lock} {concept.scenes[0].visual}".strip()
            used.append(concept.visual_direction)
            continue

        recipe = image_shot_recipe(i)
        lock = (
            f"ORIGINAL STILL {i + 1} of {len(concepts)}. Required unique treatment: {recipe} "
            "Invent a brand-new advertisement. Do not reproduce Shopify listing photos, "
            "catalog photography, or any existing Meta ad."
        )
        base = (concept.image_prompt or concept.visual_direction or "").strip()
        similar = any(_token_overlap(base, prev) > 0.7 for prev in used)
        if not base or similar:
            concept.image_prompt = (
                f"{recipe} Photorealistic new advertisement featuring {product.title}. {lock}"
            )
            concept.visual_direction = recipe
        else:
            concept.image_prompt = f"{base}\n{lock}"
            if not (concept.visual_direction or "").strip():
                concept.visual_direction = recipe
        used.append(concept.image_prompt)
    return concepts


def compact_product(product: ProductContext) -> dict[str, Any]:
    images = [img.src for img in (product.images or []) if getattr(img, "src", None)][:3]
    return {
        "title": product.title,
        "description": (product.description or "")[:500],
        "price": product.price,
        "currency": product.currency,
        "url": product.product_url,
        "image": images[0] if images else None,
        "catalog_photos": images,
        "appearance": product_appearance_notes(product),
        "restrictions": (product.restrictions or [])[:6],
        "note": "Catalog photos show product appearance only. Do not recreate those photos as ads.",
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
    """Catalog photo URLs for planner context only — never as image-edit sources."""
    return [img.src for img in (product.images or []) if getattr(img, "src", None)][:3]


def product_appearance_notes(product: ProductContext) -> str:
    bits: list[str] = [product.title]
    desc = (product.description or "").strip()
    if desc:
        bits.append(desc[:180])
    alts = [img.alt for img in (product.images or []) if getattr(img, "alt", None)]
    if alts:
        bits.append(str(alts[0])[:80])
    return " ".join(bits)[:280]


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
    variation_index: int = 0,
    variation_count: int = 1,
) -> str:
    prompt = (image_prompt or visual_direction or "").strip()
    recipe = image_shot_recipe(variation_index)
    if not prompt:
        prompt = f"{recipe} Photorealistic new advertisement of {product.title}."
    extras = [
        f"Product: {product.title}.",
        f"Product appearance to keep recognizable: {product_appearance_notes(product)}.",
        "This is a brand-new advertisement still. Do not retouch, crop, or reproduce a catalog photo "
        "or any existing ad. New scene, new camera, new lighting, new composition.",
        f"This is unique still {variation_index + 1} of {max(variation_count, 1)}. Required treatment: {recipe}",
        "Do not invent materials, logos, or packaging details that are not in the product facts.",
    ]
    desc = (product.description or "").strip()
    if desc:
        extras.append(f"Known product facts only: {desc[:240]}")
    if winning_notes:
        extras.append(
            f"Borrow only style traits associated with stronger Meta ads (not their exact shots): "
            f"{winning_notes[:400]}"
        )
    if brand_style:
        extras.append(f"Brand look: {brand_style[:160]}")
    extras.append(
        f"Finished Meta {placement} advertisement still, aspect {aspect_ratio}. "
        "Photorealistic, generous safe margins for headline overlay, "
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
    variation_index: int = 0,
    variation_count: int = 1,
) -> str:
    scenes = []
    for scene in spec.scenes[:6]:
        bit = (scene.visual or "").strip()
        if bit:
            scenes.append(bit[:180])
    shot_list = " Then ".join(scenes) if scenes else (spec.hook or product.title)
    recipe = video_story_recipe(variation_index)
    parts = [
        f"Brand-new vertical Meta Reels / Stories advertisement. Product is {product.title}.",
        f"This is unique video {variation_index + 1} of {max(variation_count, 1)}. Required storyboard: {recipe}",
        "Do not recreate an existing Meta ad, catalog clip, or listing photo. New shots and setting.",
        f"Hook: {spec.hook or product.title}.",
        f"Shot list: {shot_list}.",
        f"Keep {product.title} recognizable. Smooth camera, no fake UI, no watermarks.",
        f"End on a clear product shot and the call to action {(spec.cta or 'SHOP NOW').replace('_', ' ')}.",
    ]
    desc = (product.description or "").strip()
    if desc:
        parts.append(f"Known product facts only: {desc[:220]}")
    if winning_notes:
        parts.append(
            f"Borrow only style traits associated with stronger Meta ads (not their exact shots): "
            f"{winning_notes[:240]}"
        )
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
