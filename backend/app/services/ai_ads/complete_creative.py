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

CLEAN_PLATE = (
    "CLEAN PLATE. Zero on-screen text, letters, numbers, captions, titles, subtitles, watermarks, logos, prices, "
    "CTA words, UI chrome, or end-card copy. Quiet negative space only — the operator adds text later."
)

CRAFT = (
    "Photorealistic, print-ad craft. Sharp focus on the product, true materials, correct metal "
    "reflections, anatomically correct hands if any, no extra fingers, no melted jewelry, no "
    "duplicate clasps, no warped geometry. Single SKU. No fake packaging."
)

# Angles whose whole job is to close the sale, so real ad copy is rendered into the still.
SALES_TEXT_STYLES = ("PROMOTIONAL", "PROBLEM_SOLUTION")

TEXT_LAYOUTS: dict[str, str] = {
    "PROMOTIONAL": (
        "Layout: the headline runs across the top third on a solid opaque scrim. The product stays "
        "fully unobstructed in the middle. A rounded solid CTA button sits near the bottom. A small "
        "solid price badge, when given, sits in one corner."
    ),
    "PROBLEM_SOLUTION": (
        "Layout: one short label near the top names the friction on a solid opaque chip. The product "
        "is the hero in the middle. A rounded solid CTA button sits near the bottom."
    ),
}

_CURRENCY_SYMBOLS = {"USD": "$", "CAD": "$", "AUD": "$", "NZD": "$", "EUR": "\u20ac", "GBP": "\u00a3"}

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
            "Handheld UGC: no face needed, quick try-on, product hold-up. No text.",
            "Mirror get-ready clip, then a step-outside beat, end on the product in natural light. No captions.",
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
            "Silent demo: open on putting it on, show the mechanism, end on a clean wear shot. No text.",
            "Three tight angles of the same action, then pull back to the worn product. No captions.",
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
            "1-second product close-up, pull back into a new in-use world, end on a clean packshot. No text.",
            "Editorial montage: four distinct camera angles of the same product. No captions.",
        ],
    },
    "PROBLEM_SOLUTION": {
        "promise": "Show the friction, then the product as the fix — only using claims in the product data.",
        "forbid": "Pretty packshot with no story. Fake before/after medical or 'miracle' claims.",
        "copy": "Name a real pain the product addresses (fit, slipping, sizing). Never invent a condition.",
        "scenes": [
            "Split-beat still: left side the annoyance (too-tight, fiddly, slipping), right side this exact product solving it. Leave a clean top band and a clean bottom strip for burned-in copy.",
            "Hands struggling with a generic piece, then this SKU going on easily — keep identity locked. Uncluttered top band for a label, clear bottom strip for a CTA button.",
            "Everyday 'never take it off' scene: product worn through a real task, built from product facts. Flat, uncluttered top and bottom zones for copy.",
            "Close-up of the solving feature (adjustable fit, clasp, construction) in a new setting, with calm top and bottom zones reserved for copy.",
        ],
        "video": [
            "Problem-to-solution in pictures only: friction beat, product appears, after-moment. No text.",
            "Show the painful alternative, cut to this product on the body, hold. No captions.",
        ],
    },
    "PROMOTIONAL": {
        "promise": "Offer-ad energy that makes someone buy now. Gift, drop, value — using the REAL price only.",
        "forbid": "Invented discount percents, fake timers, fake reviews, plain catalog photo with a filter.",
        "copy": "Offer framing with the real price if provided. Urgency without lying. Short, punchy, buy-now copy.",
        "scenes": [
            "Gift-ready still: wrapped table, the exact product as the present being revealed. Keep the top third flat and uncluttered for a headline band and the bottom clear for a CTA button.",
            "Hero composition: product on a new surface with a deep, even top third for a headline scrim and a clear bottom strip for a CTA button.",
            "Limited-drop drama: dark rim light, single hero object, urgency crop, with a calm dark top band that a bright headline can sit on.",
            "Treat-yourself: hands lifting the exact SKU from tissue, warm practical light, uncluttered top and bottom zones reserved for copy.",
        ],
        "video": [
            "Gift-reveal motion, product identity close-up, freeze on a shoppable packshot. No text, no fake discounts.",
            "Drop energy: quick cuts, freeze on a clean product hold. No captions.",
        ],
    },
    "UNBOXING": {
        "promise": "The first-touch reveal. Tissue, box, hands — the SKU arriving as a gift to the self.",
        "forbid": "Website packshot, empty seamless, fake branded box art that is not in the product facts.",
        "copy": "The moment it lands. Specific, tactile. No invented unboxing claims.",
        "scenes": [
            "Hands peeling tissue to reveal the exact product, warm indoor light, real table clutter.",
            "Open box from above: the SKU sitting in packing, fingers reaching in, identity locked.",
            "First-wear right after unboxing: piece going onto a wrist or neck, leftover tissue in frame.",
            "Close hold to camera after the reveal — product sharp, packing softly out of focus.",
        ],
        "video": [
            "Tissue peel, product lift, hold to camera. No text.",
            "Box open, hands take the SKU, first wear, freeze. No captions.",
        ],
    },
    "MACRO": {
        "promise": "Proof in the details. Extreme close-up of materials, hardware, and construction.",
        "forbid": "Full-body lifestyle, tiny product in a wide room, generic jewelry that is not this SKU.",
        "copy": "One tactile fact from the product data. Texture over slogans.",
        "scenes": [
            "Extreme close-up of clasp, beads, stitching, or metal grain filling most of the frame.",
            "Raking light across the surface so material (leather, gold, enamel) is unmistakable.",
            "Fingers pinch a unique hardware detail; skin for scale; product razor-sharp.",
            "Three-quarter macro of the worn piece so shape and construction stay true.",
        ],
        "video": [
            "Slow push into hardware, light graze, pull back to the worn product. No text.",
            "Three macro beats of the same SKU, end on a clean hold. No captions.",
        ],
    },
    "FLAT_LAY": {
        "promise": "Editorial overhead. Styled surface, complementary props, product fully readable from above.",
        "forbid": "On-body crop, messy UGC, the Shopify listing backdrop, props that hide the SKU.",
        "copy": "Quiet, editorial. The object is the headline.",
        "scenes": [
            "Top-down on linen or stone, the exact product centered, two quiet props only.",
            "Diagonal overhead, morning window, product catching a hard shadow, identity locked.",
            "Magazine grid: product plus one related object, generous empty space, no labels.",
            "Dark editorial flat lay, rim light, single hero object, blank margins.",
        ],
        "video": [
            "Overhead drift across a styled table, settle on the SKU. No text.",
            "Props part to reveal the product, hold. No captions.",
        ],
    },
    "STREET_STYLE": {
        "promise": "Candid outdoor fashion. Real streets, daylight, the product worn as the finishing detail.",
        "forbid": "Indoor catalog set, studio cyclorama, posed lookbook cloned from the site.",
        "copy": "Seen in the wild. One line of attitude, no invented city names as proof.",
        "scenes": [
            "Sidewalk stride, real architecture, product catching daylight, anonymous wearer.",
            "Cafe terrace candid: product in the foreground, street bokeh, new camera height.",
            "Crosswalk still: motion blur in the city, SKU sharp on the body.",
            "Golden-hour wall: product worn, hard sun, not the listing crop.",
        ],
        "video": [
            "Walk-up, product catch-light, hold. No text.",
            "Street pan onto the worn SKU, freeze. No captions.",
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
    "None. No talking, no narration, no lip-sync speech. The operator will add voice-over later."
)
DEFAULT_MUSIC = (
    "Light original instrumental only — no lyrics, no vocals, no named artists, no copyrighted songs."
)


def bakes_sales_text(style: str | None) -> bool:
    """True when this angle should render closing copy into the frame instead of a clean plate."""
    return str(style or "").strip().upper() in SALES_TEXT_STYLES


def styles_bake_sales_text(styles: list[str] | None) -> bool:
    return any(bakes_sales_text(s) for s in normalize_styles(styles))


def _one_line(text: str, limit: int) -> str:
    """Short, single-line, no trailing punctuation — image models spell short strings reliably."""
    line = " ".join((text or "").split()).strip(" .!,;:")
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0]
    return (cut or line[:limit]).strip()


def format_price(price: Any, currency: str | None = None) -> str:
    if price is None:
        return ""
    try:
        amount = float(price)
    except (TypeError, ValueError):
        return ""
    text = f"{amount:.0f}" if abs(amount - round(amount)) < 0.005 else f"{amount:.2f}"
    code = (currency or "").strip().upper()
    symbol = _CURRENCY_SYMBOLS.get(code)
    if symbol:
        return f"{symbol}{text}"
    return f"{text} {code}".strip()


def overlay_copy(
    style: str,
    *,
    product: ProductContext,
    headline: str = "",
    hook: str = "",
    cta: str = "",
) -> dict[str, str]:
    """The exact strings the image model must spell into the frame."""
    out = {
        "headline": _one_line(headline or hook or product.title, 30),
        "cta": _one_line((cta or "SHOP NOW").replace("_", " ").title(), 14) or "Shop Now",
    }
    if style.strip().upper() == "PROMOTIONAL":
        price = format_price(product.price, product.currency)
        if price:
            out["price"] = price
    return out


def text_overlay_directive(style: str, copy: dict[str, str]) -> str:
    """Legibility contract for baked-in ad copy. Prevents white-on-white and garbled letterforms."""
    key = style.strip().upper()
    lines = [
        "BAKE THIS AD COPY INTO THE IMAGE. Render each string exactly, character for character:",
        f'HEADLINE: "{copy["headline"]}"',
        f'CTA BUTTON: "{copy["cta"]}"',
    ]
    if copy.get("price"):
        lines.append(f'PRICE BADGE: "{copy["price"]}"')
    lines.append(TEXT_LAYOUTS.get(key, TEXT_LAYOUTS["PROMOTIONAL"]))
    lines.append(
        "Typography: one bold, clean, condensed sans-serif for every string. Real letterforms, correct "
        "spelling, even kerning. No duplicated, mirrored, or half-formed letters, no lorem, no gibberish, "
        "no extra words beyond the strings above."
    )
    lines.append(
        "CONTRAST IS MANDATORY: every string sits on a solid opaque scrim, band, chip, or button in a colour "
        "that clearly opposes the text. White text only on a dark scrim; near-black text only on a light "
        "scrim. Never white text on a light background, never dark text on a dark background, never text "
        "floating directly over the product or a busy area."
    )
    lines.append(
        "Keep all copy inside the middle 80% of the frame (Meta safe area), clear of the outer 8%. Text must "
        "never cover, cross, or touch the product."
    )
    lines.append(
        "No other text anywhere: no watermark, no logo, no URL, no star rating, no invented discount percent, "
        "no fake countdown, no fake review."
    )
    return "\n".join(lines)


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


def video_only_count(videos: Any, *, default_videos: int = 1) -> int:
    """Clamp a video request. Images are planned separately via resolve_generation_counts."""
    _images, count = resolve_generation_counts(0, videos, default_images=0, default_videos=default_videos)
    return count


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
                            visual=f"Hook: {recipe} Show {product.title}. No text on screen.",
                            voiceover="",
                            text_overlay="",
                        ),
                        VideoScene(
                            duration=6,
                            visual=f"Middle: {recipe} Keep {product.title} recognizable in a brand-new setting. No captions.",
                            voiceover="",
                            text_overlay="",
                        ),
                        VideoScene(
                            duration=3,
                            visual=f"End on a clean packshot of {product.title}, no CTA text. {lock}",
                            voiceover="",
                            text_overlay="",
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
    headline: str = "",
    hook: str = "",
    cta: str = "",
) -> str:
    style = style_for_index(styles, variation_index)
    play = STYLE_PLAYBOOKS[style]
    recipe = image_shot_recipe(variation_index, styles)
    overlay = bakes_sales_text(style)
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
        CRAFT,
        "Do not invent materials, logos, discounts, or packaging details that are not in the product facts.",
    ]
    if not overlay:
        extras.insert(-1, CLEAN_PLATE)
    desc = (product.description or "").strip()
    if desc:
        extras.append(f"Known product facts only: {desc[:240]}")
    if style == "PROMOTIONAL":
        price = format_price(product.price, product.currency)
        extras.append(
            "PROMOTIONAL offer ad: gift, drop, or value energy that closes the sale. "
            + (f"Use the real price {price} only. " if price else "")
            + "Never invent a discount percent, a fake timer, or a fake review."
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
        f"{CRAFT} "
        + ("" if overlay else f"{CLEAN_PLATE} ")
        + "Single product, no fake UI, no extra logos."
    )
    body = f"{prompt}\n\n" + " ".join(extras)
    if overlay:
        copy = overlay_copy(style, product=product, headline=headline, hook=hook, cta=cta)
        body = f"{body}\n\n{text_overlay_directive(style, copy)}"
    return body


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
        CRAFT,
        f"Hook: {spec.hook or product.title}.",
        f"Shot list featuring {product.title} only: {shot_list}.",
        "Keep the product clearly visible most of the time. Smooth camera, no fake UI, no watermarks.",
        f"End on a clean hold of this same {product.title} with nothing written on the frame.",
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
    parts.append(f"Music: {spec.music_direction or DEFAULT_MUSIC}")
    parts.append(
        f"{CLEAN_PLATE} "
        "FORBIDDEN: spoken words, voiceover, narration, or talking. "
        "Leave 250px empty at the top and bottom for later overlays. "
        f"End on a still of this same {product.title} with a blank frame — no text."
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
                visual=f"Open on {product.title}. {(concept.visual_direction or '')[:160]} No text.",
                voiceover="",
                text_overlay="",
            ),
            VideoScene(
                duration=8,
                visual=concept.visual_direction or f"Show {product.title} in use. No captions.",
                voiceover="",
                text_overlay="",
            ),
            VideoScene(
                duration=4,
                visual=f"Clean product hold of {product.title}. No call-to-action text.",
                voiceover="",
                text_overlay="",
            ),
        ]
    for scene in scenes:
        scene.voiceover = ""
        scene.text_overlay = ""
    duration = min(12.0, max(4.0, sum(max(0.5, float(s.duration or 2)) for s in scenes) or 8))
    return VideoSpec(
        duration=duration,
        format=aspect_ratio,
        hook=concept.hook or product.title,
        scenes=scenes,
        voice_direction=DEFAULT_VOICE,
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
