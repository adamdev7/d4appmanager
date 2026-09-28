import asyncio
import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.ai_ads.ad_package import (
    DESCRIPTION_LIMIT,
    HEADLINE_LIMIT,
    PRIMARY_TEXT_LIMIT,
    AdPackageInputs,
    apply_edits,
    build_ad_name,
    claim_warnings,
    clean_copy,
    detect_language,
    failed_package,
    generate_ad_package,
    generate_for_asset,
    is_regenerable,
    load_package,
    price_display,
    product_facts,
    regenerate_field,
    resolve_copy_language,
    sync_asset_copy,
    trim_to_limit,
)
from app.services.ai_ads.orchestrator import AdsAIOrchestrator
from app.services.ai_ads.schemas import ProductContext


class FakeClient:
    """Returns canned JSON per operation, validated through the real schema like AdsOpenAIClient."""

    def __init__(self, responses: dict, fail: Exception | None = None):
        self.responses = responses
        self.fail = fail
        self.calls: list[str] = []

    async def complete_json(self, *, system, user, schema, model, temperature=0.3, operation="complete_json", images=None):
        self.calls.append(operation)
        if self.fail:
            raise self.fail
        return schema.model_validate(self.responses[operation])


FACTS = {
    "title": "Aurora Solitaire Ring",
    "description": "18k gold plated band with a round cubic zirconia stone. Adjustable size.",
    "price": 89.0,
    "currency": "CAD",
    "url": "https://luxory.com/products/aurora-solitaire-ring",
    "collections": ["Rings"],
    "product_type": "Ring",
    "vendor": "Luxory",
    "tags": ["gift"],
    "variants": [],
    "visual_appearance": "Thin gold-tone band, single round clear stone",
}


def _inputs(**overrides) -> AdPackageInputs:
    base = dict(
        facts=dict(FACTS),
        store_name="Luxory",
        shop_domain="luxory.com",
        creative_type="IMAGE",
        aspect_ratio="4:5",
        placement="feed",
        concept="Candlelit gift reveal",
        objective="conversions",
        pixel_configured=True,
        capi_enabled=True,
        send_initiate_checkout=True,
        created_on=date(2026, 9, 28),
    )
    base.update(overrides)
    return AdPackageInputs(**base)


def _draft(**overrides) -> dict:
    draft = {
        "angle": "Gift",
        "primary_text": "The ring she'll wear every day. A single clear stone on an 18k gold plated band.\nMade to be given.",
        "headline": "A ring made to be given",
        "description": "Adjustable, gift-ready",
        "cta": "SHOP_NOW",
        "primary_text_variants": [
            {"angle": "emotional_gift", "label": "x", "text": "Give her the moment. ✨"},
            {"angle": "value_quality", "label": "x", "text": "18k gold plated, made to last."},
            {"angle": "urgency_offer", "label": "x", "text": "Her birthday is coming. Be ready."},
        ],
        "headline_variants": [
            {"angle": "emotional_gift", "text": "Made to be given"},
            {"angle": "value_quality", "text": "Everyday gold"},
            {"angle": "urgency_offer", "text": "Gift it this season"},
        ],
        "audience": {
            "interests": ["Jewelry", "Engagement rings"],
            "age_min": 24,
            "age_max": 55,
            "genders": "all",
            "notes": "Gift givers",
            "lookalike_ideas": ["1% purchasers"],
            "retargeting_ideas": ["Viewed product 30d"],
        },
    }
    draft.update(overrides)
    return draft


def test_trim_to_limit_cuts_on_word_boundary():
    text = "Timeless gold that catches every candle"
    out = trim_to_limit(text, 30)
    assert len(out) <= 30
    assert text.startswith(out)
    assert not out.endswith(" ")
    assert out.split()[-1] in text.split()


def test_trim_to_limit_prefers_sentence_end():
    text = ("Word " * 70).strip() + ". " + "More words " * 60
    out = trim_to_limit(text, PRIMARY_TEXT_LIMIT)
    assert len(out) <= PRIMARY_TEXT_LIMIT
    assert out.endswith(".")


def test_clean_copy_limits_emojis_caps_and_bangs():
    out = clean_copy("SHOP the NEW Luxory ring ✨✨✨💍!!!", multiline=False, allowed_caps={"LUXORY"})
    assert out.count("✨") + out.count("💍") == 2
    assert "SHOP" not in out and "Shop" in out
    assert "!!" not in out


def test_generate_package_enforces_limits_and_setup():
    long_headline = "An heirloom-worthy solitaire ring that she will treasure for years"
    client = FakeClient(
        {
            "ad_package": _draft(headline=long_headline, description="x" * 80, cta="BUY STUFF"),
            # Shortening pass still returns something too long: code must trim.
            "ad_package_shorten": {"items": [{"key": "headline", "text": long_headline}]},
        }
    )
    pkg = asyncio.run(generate_ad_package(client, _inputs(), language="en", model="m"))

    assert client.calls == ["ad_package", "ad_package_shorten"]
    assert len(pkg.headline) <= HEADLINE_LIMIT
    assert len(pkg.description) <= DESCRIPTION_LIMIT
    assert pkg.cta == "SHOP_NOW"
    assert [v.angle for v in pkg.primary_text_variants] == ["emotional_gift", "value_quality", "urgency_offer"]
    assert pkg.primary_text_variants[0].label == "Emotional / gift"
    assert pkg.ad_name == "AuroraSolitaireRing_Gift_Image4x5_2026-09-28"
    assert pkg.utm.utm_source == "facebook" and pkg.utm.utm_medium == "paid"
    assert pkg.utm.utm_content == pkg.ad_name
    assert pkg.destination_url.startswith("https://luxory.com/products/aurora-solitaire-ring?")
    assert "utm_content=AuroraSolitaireRing_Gift_Image4x5_2026-09-28" in pkg.destination_url
    assert pkg.campaign_objective == "OUTCOME_SALES"
    assert pkg.conversion_event == "Purchase"
    assert any("Conversions API" in n for n in pkg.tracking_notes)
    assert "Instagram Feed" in pkg.placements
    assert pkg.special_ad_category == "None"
    assert pkg.display_link == "luxory.com"
    assert pkg.audience.genders == "All"


def test_video_package_uses_vertical_placements():
    client = FakeClient({"ad_package": _draft()})
    pkg = asyncio.run(generate_ad_package(client, _inputs(creative_type="VIDEO"), language="en", model="m"))
    assert pkg.aspect_ratio == "9:16"
    assert "Instagram Reels" in pkg.placements
    assert "_Video9x16_" in pkg.ad_name


def test_claim_warnings_flag_invented_facts_only():
    warnings = claim_warnings(
        ["20% off today only, free shipping!", "18k gold plated band"],
        FACTS,
    )
    joined = " ".join(warnings)
    assert "20%" in joined
    assert "free shipping" in joined
    assert "today only" in joined
    assert "18k" not in joined


def test_language_detection_and_override():
    fr = {"title": "Bague Aurore", "description": "Une bague élégante pour vous, avec une pierre et un anneau plaqué or."}
    assert detect_language(fr) == "fr"
    assert detect_language(FACTS) == "en"
    assert resolve_copy_language("auto", fr) == "fr"
    assert resolve_copy_language("en", fr) == "en"
    assert price_display({"price": 89.5, "currency": "CAD"}, "fr") == "89,50\u00a0$"


def test_ad_name_strips_accents():
    assert build_ad_name("Collier Étoile", "Émotion", "IMAGE", "1:1", date(2026, 1, 2)) == (
        "CollierEtoile_Emotion_Image1x1_2026-01-02"
    )


def test_apply_edits_keeps_utm_content_in_sync_and_flags_over_limit():
    client = FakeClient({"ad_package": _draft()})
    pkg = asyncio.run(generate_ad_package(client, _inputs(), language="en", model="m"))
    edited = apply_edits(pkg, {"ad_name": "Renamed_Ad", "headline": "h" * 60})
    assert edited.utm.utm_content == "Renamed_Ad"
    assert "utm_content=Renamed_Ad" in edited.destination_url
    assert edited.edited is True
    assert any("Headline is 60 characters" in w for w in edited.warnings)
    assert edited.product_facts == pkg.product_facts


def test_regenerate_single_variant_keeps_other_fields():
    client = FakeClient(
        {
            "ad_package": _draft(),
            "ad_package_field": {"text": "Crafted to shine, priced to gift."},
        }
    )
    pkg = asyncio.run(generate_ad_package(client, _inputs(), language="en", model="m"))
    before = pkg.headline
    out = asyncio.run(regenerate_field(client, _inputs(), pkg, "headline_variants.1", model="m"))
    assert out.headline_variants[1].text == "Crafted to shine, priced to gift."
    assert out.headline == before
    assert is_regenerable("primary_text_variants.2")
    assert not is_regenerable("ad_name")


def test_invalid_model_json_raises_for_missing_variants():
    client = FakeClient({"ad_package": _draft(primary_text_variants=[])})
    with pytest.raises(Exception):
        asyncio.run(generate_ad_package(client, _inputs(), language="en", model="m"))


def test_copy_failure_never_fails_the_render():
    orch = object.__new__(AdsAIOrchestrator)
    orch.db = MagicMock()
    orch.db.scalar.return_value = None
    orch.store = SimpleNamespace(id="s1", name="Luxory", shop_domain="luxory.com", timezone="UTC")
    orch.client = FakeClient({}, fail=RuntimeError("OpenAI down"))
    asset = SimpleNamespace(
        id="a1",
        type="IMAGE",
        status="READY",
        aspect_ratio="4:5",
        placement="feed",
        hook="",
        headline="",
        primary_text="",
        visual_direction="",
        created_at=None,
        ad_package_json=None,
    )
    product = ProductContext(product_id="p1", title="Aurora Solitaire Ring", description="Gold ring")
    asyncio.run(
        orch._attach_ad_package(asset=asset, concept=None, product=product, request={"copy_language": "fr"})
    )
    pkg = load_package(asset.ad_package_json)
    assert asset.status == "READY"
    assert pkg is not None and pkg.status == "FAILED"
    assert pkg.language == "fr"
    assert json.loads(asset.ad_package_json)["error"]


def test_asset_card_includes_ad_package():
    from app.db.models import CreativeAsset
    from app.services.ai_ads.ad_package import AdPackage
    from app.services.ai_ads.service import _asset_card

    asset = CreativeAsset(store_id="s", user_id="u", type="IMAGE", status="READY")
    pkg = AdPackage(status="READY", language="en", headline="Gift her gold", primary_text="A ring made to be given.")
    asset.ad_package_json = pkg.model_dump_json()
    card = _asset_card(asset)
    assert card["ad_package"]["status"] == "READY"
    assert card["ad_package"]["headline"] == "Gift her gold"
    assert "product_facts" not in (card["ad_package"] or {})


def test_product_facts_include_catalog_fields():
    product = ProductContext(
        product_id="p1",
        title="Aurora Solitaire Ring",
        description="18k gold plated band",
        collections=["Rings"],
        brand_context={"product_type": "Ring", "vendor": "Luxory", "tags": ["gift"], "appearance_lock": "Thin gold-tone band"},
        restrictions=["Do not invent discounts"],
    )
    facts = product_facts(product)
    assert facts["product_type"] == "Ring"
    assert facts["visual_appearance"] == "Thin gold-tone band"
    assert facts["restrictions"] == ["Do not invent discounts"]


def test_sync_asset_copy_updates_library_fields():
    asset = SimpleNamespace(headline="old", primary_text="old", cta="LEARN_MORE")
    pkg = asyncio.run(generate_ad_package(FakeClient({"ad_package": _draft()}), _inputs(), language="en", model="m"))
    sync_asset_copy(asset, pkg)
    assert asset.headline == pkg.headline
    assert asset.primary_text == pkg.primary_text
    assert asset.cta == pkg.cta
    sync_asset_copy(asset, failed_package("en", "boom"))
    assert asset.headline == pkg.headline


def test_generate_for_asset_persists_and_syncs():
    client = FakeClient({"ad_package": _draft()})
    asset = SimpleNamespace(
        type="IMAGE",
        aspect_ratio="4:5",
        placement="feed",
        hook="",
        headline="old",
        primary_text="old",
        cta="LEARN_MORE",
        visual_direction="",
        created_at=None,
        ad_package_json=None,
    )
    db = MagicMock()
    db.scalar.return_value = None
    store = SimpleNamespace(id="s1", name="Luxory", shop_domain="luxory.com", timezone="UTC")
    pkg = asyncio.run(generate_for_asset(client, db, store, asset, dict(FACTS), model="m", language="en"))
    stored = load_package(asset.ad_package_json)
    assert stored is not None and stored.status == "READY"
    assert asset.headline == pkg.headline
    assert pkg.display_link == "luxory.com"
