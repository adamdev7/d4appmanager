"""Ad type registry: every format the Director can propose, mapped onto a renderable style.

The renderer knows the nine styles in ``STYLE_PLAYBOOKS``. Newer formats (carousel, split
screen, gift reveal, ...) render through the closest style plus a ``direction`` note that the
planner must follow, so no new provider or pipeline is needed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from app.services.ai_ads.complete_creative import STYLE_PLAYBOOKS


@dataclass(frozen=True)
class AdType:
    id: str
    label: str
    style: str
    media: tuple[str, ...]
    description: str
    direction: str = ""
    default_images: int = 1
    default_videos: int = 0
    # Testimonial-style formats voiced by an AI character: must never read as a real customer.
    testimonial_style: bool = False


_STYLE_TYPES = [
    AdType("UGC", "UGC", "UGC", ("IMAGE", "VIDEO"), "Phone-native real life, creator voice.", testimonial_style=True),
    AdType("PRODUCT_DEMO", "Product demo", "PRODUCT_DEMO", ("IMAGE", "VIDEO"), "The exact product worn or used on a body."),
    AdType("LIFESTYLE", "Lifestyle", "LIFESTYLE", ("IMAGE", "VIDEO"), "A new world around the product."),
    AdType("PROBLEM_SOLUTION", "Problem / solution", "PROBLEM_SOLUTION", ("IMAGE",), "Friction first, then the fix — only from real product facts."),
    AdType("PROMOTIONAL", "Promotional", "PROMOTIONAL", ("IMAGE",), "Offer energy on the real price. Never a fake discount."),
    AdType("UNBOXING", "Unboxing", "UNBOXING", ("IMAGE", "VIDEO"), "First-touch reveal from tissue or a box."),
    AdType("MACRO", "Macro", "MACRO", ("IMAGE", "VIDEO"), "Extreme close-up of materials and craftsmanship."),
    AdType("FLAT_LAY", "Flat lay", "FLAT_LAY", ("IMAGE",), "Editorial overhead, product fully readable."),
    AdType("STREET_STYLE", "Street style", "STREET_STYLE", ("IMAGE", "VIDEO"), "Candid outdoor fashion, product worn."),
]

_FORMAT_TYPES = [
    AdType(
        "CAROUSEL",
        "Carousel",
        "LIFESTYLE",
        ("IMAGE",),
        "3 connected cards telling one story (styling steps, gift guide, 3 reasons).",
        direction="Plan the stills as consecutive carousel cards of ONE story: same light and palette, card 1 is the hook.",
        default_images=3,
    ),
    AdType(
        "GIFT_REVEAL",
        "Gift reveal",
        "UNBOXING",
        ("IMAGE", "VIDEO"),
        "Before-the-gift-is-wrapped or the moment it is opened.",
        direction="Gift moment: hands, wrapping or box, the reveal of the exact piece. Emotion on the receiver, not a studio shot.",
        default_videos=1,
        default_images=0,
    ),
    AdType(
        "SPLIT_SCREEN",
        "Split screen",
        "LIFESTYLE",
        ("IMAGE",),
        "Two panels: two ways to wear it, day vs night, solo vs stacked.",
        direction="Compose as a clean two-panel split: the same exact product in both halves, one variable changes.",
    ),
    AdType(
        "STYLING_GUIDE",
        "How to style",
        "PRODUCT_DEMO",
        ("IMAGE", "VIDEO"),
        "Layering, stacking, outfit pairings with the real piece.",
        direction="Styling lesson: show the piece layered or paired with an outfit; the product stays the hero and unaltered.",
    ),
    AdType(
        "NATIVE_POST",
        "Native post",
        "UGC",
        ("IMAGE",),
        "Feed-native, meme-adjacent post that does not look like an ad.",
        direction="Looks like an organic friend's post, casual framing, relatable situation; tasteful, never mocking anyone.",
    ),
    AdType(
        "BRAND_STORY",
        "Brand / craft story",
        "MACRO",
        ("IMAGE", "VIDEO"),
        "Craftsmanship, packaging, behind the scenes of Luxory.",
        direction="Behind the scenes: packing, finishing, care. No invented founder quotes, workshop claims, or origin facts.",
    ),
    AdType(
        "GIFT_GUIDE",
        "Gift guide / price anchor",
        "PROMOTIONAL",
        ("IMAGE",),
        "'Gifts for her under $X' using the real price only.",
        direction="Gift-guide framing anchored on the REAL current price. No discount, no crossed-out price unless provided.",
    ),
    AdType(
        "CARE_TIPS",
        "Jewelry care",
        "FLAT_LAY",
        ("IMAGE",),
        "Care or everyday-wear tips — only claims backed by product data.",
        direction="Educational card about wearing and caring for the piece. Only materials and properties present in product data.",
    ),
]

AD_TYPES: dict[str, AdType] = {t.id: t for t in _STYLE_TYPES + _FORMAT_TYPES}
HOOK_TYPES = ("question", "bold_statement", "pov", "three_reasons", "mini_story", "comparison", "countdown", "other")
EMOTIONS = ("gifting_joy", "self_love", "elegance", "nostalgia", "celebration", "confidence", "romance", "curiosity")


def renderable(ad_type: AdType) -> bool:
    return ad_type.style in STYLE_PLAYBOOKS


def get_ad_type(ad_type_id: str | None) -> AdType:
    return AD_TYPES.get(str(ad_type_id or "").strip().upper()) or AD_TYPES["LIFESTYLE"]


def registry_payload() -> list[dict]:
    """Compact registry for prompts and the UI."""
    out = []
    for t in AD_TYPES.values():
        row = asdict(t)
        row["media"] = list(t.media)
        out.append(row)
    return out


def clamp_media(ad_type: AdType, images: int, videos: int) -> tuple[int, int]:
    images = max(0, min(int(images or 0), 4))
    videos = max(0, min(int(videos or 0), 2))
    if "VIDEO" not in ad_type.media:
        videos = 0
    if "IMAGE" not in ad_type.media:
        images = 0
    if images + videos == 0:
        images, videos = ad_type.default_images, ad_type.default_videos
        if images + videos == 0:
            images = 1
    return images, videos
