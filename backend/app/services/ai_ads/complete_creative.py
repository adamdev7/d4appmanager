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

STYLE_PLAYBOOKS: dict[str, dict[str, Any]] = {
    "UGC": {
        "promise": "Authentic phone-shot social proof. Lived-in rooms, imperfect framing, real light.",
        "forbid": "Studio packshot, white seamless catalog, color-graded listing photo, campaign polish.",
        "copy": "First-person, specific, like a friend showing what they just got. No invented reviews.",
        "scenes": [
            "Bathroom-mirror phone still: messy real counter, warm bulbs, product clearly worn, slight grain.",
            "Night-out candid: restaurant table clutter, practical lights, product catching the lamp, no celebrity face.",
            "Commute / desk life: window light, ordinary room, product in use as an everyday detail.",
            "Getting-ready still: anonymous hands fastening or sliding the piece on, phone-angle, real bedroom.",
        ],
        "video": [
            "Handheld UGC: spoken first-person VO, original music bed, no readable face, quick try-on, product hold-up CTA.",
            "Mirror get-ready clip with spoken hook, then a step-outside beat, music swell, end on the product in natural light.",
        ],
    },
    "PRODUCT_DEMO": {
        "promise": "Prove how it works on a real body. The mechanism is the hero.",
        "forbid": "Static jewelry-box catalog crop, beauty-only lighting with no action.",
        "copy": "One concrete feature from product facts (fit, adjust, clasp, wear). No invented specs.",
        "scenes": [
            "Macro demo: fingers adjust, clasp, or slide the exact product so the construction is obvious.",
            "On-body fit: how it sits on a hand, wrist, or neck in a new angle the listing never used.",
            "Motion still: mid-action of putting it on, fabric and skin for scale, product sharp.",
            "Detail proof: extreme close-up of the unique hardware while it is being used, not on a void background.",
        ],
        "video": [
            "Spoken demo VO: open on the problem of putting it on, demonstrate the mechanism, music under, end on a clean wear shot and CTA.",
            "Three tight angles of the same action with a voice explaining the feature, then pull back to the worn product.",
        ],
    },
    "LIFESTYLE": {
        "promise": "A world the buyer wants. The product is the finishing detail, never a retouched listing.",
        "forbid": "The catalog backdrop, the same crop as Shopify, empty infinity sweep copied from the site.",
        "copy": "Aspiration in one line tied to a real product fact.",
        "scenes": [
            "Evening out: dinner or city night, product as the last thing you notice, new camera height.",
            "Daylight street or travel: sun, real architecture, product worn, shallow depth of field.",
            "Intimate home that is NOT the listing set: morning window, linen, product in a lived scene.",
            "Editorial lifestyle: magazine styling, complementary props only, product fully recognizable.",
        ],
        "video": [
            "Spoken lifestyle VO over original music: 1-second product close-up, pull back into a new in-use world, end on packshot and CTA.",
            "Editorial montage: four distinct camera angles of the same product, music-led with a whispered VO and on-screen CTA.",
        ],
    },
    "PROBLEM_SOLUTION": {
        "promise": "Show the friction, then the product as the fix — only using claims in the product data.",
        "forbid": "Pretty packshot with no story. Fake before/after medical or 'miracle' claims.",
        "copy": "Name a real pain the product addresses (fit, slipping, sizing). Never invent a condition.",
        "scenes": [
            "Split-beat still: left side the annoyance (too-tight, fiddly, slipping), right side this exact product solving it.",
            "Hands struggling with a generic piece, then this SKU going on easily — keep identity locked.",
            "Everyday 'never take it off' scene: product worn through a real task, built from product facts.",
            "Close-up of the solving feature (adjustable fit, clasp, construction) in a new setting.",
        ],
        "video": [
            "Spoken problem-to-solution: friction beat, product appears, after-moment, original music, end card CTA.",
            "Voice names the painful alternative, cut to this product on the body, hold, spoken CTA.",
        ],
    },
    "PROMOTIONAL": {
        "promise": "Offer-ad energy that makes someone buy now. Gift, drop, value — using the REAL price only.",
        "forbid": "Invented discount percents, fake timers, fake reviews, plain catalog photo with a filter.",
        "copy": "Offer framing with the real price if provided. Urgency without lying. Empty overlay band for headline.",
        "scenes": [
            "Gift-ready still: wrapped table, the exact product as the present being revealed, empty top third for offer type.",
            "Price-as-hero composition: product on a new surface, huge negative space for a real-price overlay — never bake a fake % off.",
            "Limited-drop drama: dark rim light, single hero object, urgency crop, overlay-safe margins.",
            "Unboxing / treat-yourself: hands lifting the exact SKU from tissue, warm practical light, not the website photo.",
        ],
        "video": [
            "Spoken gift-reveal hook over music, product identity close-up, offer-safe end card with CTA. No fake discounts.",
            "Drop energy: quick cuts, energetic original music, freeze on a shoppable packshot with spoken CTA.",
        ],
    },
}

KNOWN_STYLES = tuple(STYLE_PLAYBOOKS.keys())
DEFAULT_STYLES = ["UGC", "PRODUCT_DEMO", "LIFESTYLE"]

# Meta Ads CTA enum. Unknown values become SHOP_NOW so publish does not 400.
META_CTAS = {
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

DEFAULT_VOICE = (
    "Native spoken English, warm confident woman, 1–2 feet from the mic, not a radio announcer. "
    "Every scene voiceover line must be heard clearly in the MP4."
)
DEFAULT_MUSIC = (
    "Original instrumental bed only — soft luxury pop, no lyrics, no named artists, no copyrighted songs. "
    "Sit under the voice at about -12 dB, swell into the CTA."
)


def meta_cta(raw: str | None) -> str:
    token = (raw or "SHOP_NOW").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {"SHOP": "SHOP_NOW", "BUY": "BUY_NOW", "LEARN": "LEARN_MORE"}
    token = aliases.get(token, token)
    return token if token in META_CTAS else "SHOP_NOW"


def meta_ready_copy(
    *,
    hook: str = "",
    headline: str = "",
    primary_text: str = "",
    cta: str = "",
    product_title: str = "",
) -> dict[str, str]:
    """Clamp copy to Meta Ads field limits so a READY creative can be published without a 400."""
    fallback = (product_title or "Shop now").strip() or "Shop now"
    hook_text = (hook or headline or fallback).strip()
    headline_text = (headline or hook_text or fallback).strip()
    primary = (primary_text or hook_text or headline_text).strip()
    return {
        "hook": hook_text[:125],
        "headline": headline_text[:255],
        "primary_text": primary[:2200],
        "cta": meta_cta(cta),
    }


def spoken_script(spec: VideoSpec) -> str:
    """Timed VO the video model must speak, not just paint as on-screen text."""
    parts: list[str] = []
    t = 0.0
    for scene in spec.scenes[:6]:
        line = (scene.voiceover or scene.text_overlay or spec.hook or "").strip()
        dur = max(0.5, float(scene.duration or 2))
        if line:
            parts.append(f"{t:.0f}-{t + dur:.0f}s: {line[:160]}")
        t += dur
    return " ".join(parts) if parts else (spec.hook or "")


def _as_count(value: Any, default: int = 0) -> int:
    if value is None or value == "":
        return int(default or 0)
    return int(value)


def clamp_generation_counts(images: int, videos: int) -> tuple[int, int]:
    return max(0, min(_as_count(images), MAX_IMAGE_ADS)), max(0, min(_as_count(videos), MAX_VIDEO_ADS))


def resolve_generation_counts(
    images: Any,
    videos: Any,
    *,
    default_images: int = 0,
    default_videos: int = 0,
) -> tuple[int, int]:
    """Keep an explicit 0. Only fall back to defaults when the value is missing."""
    return clamp_generation_counts(
        _as_count(images, default_images),
        _as_count(videos, default_videos),
    )


def normalize_styles(styles: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in styles or []:
        key = str(raw or "").strip().upper().replace(" ", "_")
        if key in STYLE_PLAYBOOKS and key not in out:
            out.append(key)
    return out or list(DEFAULT_STYLES)


def style_for_index(styles: list[str] | None, index: int) -> str:
    keys = normalize_styles(styles)
    return keys[int(index) % len(keys)]


def image_shot_recipe(index: int, styles: list[str] | None = None) -> str:
    style = style_for_index(styles, index)
    scenes = STYLE_PLAYBOOKS[style]["scenes"]
    return f"{style}: {scenes[int(index) % len(scenes)]}"


def video_story_recipe(index: int, styles: list[str] | None = None) -> str:
    style = style_for_index(styles, index)
    stories = STYLE_PLAYBOOKS[style]["video"]
    return f"{style}: {stories[int(index) % len(stories)]}"


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
    styles: list[str] | None = None,
) -> list[CreativeConceptModel]:
    """Guarantee each concept follows a selected style and a unique new scene."""
    used: list[str] = []
    kind = (media_type or "IMAGE").upper()
    for i, concept in enumerate(concepts):
        style = style_for_index(styles, i)
        concept.style = style
        play = STYLE_PLAYBOOKS[style]
        if kind == "VIDEO":
            recipe = video_story_recipe(i, styles)
            lock = (
                f"ORIGINAL VIDEO {i + 1} of {len(concepts)}. Style {style}. Unique storyboard: {recipe} "
                f"{play['forbid']} Do not recreate an existing Meta ad or catalog clip."
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
                            visual=f"Middle: {recipe} Keep {product.title} recognizable in a brand-new setting.",
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
                concept.visual_direction = f"{style} {base} {lock}".strip()
                if concept.scenes:
                    concept.scenes[0].visual = f"{lock} {concept.scenes[0].visual}".strip()
            used.append(concept.visual_direction)
            continue

        recipe = image_shot_recipe(i, styles)
        lock = (
            f"ORIGINAL STILL {i + 1} of {len(concepts)}. STYLE {style}. Required scene: {recipe} "
            f"{play['promise']} Forbidden: {play['forbid']} "
            f"Show the exact {product.title} from the catalog photos — never a different product. "
            "Invent a brand-new advertisement scene that has never been used on the website or in Meta. "
            "Do not return a color-graded, cropped, or lightly edited listing photo."
        )
        base = (concept.image_prompt or concept.visual_direction or "").strip()
        similar = any(_token_overlap(base, prev) > 0.7 for prev in used)
        if not base or similar:
            concept.image_prompt = (
                f"{recipe} Photorealistic NEW advertisement featuring {product.title}. {lock}"
            )
            concept.visual_direction = recipe
        else:
            concept.image_prompt = f"{style} {base}\n{lock}"
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
        "appearance_lock": (product.brand_context or {}).get("appearance_lock") or product_appearance_notes(product),
        "restrictions": (product.restrictions or [])[:6],
        "note": "Catalog photos ARE the product identity only. New ads must show this exact SKU in a brand-new scene — never a different item, and never a retouch of the listing.",
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
        "offer_look": visual.get("offer_look") or copy_dna.get("offer_presentation"),
        "product_in_ad": visual.get("product_depicted"),
        "setting": visual.get("setting") or visual.get("background"),
        "lighting": visual.get("lighting"),
        "framing": visual.get("framing"),
        "visual_hook": visual.get("visual_hook"),
        "human_presence": visual.get("human_presence"),
        "product_visibility": visual.get("product_visibility"),
        "hook_type": copy_dna.get("hook_type"),
        "tone": copy_dna.get("tone"),
        "roas": perf.get("roas"),
        "ctr": perf.get("ctr"),
        "cpa": perf.get("cpa"),
        "spend": perf.get("spend"),
        "purchases": perf.get("purchases"),
    }


def product_reference_urls(product: ProductContext) -> list[str]:
    """Shopify catalog photos used as identity references for generation.

    Prefer locally cached data URLs so OpenAI does not have to fetch the CDN.
    """
    cached = list((product.brand_context or {}).get("identity_data_urls") or [])
    if cached:
        return [str(url) for url in cached if url][:3]
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


def format_appearance_lock(lock: Any) -> str:
    if lock is None:
        return ""
    if isinstance(lock, str):
        return lock.strip()
    parts = [
        getattr(lock, "summary", "") or "",
        getattr(lock, "materials", "") or "",
        getattr(lock, "colors", "") or "",
        getattr(lock, "hardware", "") or "",
        getattr(lock, "construction", "") or "",
        getattr(lock, "distinguishing_details", "") or "",
    ]
    if hasattr(lock, "model_dump"):
        data = lock.model_dump()
        parts = [str(data.get(k) or "") for k in ("summary", "materials", "colors", "hardware", "construction", "distinguishing_details")]
    return " ".join(p for p in parts if p).strip()[:700]


def winning_style_notes(winners: list[dict[str, Any]], *, sku_safe: bool = False) -> str:
    keys = (
        ("setting", "visual_hook", "style", "composition", "hook_type")
        if sku_safe
        else (
            "offer_look",
            "product_in_ad",
            "setting",
            "visual_hook",
            "style",
            "composition",
            "hook_type",
            "headline",
        )
    )
    parts: list[str] = []
    for item in winners[:6]:
        for key in keys:
            value = item.get(key)
            if value and str(value) not in parts:
                parts.append(str(value)[:140])
    return "; ".join(parts[:10])


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
    styles: list[str] | None = None,
) -> str:
    style = style_for_index(styles, variation_index)
    play = STYLE_PLAYBOOKS[style]
    recipe = image_shot_recipe(variation_index, styles)
    prompt = (image_prompt or visual_direction or "").strip()
    if not prompt:
        prompt = f"{recipe} Photorealistic NEW advertisement of {product.title}."
    appearance = (product.brand_context or {}).get("appearance_lock") or product_appearance_notes(product)
    extras = [
        f"Assigned style: {style}. {play['promise']}",
        f"Required new scene: {recipe}",
        f"Copy tone: {play['copy']}",
        f"Forbidden: {play['forbid']}",
        f"Product: {product.title}.",
        f"IDENTITY LOCK — the reference image(s) are ONLY for SKU identity: {appearance}. "
        "Keep colors, materials, clasp, beads, leather, metal, geometry. "
        "Do not invent a different ring, bracelet, leather band, or generic jewelry.",
        "The reference is NOT a layout to copy. Do not return the catalog photo, a crop of it, "
        "a color grade of it, or a Meta ad you have seen. New camera, new lighting, new background, new crop.",
        f"This is unique still {variation_index + 1} of {max(variation_count, 1)}.",
        "Do not invent materials, logos, discounts, or packaging details that are not in the product facts.",
    ]
    desc = (product.description or "").strip()
    if desc:
        extras.append(f"Known product facts only: {desc[:240]}")
    if product.price is not None and style == "PROMOTIONAL":
        currency = product.currency or ""
        extras.append(
            f"PROMOTIONAL offer ad: you may imply value using the real price {currency} {product.price}. "
            "Leave empty space for an overlay. Never invent a % off, fake timer, or fake review."
        )
    elif style == "PROMOTIONAL":
        extras.append(
            "PROMOTIONAL offer ad: gift/drop/urgency composition with overlay-safe margins. "
            "Never invent a discount, fake timer, or fake review."
        )
    if winning_notes:
        extras.append(
            f"Borrow only STYLE TRAITS from stronger Meta ads (hook energy, setting type) — never their pixels: "
            f"{winning_notes[:320]}"
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
    styles: list[str] | None = None,
) -> str:
    scenes = []
    for scene in spec.scenes[:6]:
        bit = (scene.visual or "").strip()
        if bit:
            scenes.append(bit[:180])
    shot_list = " Then ".join(scenes) if scenes else (spec.hook or product.title)
    style = style_for_index(styles, variation_index)
    play = STYLE_PLAYBOOKS[style]
    recipe = video_story_recipe(variation_index, styles)
    appearance = (product.brand_context or {}).get("appearance_lock") or product_appearance_notes(product)
    parts = [
        f"Image-to-video ad. The attached input_reference is the FIRST FRAME and the EXACT {product.title}.",
        f"Keep this same physical product in every frame: {appearance}.",
        "Do not replace, restyle, or invent a different ring, bracelet, necklace, or generic jewelry. "
        "Colors, materials, clasp, beads, leather, metal, and geometry must match the reference image.",
        f"Assigned style: {style}. {play['promise']} Forbidden: {play['forbid']}",
        f"This is unique video {variation_index + 1} of {max(variation_count, 1)}. Motion recipe: {recipe}",
        "Camera may move around THIS item and the setting may change after the opening beat, "
        "but the SKU on screen must stay the one in the reference.",
        "Do not recreate an existing Meta ad. Do not invent a different product to match a winning ad's look.",
        f"Hook: {spec.hook or product.title}.",
        f"Shot list featuring {product.title} only: {shot_list}.",
        "Keep the product clearly visible most of the time. Smooth camera, no fake UI, no watermarks.",
        f"End on a clear shot of this same {product.title} and the call to action {(spec.cta or 'SHOP NOW').replace('_', ' ')}.",
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
        parts.append(f"Voice: {spec.voice_direction[:160]}")
    else:
        parts.append(f"Voice: {DEFAULT_VOICE}")
    if spec.music_direction:
        parts.append(f"Music: {spec.music_direction[:160]}")
    else:
        parts.append(f"Music: {DEFAULT_MUSIC}")
    spoken = spoken_script(spec)
    if spoken:
        parts.append(f"SPOKEN SCRIPT (must be audible, not silent, not text-only): {spoken}")
    parts.append(
        "AUDIO IS REQUIRED. This MP4 must be ready to spend on Meta Reels/Stories: "
        "spoken voiceover throughout, original music under the voice, no copyrighted songs, "
        "no celebrity likeness. Keep 250px clear at the top and bottom for Reels UI. "
        "On-screen text only for the hook (first second) and the end CTA, large high-contrast, center-safe. "
        "Do not bake fake UI, fake reviews, watermarks, or a different product. "
        f"End on a clear shot of this same {product.title} and {(spec.cta or 'SHOP NOW').replace('_', ' ')}."
    )
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
    for scene in scenes:
        if not (scene.voiceover or "").strip():
            scene.voiceover = (scene.text_overlay or concept.hook or product.title)[:180]
        if not (scene.text_overlay or "").strip():
            scene.text_overlay = (scene.voiceover or concept.headline or product.title)[:80]
    duration = min(12.0, max(4.0, sum(max(0.5, float(s.duration or 2)) for s in scenes) or 8))
    return VideoSpec(
        duration=duration,
        format=aspect_ratio,
        hook=concept.hook or product.title,
        scenes=scenes,
        voice_direction=concept.voice_direction or DEFAULT_VOICE,
        music_direction=concept.music_direction or DEFAULT_MUSIC,
        cta=meta_cta(concept.cta),
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
