"""Meta Ads Manager copy package generated alongside each rendered creative."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.services.ai_ads.complete_creative import format_appearance_lock, format_price, meta_cta
from app.services.ai_ads.prompts import (
    AD_PACKAGE,
    AD_PACKAGE_AUDIENCE,
    AD_PACKAGE_FIELD,
    AD_PACKAGE_SHORTEN,
)
from app.services.ai_ads.schemas import ProductContext

logger = logging.getLogger(__name__)

AD_PACKAGE_VERSION = 1

CopyLanguage = Literal["en", "fr"]
COPY_LANGUAGES: tuple[str, ...] = ("en", "fr")

PRIMARY_TEXT_LIMIT = 500
PRIMARY_HOOK_CHARS = 125
HEADLINE_LIMIT = 40
HEADLINE_IDEAL = 27
DESCRIPTION_LIMIT = 30
MAX_EMOJIS_PER_FIELD = 2

# Hard caps Meta's API accepts. Operator edits past the soft limits are kept but flagged.
EDIT_CAPS = {"primary_text": 2200, "headline": 255, "description": 255, "display_link": 255}

VARIANT_ANGLES: list[tuple[str, str]] = [
    ("emotional_gift", "Emotional / gift"),
    ("value_quality", "Value / quality"),
    ("urgency_offer", "Urgency / offer"),
]

SPECIAL_AD_CATEGORY_NOTE = (
    "Jewelry does not fall under Credit, Employment, Housing, Social issues, elections or politics. "
    "Double-check before publishing if the campaign promotes financing or anything outside the product."
)
AI_DISCLOSURE_NOTE = (
    "This creative was made with generative AI. In Ads Manager, keep Meta's \"AI info\" label on when "
    "people or scenes look real, and never present an AI person as a real customer."
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdCopyVariant(BaseModel):
    angle: str = ""
    label: str = ""
    text: str = Field(min_length=1)


class AdAudience(BaseModel):
    interests: list[str] = Field(default_factory=list)
    age_min: int = 18
    age_max: int = 65
    genders: str = "All"
    notes: str = ""
    lookalike_ideas: list[str] = Field(default_factory=list)
    retargeting_ideas: list[str] = Field(default_factory=list)

    @field_validator("age_min", "age_max", mode="before")
    @classmethod
    def _clamp_age(cls, v: Any, info: ValidationInfo) -> int:
        try:
            n = int(v)
        except (TypeError, ValueError):
            return 18 if info.field_name == "age_min" else 65
        return max(18, min(n, 65))

    @field_validator("genders", mode="before")
    @classmethod
    def _gender(cls, v: Any) -> str:
        token = str(v or "").strip().lower()
        if token in {"women", "woman", "female", "femmes", "f"}:
            return "Women"
        if token in {"men", "man", "male", "hommes", "m"}:
            return "Men"
        return "All"

    @field_validator("interests", "lookalike_ideas", "retargeting_ideas", mode="before")
    @classmethod
    def _str_list(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = [part for part in re.split(r"[,\n;]", v)]
        if not isinstance(v, list):
            return []
        return [str(x).strip() for x in v if str(x or "").strip()][:10]

    def model_post_init(self, __context: Any) -> None:
        if self.age_min > self.age_max:
            self.age_min, self.age_max = self.age_max, self.age_min


class AdPackageDraft(BaseModel):
    """What the model must return. Structure is validated here; lengths are enforced after."""

    angle: str = ""
    primary_text: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    description: str = ""
    cta: str = "SHOP_NOW"
    primary_text_variants: list[AdCopyVariant] = Field(min_length=3)
    headline_variants: list[AdCopyVariant] = Field(min_length=3)
    audience: AdAudience = Field(default_factory=AdAudience)


class FieldRewrite(BaseModel):
    text: str = Field(min_length=1)


class ShortenItem(BaseModel):
    key: str
    text: str


class ShortenResult(BaseModel):
    items: list[ShortenItem] = Field(default_factory=list)


class AdUtm(BaseModel):
    utm_source: str = "facebook"
    utm_medium: str = "paid"
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""


class AdPackage(BaseModel):
    version: int = AD_PACKAGE_VERSION
    status: Literal["READY", "GENERATING", "FAILED"] = "READY"
    error: str | None = None
    language: CopyLanguage = "en"
    generated_at: str | None = None
    updated_at: str | None = None
    edited: bool = False

    angle: str = ""
    primary_text: str = ""
    headline: str = ""
    description: str = ""
    cta: str = "SHOP_NOW"
    display_link: str = ""
    primary_text_variants: list[AdCopyVariant] = Field(default_factory=list)
    headline_variants: list[AdCopyVariant] = Field(default_factory=list)

    ad_name: str = ""
    base_url: str | None = None
    destination_url: str | None = None
    url_parameters: str = ""
    utm: AdUtm = Field(default_factory=AdUtm)

    campaign_objective: str = "OUTCOME_SALES"
    campaign_objective_label: str = "Sales"
    conversion_location: str = "Website"
    conversion_event: str = "Purchase"
    tracking_notes: list[str] = Field(default_factory=list)

    audience: AdAudience = Field(default_factory=AdAudience)
    placements: list[str] = Field(default_factory=list)
    aspect_ratio: str = "4:5"
    placement_notes: str = ""
    special_ad_category: str = "None"
    special_ad_category_note: str = SPECIAL_AD_CATEGORY_NOTE
    ai_generated: bool = True
    ai_disclosure_note: str = AI_DISCLOSURE_NOTE
    test_hypothesis: str = ""
    test_variable: str = ""

    warnings: list[str] = Field(default_factory=list)
    product_facts: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass
class AdPackageInputs:
    facts: dict[str, Any]
    store_name: str = ""
    shop_domain: str = ""
    creative_type: str = "IMAGE"
    aspect_ratio: str = "4:5"
    placement: str = "feed"
    concept: str = ""
    hook: str = ""
    headline: str = ""
    primary_text: str = ""
    visual_direction: str = ""
    audience_hint: str = ""
    objective: str = "conversions"
    pixel_configured: bool = False
    capi_enabled: bool = False
    send_initiate_checkout: bool = False
    created_on: date | None = None
    hypothesis: str = ""
    test_variable: str = ""


def product_facts(product: ProductContext) -> dict[str, Any]:
    """The product inputs the image prompt uses, trimmed for the copy prompt."""
    ctx = product.brand_context or {}
    variants = [
        v.title
        for v in (product.variants or [])
        if v.title and v.title.strip().lower() not in {"default", "default title"}
    ]
    appearance = format_appearance_lock(ctx.get("appearance_lock")) or str(ctx.get("appearance_lock") or "")
    return {
        "title": product.title,
        "description": (product.description or "")[:1500],
        "price": product.price,
        "currency": product.currency,
        "url": product.product_url,
        "collections": list(product.collections or [])[:8],
        "product_type": ctx.get("product_type") or "",
        "vendor": ctx.get("vendor") or "",
        "tags": list(ctx.get("tags") or [])[:15],
        "variants": variants[:12],
        "visual_appearance": appearance[:700],
        "restrictions": list(product.restrictions or [])[:6],
    }


def merge_facts(fresh: dict[str, Any], stored: dict[str, Any] | None) -> dict[str, Any]:
    """Prefer fresh catalog values; keep stored tags/collections the cached catalog row drops."""
    out = dict(stored or {})
    for key, value in fresh.items():
        if value not in (None, "", [], {}):
            out[key] = value
        else:
            out.setdefault(key, value)
    return out


# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------

_FR_MARKERS = {
    "le", "les", "des", "et", "pour", "avec", "une", "du", "est", "vous", "votre", "vos", "sur",
    "dans", "aux", "qui", "notre", "nos", "chaque", "bague", "collier", "bijou", "bijoux", "cadeau",
    "plaqué", "argent", "élégant", "élégante", "délicat", "délicate", "femme", "boucles", "oreilles",
}
_EN_MARKERS = {
    "the", "and", "for", "with", "your", "you", "this", "that", "our", "each", "ring", "necklace",
    "gift", "gold", "silver", "earrings", "bracelet", "women", "perfect", "made",
}


def detect_language(facts: dict[str, Any]) -> CopyLanguage:
    text = " ".join(
        [
            str(facts.get("title") or ""),
            str(facts.get("description") or ""),
            " ".join(str(c) for c in facts.get("collections") or []),
        ]
    ).lower()
    words = re.findall(r"[a-zàâçéèêëîïôûùüÿœ']+", text)
    fr = sum(1 for w in words if w in _FR_MARKERS)
    en = sum(1 for w in words if w in _EN_MARKERS)
    return "fr" if fr >= 3 and fr > en else "en"


def resolve_copy_language(requested: str | None, facts: dict[str, Any]) -> CopyLanguage:
    token = str(requested or "").strip().lower()
    if token in COPY_LANGUAGES:
        return token  # type: ignore[return-value]
    return detect_language(facts)


def language_directive(language: CopyLanguage) -> str:
    if language == "fr":
        return (
            "LANGUAGE: Québec French. Write it the way a Montréal copywriter would write it from scratch, "
            "not a translation of English copy. Use 'vous'. Prefer Québec usage where natural "
            "(magasiner, fin de semaine), avoid anglicisms, use « guillemets » and prices written like 129 $. "
            "Keep the cta value as the English Meta enum (e.g. SHOP_NOW) and keep the variant angle keys unchanged."
        )
    return "LANGUAGE: natural North American English."


def price_display(facts: dict[str, Any], language: CopyLanguage) -> str:
    price = facts.get("price")
    if price is None:
        return ""
    if language != "fr":
        return format_price(price, facts.get("currency"))
    try:
        amount = float(price)
    except (TypeError, ValueError):
        return ""
    whole = abs(amount - round(amount)) < 0.005
    text = f"{amount:.0f}" if whole else f"{amount:.2f}".replace(".", ",")
    code = str(facts.get("currency") or "").upper()
    symbol = {"USD": "$ US", "CAD": "$", "AUD": "$ AU", "EUR": "€", "GBP": "£"}.get(code, code)
    return f"{text}\u00a0{symbol}".strip()


# ---------------------------------------------------------------------------
# Text hygiene + limits
# ---------------------------------------------------------------------------

_EMOJI_RE = re.compile(
    "(?:[\U0001F300-\U0001FAFF\U0001F1E6-\U0001F1FF\u2600-\u27BF\u2B00-\u2BFF])\ufe0f?"
)
_CAPS_RE = re.compile(r"\b[A-ZÀ-ÖØ-Þ]{4,}\b")


def limit_emojis(text: str, max_count: int = MAX_EMOJIS_PER_FIELD) -> str:
    seen = 0

    def keep(match: re.Match[str]) -> str:
        nonlocal seen
        seen += 1
        return match.group(0) if seen <= max_count else ""

    return _EMOJI_RE.sub(keep, text)


def fix_all_caps(text: str, allowed: set[str] | None = None) -> str:
    keep = {w.upper() for w in (allowed or set())}

    def soften(match: re.Match[str]) -> str:
        word = match.group(0)
        return word if word in keep else word.capitalize()

    return _CAPS_RE.sub(soften, text)


def clean_copy(text: str, *, multiline: bool, allowed_caps: set[str] | None = None) -> str:
    raw = str(text or "").replace("\r\n", "\n").strip()
    if len(raw) >= 2 and raw[0] in "\"'“«" and raw[-1] in "\"'”»":
        raw = raw[1:-1].strip()
    raw = limit_emojis(raw)
    raw = fix_all_caps(raw, allowed_caps)
    raw = re.sub(r"([!?])\1+", r"\1", raw)
    if multiline:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.split("\n")]
        raw = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    else:
        raw = re.sub(r"\s+", " ", raw)
    return raw.strip()


def trim_to_limit(text: str, limit: int) -> str:
    """Cut at a sentence or word boundary, never mid-word."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[: limit + 1]
    sentence_end = max(window.rfind(". "), window.rfind("! "), window.rfind("? "), window.rfind("\n"))
    if sentence_end >= int(limit * 0.6):
        cut = window[: sentence_end + 1]
    else:
        space = window.rfind(" ")
        cut = window[:space] if space >= int(limit * 0.5) else text[:limit]
    return cut.rstrip(" \n,;:-–—·|/&")[:limit].strip()


def _allowed_caps(inputs: AdPackageInputs) -> set[str]:
    words = f"{inputs.store_name} {inputs.facts.get('title') or ''} {inputs.facts.get('vendor') or ''}"
    return {w for w in re.findall(r"\b[A-ZÀ-ÖØ-Þ]{4,}\b", words)}


LIMITED_KEYS = ("primary_text", "headline", "description")


def field_limit(key: str) -> int | None:
    if key == "primary_text" or key.startswith("primary_text_variants."):
        return PRIMARY_TEXT_LIMIT
    if key == "headline" or key.startswith("headline_variants."):
        return HEADLINE_LIMIT
    if key == "description":
        return DESCRIPTION_LIMIT
    return None


def _is_multiline(key: str) -> bool:
    return key == "primary_text" or key.startswith("primary_text_variants.")


def copy_keys(data: dict[str, Any]) -> list[str]:
    keys = list(LIMITED_KEYS)
    keys += [f"primary_text_variants.{i}" for i in range(len(data.get("primary_text_variants") or []))]
    keys += [f"headline_variants.{i}" for i in range(len(data.get("headline_variants") or []))]
    return keys


def get_field(data: dict[str, Any], key: str) -> str:
    if "." in key:
        group, idx = key.split(".", 1)
        items = data.get(group) or []
        i = int(idx)
        return str(items[i].get("text") or "") if 0 <= i < len(items) else ""
    return str(data.get(key) or "")


def set_field(data: dict[str, Any], key: str, value: str) -> None:
    if "." in key:
        group, idx = key.split(".", 1)
        items = data.get(group) or []
        i = int(idx)
        if 0 <= i < len(items):
            items[i]["text"] = value
        return
    data[key] = value


def _normalize_variants(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exactly one variant per canonical angle, matched by key first, then by position."""
    canonical = {angle for angle, _ in VARIANT_ANGLES}
    remaining = [it for it in items if str(it.get("text") or "").strip()]
    out: list[dict[str, Any]] = []
    for angle, label in VARIANT_ANGLES:
        item = next((it for it in remaining if str(it.get("angle") or "").strip().lower() == angle), None)
        if item is None:
            item = next(
                (it for it in remaining if str(it.get("angle") or "").strip().lower() not in canonical),
                remaining[0] if remaining else None,
            )
        if item is None:
            break
        remaining.remove(item)
        out.append({"angle": angle, "label": label, "text": str(item.get("text") or "")})
    return out


def over_limit(data: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for key in copy_keys(data):
        limit = field_limit(key)
        if limit and len(get_field(data, key)) > limit:
            out[key] = limit
    return out


def sanitize_draft(draft: AdPackageDraft, inputs: AdPackageInputs) -> dict[str, Any]:
    data = draft.model_dump()
    data["primary_text_variants"] = _normalize_variants(data.get("primary_text_variants") or [])
    data["headline_variants"] = _normalize_variants(data.get("headline_variants") or [])
    caps = _allowed_caps(inputs)
    for key in copy_keys(data):
        set_field(data, key, clean_copy(get_field(data, key), multiline=_is_multiline(key), allowed_caps=caps))
    data["cta"] = meta_cta(data.get("cta"))
    data["angle"] = clean_copy(data.get("angle") or "", multiline=False)[:40]
    return data


def enforce_limits(data: dict[str, Any]) -> dict[str, Any]:
    for key, limit in over_limit(data).items():
        set_field(data, key, trim_to_limit(get_field(data, key), limit))
    return data


async def shorten_fields(
    client: Any,
    data: dict[str, Any],
    inputs: AdPackageInputs,
    language: CopyLanguage,
    model: str,
) -> dict[str, Any]:
    """One model pass to rewrite over-limit fields tighter. Anything still long is trimmed after."""
    long = over_limit(data)
    if not long:
        return data
    payload = [
        {"key": key, "limit": limit, "current_length": len(get_field(data, key)), "text": get_field(data, key)}
        for key, limit in long.items()
    ]
    try:
        result = await client.complete_json(
            system=AD_PACKAGE_SHORTEN,
            user=f"{language_directive(language)}\n\nFIELDS:\n{json.dumps(payload, ensure_ascii=False)}",
            schema=ShortenResult,
            model=model,
            temperature=0.4,
            operation="ad_package_shorten",
        )
    except Exception as exc:
        logger.warning("ai_ads ad package shorten failed err=%s", str(exc)[:200])
        return data
    caps = _allowed_caps(inputs)
    for item in getattr(result, "items", []) or []:
        if item.key in long and item.text.strip():
            set_field(data, item.key, clean_copy(item.text, multiline=_is_multiline(item.key), allowed_caps=caps))
    return data


# ---------------------------------------------------------------------------
# Setup fields computed in code
# ---------------------------------------------------------------------------

_OBJECTIVES = {
    "conversions": ("OUTCOME_SALES", "Sales"),
    "sales": ("OUTCOME_SALES", "Sales"),
    "traffic": ("OUTCOME_TRAFFIC", "Traffic"),
    "awareness": ("OUTCOME_AWARENESS", "Awareness"),
    "engagement": ("OUTCOME_ENGAGEMENT", "Engagement"),
}

_PLACEMENTS: dict[str, tuple[list[str], str]] = {
    "1:1": (
        ["Facebook Feed", "Instagram Feed", "Instagram Explore", "Facebook Marketplace"],
        "1:1 runs cleanly across feeds. Add a 9:16 version for Stories and Reels so Meta does not letterbox it.",
    ),
    "4:5": (
        ["Facebook Feed", "Instagram Feed", "Instagram Explore", "Facebook Marketplace"],
        "4:5 takes the most space in mobile feeds. A few placements crop it to 1:1, so keep the jewelry centered.",
    ),
    "9:16": (
        ["Instagram Stories", "Instagram Reels", "Facebook Stories", "Facebook Reels"],
        "9:16 is full screen. Keep the product and any text out of the top 14% and bottom 20%, "
        "where the Stories and Reels UI sits.",
    ),
    "16:9": (
        ["Facebook Feed", "Facebook In-stream video", "Audience Network"],
        "16:9 is best for in-stream. Prefer a 4:5 or 9:16 version for mobile feeds and Stories.",
    ),
}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode("ascii")


def pascal_token(text: str, limit: int = 40) -> str:
    words = re.findall(r"[A-Za-z0-9]+", _ascii(text))
    return "".join(w[:1].upper() + w[1:] for w in words)[:limit]


def slug(text: str, limit: int = 60) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _ascii(text).lower()).strip("-")[:limit].strip("-")


def format_token(creative_type: str, aspect_ratio: str) -> str:
    kind = "Video" if (creative_type or "").upper() == "VIDEO" else "Image"
    return f"{kind}{(aspect_ratio or '4:5').replace(':', 'x')}"


def build_ad_name(product_title: str, angle: str, creative_type: str, aspect_ratio: str, on: date) -> str:
    return "_".join(
        [
            pascal_token(product_title) or "Product",
            pascal_token(angle, 24) or "Main",
            format_token(creative_type, aspect_ratio),
            on.isoformat(),
        ]
    )


def with_query(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k not in params]
    query += [(k, v) for k, v in params.items() if v]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def apply_tracking(pkg: AdPackage) -> AdPackage:
    params = {k: v for k, v in pkg.utm.model_dump().items() if v}
    pkg.url_parameters = urlencode(params)
    pkg.destination_url = with_query(pkg.base_url, params) if pkg.base_url else None
    return pkg


def display_link_for(shop_domain: str) -> str:
    domain = (shop_domain or "").replace("https://", "").replace("http://", "").strip("/").lower()
    if not domain or domain.endswith(".myshopify.com"):
        return ""
    return domain.removeprefix("www.")


def tracking_notes(inputs: AdPackageInputs, objective_label: str) -> list[str]:
    notes: list[str] = []
    if objective_label != "Sales":
        notes.append(
            f"This creative was planned for {objective_label}. For launch-ready jewelry sales, run it in a "
            "Sales campaign optimized for Purchase."
        )
    if inputs.capi_enabled and inputs.pixel_configured:
        notes.append(
            "Purchase reaches Meta from both the browser Pixel and App Manager's Conversions API, "
            "deduplicated by event_id. Optimize the ad set for Purchase."
        )
    else:
        notes.append(
            "Server-Side Tracking (Conversions API) is not enabled in App Manager, so Purchase relies on the "
            "browser Pixel only. Turn it on for more reliable attribution."
        )
    if inputs.capi_enabled and inputs.send_initiate_checkout:
        notes.append(
            "Initiate Checkout is also sent server-side. If the ad set cannot reach about 50 purchases a week, "
            "test optimizing for Initiate Checkout (or Add to Cart from the Pixel) while it learns."
        )
    else:
        notes.append(
            "Add to Cart and Initiate Checkout come from the browser Pixel. Use them as a fallback "
            "optimization event if purchases are too sparse to exit the learning phase."
        )
    notes.append("Select your Pixel/dataset in the ad set conversion settings and keep the URL parameters so UTMs reach Shopify.")
    return notes


# ---------------------------------------------------------------------------
# Warnings
# ---------------------------------------------------------------------------

_CLAIM_CHECKS: list[tuple[str, str]] = [
    (r"\d+\s?%|\bpercent off\b|\brabais\b|\bsoldes?\b|\bsale\b", "a discount"),
    (r"\bfree shipping\b|\bships free\b|\blivraison gratuite\b", "free shipping"),
    (r"\breviews?\b|\bavis clients?\b|★|\b\d(?:[.,]\d)?\s?(?:stars?|étoiles)\b|\bbest-?sellers?\b|\bcustomers love\b", "reviews or bestseller status"),
    (
        r"\blimited time\b|\btoday only\b|\blast chance\b|\bselling fast\b|\bonly \d+ left\b|\balmost gone\b"
        r"|\bdernière chance\b|\baujourd'hui seulement\b|\bquantités? limitées?\b|\bstock limité\b",
        "urgency or scarcity",
    ),
    (r"\bbefore (?:and|&) after\b|\bavant[- /]après\b", "a before/after claim"),
    (
        r"\b(?:9|10|14|18|22|24)\s?k(?:t|arats?)?\b|\bkarats?\b|\bcarats?\b|\bsterling\b|\b925\b|\bdiamonds?\b"
        r"|\bdiamants?\b|\bmoissanite\b|\bgold[- ]plated\b|\bplaqué or\b|\bsolid gold\b|\bor massif\b",
        "a material or stone spec",
    ),
    (r"\bships? (?:in|within)\b|\bdelivered in\b|\blivré en\b|\bexpédié en\b|\bnext[- ]day\b", "a shipping time"),
    (r"\bwarrant(?:y|ies)\b|\bgarantie\b|\blifetime\b|\bà vie\b|\bmoney[- ]back\b", "a warranty or guarantee"),
]


def _source_text(facts: dict[str, Any]) -> str:
    parts = [
        facts.get("title"),
        facts.get("description"),
        facts.get("product_type"),
        facts.get("vendor"),
        " ".join(str(x) for x in facts.get("collections") or []),
        " ".join(str(x) for x in facts.get("tags") or []),
        " ".join(str(x) for x in facts.get("variants") or []),
    ]
    return " ".join(str(p or "") for p in parts).lower()


def claim_warnings(texts: list[str], facts: dict[str, Any] | None) -> list[str]:
    if not facts:
        return []
    source = _source_text(facts)
    out: list[str] = []
    seen: set[str] = set()
    blob = "\n".join(texts)
    for pattern, category in _CLAIM_CHECKS:
        for match in re.finditer(pattern, blob, flags=re.IGNORECASE):
            token = match.group(0).strip().lower()
            if not token or token in seen or token in source:
                continue
            seen.add(token)
            out.append(
                f"Copy mentions “{match.group(0).strip()}” ({category}), which is not in the product data. "
                "Verify or remove before launch."
            )
    return out


def hook_warning(text: str, label: str) -> str | None:
    if len(text) <= PRIMARY_HOOK_CHARS:
        return None
    head = text[:PRIMARY_HOOK_CHARS]
    if re.search(r"[.!?…](\s|$)|\n", head):
        return None
    return f"{label}: the first sentence runs past {PRIMARY_HOOK_CHARS} characters, so the hook gets cut off by “See more”."


def build_warnings(pkg: AdPackage) -> list[str]:
    out: list[str] = []
    checks = [
        ("Primary text", pkg.primary_text, PRIMARY_TEXT_LIMIT),
        ("Headline", pkg.headline, HEADLINE_LIMIT),
        ("Description", pkg.description, DESCRIPTION_LIMIT),
    ]
    checks += [(f"Primary text ({v.label})", v.text, PRIMARY_TEXT_LIMIT) for v in pkg.primary_text_variants]
    checks += [(f"Headline ({v.label})", v.text, HEADLINE_LIMIT) for v in pkg.headline_variants]
    for label, text, limit in checks:
        if len(text) > limit:
            out.append(f"{label} is {len(text)} characters, over the {limit}-character limit.")
    if HEADLINE_IDEAL < len(pkg.headline) <= HEADLINE_LIMIT:
        out.append(f"Headline is {len(pkg.headline)} characters. Under {HEADLINE_IDEAL} avoids truncation on mobile.")
    for label, text in [("Primary text", pkg.primary_text)] + [
        (f"Primary text ({v.label})", v.text) for v in pkg.primary_text_variants
    ]:
        warn = hook_warning(text, label)
        if warn:
            out.append(warn)
    if not pkg.display_link:
        out.append("No public domain on file for the display link. Add yours (e.g. luxory.com) or leave it blank.")
    if not pkg.base_url:
        out.append("No product URL on file. Paste the product page link before publishing.")
    texts = [pkg.primary_text, pkg.headline, pkg.description]
    texts += [v.text for v in pkg.primary_text_variants] + [v.text for v in pkg.headline_variants]
    out += claim_warnings(texts, pkg.product_facts)
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def assemble_package(data: dict[str, Any], inputs: AdPackageInputs, language: CopyLanguage) -> AdPackage:
    on = inputs.created_on or datetime.now(UTC).date()
    angle = data.get("angle") or inputs.concept or "Main"
    title = str(inputs.facts.get("title") or "Product")
    aspect = "9:16" if (inputs.creative_type or "").upper() == "VIDEO" else (inputs.aspect_ratio or "4:5")
    ad_name = build_ad_name(title, angle, inputs.creative_type, aspect, on)
    objective, objective_label = _OBJECTIVES.get(
        (inputs.objective or "conversions").strip().lower(), _OBJECTIVES["conversions"]
    )
    placements, placement_notes = _PLACEMENTS.get(aspect, _PLACEMENTS["4:5"])
    base_url = inputs.facts.get("url") or None
    utm = AdUtm(
        utm_campaign=f"{slug(title, 40) or 'product'}_{slug(objective_label)}_{on.strftime('%Y-%m')}",
        utm_content=ad_name,
        utm_term=slug(angle, 40) or "main",
    )
    pkg = AdPackage(
        status="READY",
        language=language,
        generated_at=_now_iso(),
        updated_at=_now_iso(),
        angle=angle,
        primary_text=data.get("primary_text") or "",
        headline=data.get("headline") or "",
        description=data.get("description") or "",
        cta=meta_cta(data.get("cta")),
        display_link=display_link_for(inputs.shop_domain),
        primary_text_variants=[AdCopyVariant(**v) for v in data.get("primary_text_variants") or []],
        headline_variants=[AdCopyVariant(**v) for v in data.get("headline_variants") or []],
        ad_name=ad_name,
        base_url=base_url,
        utm=utm,
        campaign_objective=objective,
        campaign_objective_label=objective_label,
        conversion_event="Purchase",
        tracking_notes=tracking_notes(inputs, objective_label),
        audience=AdAudience.model_validate(data.get("audience") or {}),
        placements=list(placements),
        aspect_ratio=aspect,
        placement_notes=placement_notes,
        test_hypothesis=inputs.hypothesis,
        test_variable=inputs.test_variable,
        product_facts=inputs.facts,
    )
    apply_tracking(pkg)
    pkg.warnings = build_warnings(pkg)
    return pkg


def product_payload(inputs: AdPackageInputs, language: CopyLanguage) -> dict[str, Any]:
    facts = dict(inputs.facts)
    facts["price_display"] = price_display(facts, language)
    facts["brand"] = inputs.store_name or facts.get("vendor") or ""
    facts.pop("url", None)
    return facts


def creative_payload(inputs: AdPackageInputs) -> dict[str, Any]:
    return {
        "type": inputs.creative_type,
        "aspect_ratio": inputs.aspect_ratio,
        "placement": inputs.placement,
        "concept": inputs.concept,
        "planned_hook": inputs.hook,
        "planned_headline": inputs.headline,
        "planned_primary_text": inputs.primary_text[:600],
        "visual_direction": inputs.visual_direction[:600],
        "audience_hint": inputs.audience_hint,
        "objective": inputs.objective,
    }


def _context_prompt(inputs: AdPackageInputs, language: CopyLanguage) -> str:
    return (
        f"{language_directive(language)}\n\n"
        "PRODUCT (the only source of facts):\n"
        f"{json.dumps(product_payload(inputs, language), ensure_ascii=False, default=str)}\n\n"
        "CREATIVE (what the rendered ad shows and the angle it was planned with):\n"
        f"{json.dumps(creative_payload(inputs), ensure_ascii=False, default=str)}"
    )


async def generate_ad_package(
    client: Any,
    inputs: AdPackageInputs,
    *,
    language: CopyLanguage,
    model: str,
) -> AdPackage:
    draft = await client.complete_json(
        system=AD_PACKAGE,
        user=_context_prompt(inputs, language),
        schema=AdPackageDraft,
        model=model,
        temperature=0.7,
        operation="ad_package",
    )
    data = sanitize_draft(draft, inputs)
    data = await shorten_fields(client, data, inputs, language, model)
    return assemble_package(enforce_limits(data), inputs, language)


REGENERABLE_FIELDS = ("primary_text", "headline", "description", "cta", "audience")


def is_regenerable(field_key: str) -> bool:
    if field_key in REGENERABLE_FIELDS:
        return True
    match = re.fullmatch(r"(primary_text_variants|headline_variants)\.([0-2])", field_key or "")
    return bool(match)


async def regenerate_field(
    client: Any,
    inputs: AdPackageInputs,
    pkg: AdPackage,
    field_key: str,
    *,
    model: str,
) -> AdPackage:
    language = pkg.language
    current = pkg.model_dump(exclude={"product_facts", "warnings", "tracking_notes"})
    context = _context_prompt(inputs, language)
    if field_key == "audience":
        audience = await client.complete_json(
            system=AD_PACKAGE_AUDIENCE,
            user=f"{context}\n\nCURRENT AUDIENCE:\n{json.dumps(current['audience'], ensure_ascii=False)}",
            schema=AdAudience,
            model=model,
            temperature=0.7,
            operation="ad_package_audience",
        )
        pkg.audience = AdAudience.model_validate(audience.model_dump())
    else:
        limit = field_limit(field_key)
        angle_note = ""
        if "." in field_key:
            group, idx = field_key.split(".", 1)
            variant = (current.get(group) or [{}])[int(idx)] if int(idx) < len(current.get(group) or []) else {}
            angle_note = f"This is the {variant.get('label') or 'variant'} angle. Keep that angle."
        elif field_key == "cta":
            angle_note = "Return one Meta CTA enum value only."
        ask = {
            "field": field_key,
            "limit_chars": limit,
            "current_value": get_field(current, field_key) if field_key != "cta" else current.get("cta"),
            "main_angle": current.get("angle"),
            "other_fields": {
                "primary_text": current.get("primary_text"),
                "headline": current.get("headline"),
                "description": current.get("description"),
            },
        }
        rewrite = await client.complete_json(
            system=AD_PACKAGE_FIELD,
            user=f"{context}\n\n{angle_note}\nREWRITE:\n{json.dumps(ask, ensure_ascii=False)}",
            schema=FieldRewrite,
            model=model,
            temperature=0.8,
            operation="ad_package_field",
        )
        if field_key == "cta":
            pkg.cta = meta_cta(rewrite.text)
        else:
            data = pkg.model_dump()
            text = clean_copy(rewrite.text, multiline=_is_multiline(field_key), allowed_caps=_allowed_caps(inputs))
            set_field(data, field_key, text)
            if limit and len(text) > limit:
                data = await shorten_fields(client, data, inputs, language, model)
            data = enforce_limits(data)
            pkg = AdPackage.model_validate(data)
    pkg.status = "READY"
    pkg.error = None
    pkg.updated_at = _now_iso()
    pkg.warnings = build_warnings(pkg)
    return pkg


def apply_edits(existing: AdPackage | None, raw: dict[str, Any]) -> AdPackage:
    """Operator edits. Kept even when over the soft limits (flagged), capped at Meta's hard limits."""
    base = existing.model_dump() if existing else {}
    protected = {
        "product_facts",
        "version",
        "generated_at",
        "status",
        "error",
        "warnings",
        "tracking_notes",
        "ai_generated",
        "ai_disclosure_note",
    }
    merged = {**base, **{k: v for k, v in raw.items() if k not in protected}}
    previous_name = (existing.ad_name if existing else "") or ""
    previous_content = (existing.utm.utm_content if existing else "") or ""
    pkg = AdPackage.model_validate(merged)
    for key, cap in EDIT_CAPS.items():
        setattr(pkg, key, str(getattr(pkg, key) or "")[:cap])
    pkg.primary_text_variants = [
        AdCopyVariant(angle=v.angle, label=v.label, text=v.text[: EDIT_CAPS["primary_text"]])
        for v in pkg.primary_text_variants
    ]
    pkg.headline_variants = [
        AdCopyVariant(angle=v.angle, label=v.label, text=v.text[: EDIT_CAPS["headline"]])
        for v in pkg.headline_variants
    ]
    pkg.cta = meta_cta(pkg.cta)
    if pkg.ad_name != previous_name and pkg.utm.utm_content == previous_content:
        pkg.utm.utm_content = pkg.ad_name
    pkg.status = "READY"
    pkg.error = None
    pkg.edited = True
    pkg.updated_at = _now_iso()
    if existing:
        pkg.tracking_notes = existing.tracking_notes
    apply_tracking(pkg)
    pkg.warnings = build_warnings(pkg)
    return pkg


def pending_package(language: CopyLanguage, facts: dict[str, Any] | None = None) -> AdPackage:
    return AdPackage(status="GENERATING", language=language, product_facts=facts or {})


def failed_package(language: CopyLanguage, error: str) -> AdPackage:
    return AdPackage(status="FAILED", language=language, error=error[:400])


def load_package(raw: str | None) -> AdPackage | None:
    if not raw:
        return None
    try:
        return AdPackage.model_validate(json.loads(raw))
    except Exception:
        logger.warning("ai_ads stored ad package unreadable")
        return None


def package_card(raw: str | None) -> dict[str, Any] | None:
    pkg = load_package(raw)
    if not pkg:
        return None
    return pkg.model_dump(exclude={"product_facts"})


def local_date(moment: datetime | None, timezone: str | None) -> date:
    moment = moment or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    try:
        return moment.astimezone(ZoneInfo(timezone or "UTC")).date()
    except Exception:
        return moment.astimezone(UTC).date()


def build_inputs(
    db: Any,
    store: Any,
    asset: Any,
    facts: dict[str, Any],
    *,
    concept: Any = None,
    request: dict[str, Any] | None = None,
) -> AdPackageInputs:
    from sqlalchemy import select

    from app.db.models import StoreMetaCapiSettings

    capi = db.scalar(select(StoreMetaCapiSettings).where(StoreMetaCapiSettings.store_id == store.id))
    request = request or {}
    concept_label = ""
    if concept is not None:
        concept_label = str(getattr(concept, "concept_name", "") or getattr(concept, "angle", "") or "")[:80]
    return AdPackageInputs(
        facts=facts,
        store_name=getattr(store, "name", "") or "",
        shop_domain=getattr(store, "shop_domain", "") or "",
        creative_type=asset.type or "IMAGE",
        aspect_ratio=asset.aspect_ratio or "4:5",
        placement=asset.placement or "feed",
        concept=concept_label,
        hook=asset.hook or "",
        headline=asset.headline or "",
        primary_text=asset.primary_text or "",
        visual_direction=asset.visual_direction or "",
        audience_hint=str(request.get("audience") or ""),
        objective=str(request.get("objective") or "conversions"),
        pixel_configured=bool(capi and capi.meta_pixel_id),
        capi_enabled=bool(capi and capi.enabled),
        send_initiate_checkout=bool(capi and capi.send_initiate_checkout),
        created_on=local_date(asset.created_at, getattr(store, "timezone", None)),
        hypothesis=str(getattr(concept, "hypothesis", "") or "")[:500],
        test_variable=str(getattr(concept, "test_variable", "") or "")[:64],
    )


async def generate_for_asset(
    client: Any,
    db: Any,
    store: Any,
    asset: Any,
    facts: dict[str, Any],
    *,
    model: str,
    concept: Any = None,
    request: dict[str, Any] | None = None,
    language: str | None = None,
) -> AdPackage:
    """Generate and attach a package to the asset. The caller commits."""
    inputs = build_inputs(db, store, asset, facts, concept=concept, request=request)
    lang = resolve_copy_language(language, facts)
    pkg = await generate_ad_package(client, inputs, language=lang, model=model)
    asset.ad_package_json = pkg.model_dump_json()
    sync_asset_copy(asset, pkg)
    return pkg


def sync_asset_copy(asset: Any, pkg: AdPackage) -> None:
    """Keep the library card in sync with the Ads Manager headline, body, and CTA."""
    if pkg.status != "READY":
        return
    if pkg.headline:
        asset.headline = pkg.headline
    if pkg.primary_text:
        asset.primary_text = pkg.primary_text
    if pkg.cta:
        asset.cta = pkg.cta
