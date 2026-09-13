import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.ai_ads.creative_planner import allocate_portfolio
from app.services.ai_ads.exceptions import ImageGenerationError, InvalidAIOutput
from app.services.ai_ads.meta_importer import fingerprint_creative, infer_format, normalize_meta_ad
from app.services.ai_ads.performance_analyzer import normalize_insight_row, percentile_ranks, split_performance_groups
from app.services.ai_ads.product_context import normalize_product
from app.services.ai_ads.schemas import (
    CreativeConceptModel,
    CreativeDNAModel,
    CreativeStrategyModel,
    PerformanceDNA,
    ProductContext,
)
from app.services.ai_ads.service import AIAdsService


def test_product_context_normalization_does_not_invent_facts():
    raw = {
        "id": 11,
        "title": "Glow Serum",
        "body_html": "<p>Hydrating serum</p>",
        "handle": "glow-serum",
        "vendor": "Acme",
        "product_type": "Skincare",
        "tags": "vegan, glow",
        "images": [{"src": "https://cdn.example/p.jpg", "width": 800, "height": 800}],
        "variants": [{"id": 2, "title": "Default", "price": "29.00", "sku": "GS-1"}],
    }
    ctx = normalize_product(raw, shop_domain="shop.myshopify.com", currency="USD")
    assert isinstance(ctx, ProductContext)
    assert ctx.product_id == "11"
    assert ctx.title == "Glow Serum"
    assert "Hydrating serum" in ctx.description
    assert ctx.price == 29.0
    assert ctx.currency == "USD"
    assert ctx.images[0].src.endswith("p.jpg")
    assert "Do not invent" in ctx.restrictions[0]
    assert "miracle" not in ctx.description.lower()


def test_product_context_empty_description_adds_restriction():
    ctx = normalize_product({"id": "1", "title": "X"}, shop_domain="a.myshopify.com")
    assert any("empty" in r.lower() for r in ctx.restrictions)


def test_meta_creative_normalization_image_and_copy():
    ad = {
        "id": "111",
        "name": "Prospecting A",
        "campaign_id": "c1",
        "adset_id": "s1",
        "created_time": "2026-01-02T00:00:00+0000",
        "creative": {
            "id": "cr9",
            "object_type": "SHARE",
            "image_url": "https://fbcdn/img.jpg",
            "thumbnail_url": "https://fbcdn/thumb.jpg",
            "object_story_spec": {
                "link_data": {
                    "message": "See the glow",
                    "name": "Glow Serum",
                    "description": "Shop the serum",
                    "link": "https://shop.example/p",
                    "call_to_action": {"type": "SHOP_NOW"},
                    "picture": "https://fbcdn/img.jpg",
                }
            },
        },
    }
    norm = normalize_meta_ad(ad, campaigns={"c1": "Prospecting"}, adsets={"s1": "Broad"})
    assert norm.ad_id == "111"
    assert norm.campaign_name == "Prospecting"
    assert norm.headline == "Glow Serum"
    assert norm.primary_text == "See the glow"
    assert norm.cta == "SHOP_NOW"
    assert norm.format == "IMAGE"
    assert norm.image_url.endswith("img.jpg")
    assert norm.creative_fingerprint


def test_meta_creative_normalization_video():
    ad = {
        "id": "222",
        "creative": {
            "id": "v1",
            "object_type": "VIDEO",
            "video_id": "999",
            "object_story_spec": {"video_data": {"video_id": "999", "message": "Watch this", "title": "Hook"}},
        },
    }
    norm = normalize_meta_ad(ad, campaigns={}, adsets={})
    assert norm.format == "VIDEO"
    assert norm.video_id == "999"
    assert norm.headline == "Hook"


def test_infer_format_carousel():
    assert infer_format({}, video_id=None, image_url=None, feed={"images": [{}, {}]}) == "CAROUSEL"


def test_fingerprint_stable():
    a = fingerprint_creative({"creative_id": "1", "headline": "A"})
    b = fingerprint_creative({"headline": "A", "creative_id": "1"})
    assert a == b


def test_performance_normalization_keeps_nulls():
    row = {"impressions": "1000", "spend": "40", "inline_link_clicks": "20"}
    summary = normalize_insight_row(row, since="2026-09-01", until="2026-09-07")
    assert summary.impressions == 1000
    assert summary.spend == 40
    assert summary.clicks == 20
    assert summary.purchases is None or summary.purchases == 0
    assert summary.date_range_start == "2026-09-01"


def test_performance_insufficient_when_no_impressions():
    summary = normalize_insight_row({})
    assert summary.insufficient_data is True
    assert summary.impressions is None


def test_percentiles_omitted_without_enough_data():
    from app.services.ai_ads.schemas import PerformanceSummary

    ranks = percentile_ranks([PerformanceSummary(ctr=1.0)])
    assert ranks == {}


def test_percentiles_from_actual_values():
    from app.services.ai_ads.schemas import PerformanceSummary

    summaries = [
        PerformanceSummary(ctr=1.0, roas=1.0, cpa=50, spend=10),
        PerformanceSummary(ctr=3.0, roas=4.0, cpa=10, spend=80),
        PerformanceSummary(ctr=2.0, roas=2.0, cpa=20, spend=40),
    ]
    ranks = percentile_ranks(summaries)
    assert ranks[1]["ctr_percentile"] == 1.0
    assert ranks[0]["ctr_percentile"] == 0.0
    assert ranks[1]["cpa_percentile"] == 1.0  # lowest CPA is best


def test_split_groups_needs_three():
    groups = split_performance_groups(
        [
            {"id": "a", "performance": {"roas": 4, "spend": 50}},
            {"id": "b", "performance": {"roas": 1, "spend": 50}},
        ]
    )
    assert groups["insufficient"] is True


def test_creative_dna_rejects_fake_percentiles():
    with pytest.raises(ValidationError):
        PerformanceDNA(ctr_percentile=1.5)


def test_creative_dna_schema():
    dna = CreativeDNAModel.model_validate(
        {
            "visual_dna": {"style": "ugc", "human_presence": True, "product_visibility": "high"},
            "copy_dna": {"hook_type": "problem_solution", "cta": "shop_now"},
            "format_dna": {"type": "image", "aspect_ratio": "4:5"},
            "performance_dna": {"ctr_percentile": 0.91},
            "analysis_basis": "image",
            "observed": ["Close-up product"],
            "interpretation": ["May signal lifestyle context"],
        }
    )
    assert dna.visual_dna.style == "ugc"
    assert dna.performance_dna.ctr_percentile == 0.91


def test_strategy_and_concept_schemas():
    strategy = CreativeStrategyModel.model_validate(
        {"summary": "Lead with product close-ups", "confidence": 0.6, "winning_patterns": ["close_up"]}
    )
    concept = CreativeConceptModel.model_validate(
        {
            "concept_name": "Close-up UGC",
            "type": "IMAGE",
            "hook": "See it up close",
            "portfolio_bucket": "winner_variation",
            "source_creative_ids": ["abc"],
        }
    )
    assert strategy.summary
    assert concept.source_creative_ids == ["abc"]


def test_portfolio_allocation_sums_to_n():
    buckets = allocate_portfolio(10)
    assert len(buckets) == 10
    assert buckets.count("winner_variation") == 4
    assert buckets.count("combination") == 3
    assert buckets.count("exploration") == 2
    assert buckets.count("experimental") == 1


def test_portfolio_allocation_zero():
    assert allocate_portfolio(0) == []


def test_job_status_values():
    from app.db.models import CreativeGenerationJob

    job = CreativeGenerationJob(store_id="s", user_id="u", status="QUEUED")
    assert job.status == "QUEUED"
    job.status = "RUNNING"
    assert job.status == "RUNNING"


def test_authorization_rejects_foreign_store():
    service = AIAdsService()
    user = SimpleNamespace(id="user-1")
    db = MagicMock()
    db.get.return_value = SimpleNamespace(id="store-2", owner_id="someone-else")
    with pytest.raises(HTTPException) as exc:
        service.ensure_store(db, user, "store-2")
    assert exc.value.status_code == 404


def test_authorization_accepts_owner():
    service = AIAdsService()
    user = SimpleNamespace(id="user-1")
    store = SimpleNamespace(id="store-1", owner_id="user-1")
    db = MagicMock()
    db.get.return_value = store
    assert service.ensure_store(db, user, "store-1") is store


def test_image_provider_saves_bytes():
    import asyncio

    from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
    from app.services.ai_ads.schemas import ImageGenerationRequest

    client = SimpleNamespace(generate_image_b64=AsyncMock(return_value=(b"\x89PNG\r\n\x1a\n" + b"x" * 20, "image/png")))
    store = MagicMock()
    store.save_bytes.return_value = {
        "relative_path": "ai-ads/s/gen.png",
        "public_url": "/uploads/ai-ads/s/gen.png",
    }
    provider = OpenAIImageProvider(client, store, model="gpt-image-2")
    result = asyncio.run(provider.generate(ImageGenerationRequest(prompt="product on marble", aspect_ratio="1:1")))
    assert result.status == "completed"
    assert result.preview_url.endswith("gen.png")
    client.generate_image_b64.assert_awaited()


def test_image_provider_failure_is_typed():
    import asyncio

    from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
    from app.services.ai_ads.schemas import ImageGenerationRequest

    client = SimpleNamespace(generate_image_b64=AsyncMock(side_effect=RuntimeError("boom")))
    provider = OpenAIImageProvider(client, MagicMock(), model="x")
    with pytest.raises(ImageGenerationError):
        asyncio.run(provider.generate(ImageGenerationRequest(prompt="x")))


def test_meta_importer_skips_unchanged_hash_logic():
    first = fingerprint_creative({"creative_id": "1", "image_url": "a"})
    second = fingerprint_creative({"creative_id": "1", "image_url": "a"})
    third = fingerprint_creative({"creative_id": "1", "image_url": "b"})
    assert first == second
    assert first != third


def test_openai_json_retry_on_invalid_output():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient
    from app.services.ai_ads.schemas import CreativeStrategyModel

    client = AdsOpenAIClient("sk-test", store_id="s")
    bad = json.dumps({"confidence": "nope"})
    good = json.dumps({"summary": "ok", "confidence": 0.2})
    with patch.object(client, "_chat", new=AsyncMock(side_effect=[bad, good])):
        result = asyncio.run(
            client.complete_json(
                system="sys",
                user="user",
                schema=CreativeStrategyModel,
                model="gpt-test",
            )
        )
    assert result.summary == "ok"


def test_openai_json_failure_after_retry():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient

    client = AdsOpenAIClient("sk-test", store_id="s")
    with patch.object(client, "_chat", new=AsyncMock(return_value='{"confidence":"bad"}')):
        with pytest.raises(InvalidAIOutput):
            asyncio.run(
                client.complete_json(
                    system="sys",
                    user="user",
                    schema=CreativeStrategyModel,
                    model="gpt-test",
                )
            )


def test_unconfigured_video_provider_does_not_call_vendor():
    import asyncio

    from app.services.ai_ads.providers.video_provider import UnconfiguredVideoProvider

    provider = UnconfiguredVideoProvider()
    result = asyncio.run(provider.generate_video({"duration": 15}))
    assert result["status"] == "planned"
    assert result["provider"] is None


def test_gpt6_omits_custom_temperature():
    from app.services.ai_ads.openai_client import model_omits_temperature, should_retry_without_temperature

    assert model_omits_temperature("gpt-6-astra")
    assert model_omits_temperature("gpt-5.4")
    assert not model_omits_temperature("gpt-4o-mini")
    body = "Unsupported value: 'temperature' does not support 0.5 with this model. Only the default (1) value is supported."
    assert should_retry_without_temperature({"temperature": 0.5}, 400, body)
    assert not should_retry_without_temperature({}, 400, body)


def test_complete_text_skips_temperature_for_gpt6():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient

    client = AdsOpenAIClient("sk-test", store_id="s")
    seen: dict = {}

    async def capture(payload, **_kwargs):
        seen.update(payload)
        return "ok"

    with patch.object(client, "_chat", new=AsyncMock(side_effect=capture)):
        out = asyncio.run(client.complete_text(system="s", user="u", model="gpt-6-astra"))
    assert out == "ok"
    assert "temperature" not in seen


def test_storyboard_preview_from_video_asset():
    from app.services.ai_ads.service import _storyboard_preview

    asset = SimpleNamespace(
        type="VIDEO",
        video_spec_json=json.dumps(
            {
                "spec": {
                    "hook": "Open on the bracelet",
                    "duration": 15,
                    "format": "9:16",
                    "cta": "SHOP_NOW",
                    "scenes": [
                        {
                            "duration": 3,
                            "visual": "Close-up on clasp",
                            "text_overlay": "Courage",
                            "voiceover": "Feel the courage",
                        }
                    ],
                }
            }
        ),
    )
    preview = _storyboard_preview(asset)
    assert preview is not None
    assert preview["duration"] == 15
    assert preview["scenes"][0]["visual"] == "Close-up on clasp"
    assert preview["scenes"][0]["voiceover"] == "Feel the courage"


def test_clamp_generation_counts_caps_token_use():
    from app.services.ai_ads.complete_creative import clamp_generation_counts

    assert clamp_generation_counts(40, 40) == (8, 4)
    assert clamp_generation_counts(3, 2) == (3, 2)
    assert clamp_generation_counts(-1, 0) == (0, 0)


def test_complete_image_prompt_includes_product_and_winners():
    from app.services.ai_ads.complete_creative import build_image_prompt
    from app.services.ai_ads.schemas import ProductContext

    prompt = build_image_prompt(
        product=ProductContext(product_id="1", title="Courage Bracelet", description="Gold plated"),
        visual_direction="Close-up on clasp",
        winning_notes="ugc close-up",
        aspect_ratio="4:5",
    )
    assert "Courage Bracelet" in prompt
    assert "ugc close-up" in prompt
    assert "4:5" in prompt


def test_video_spec_built_without_openai():
    from app.services.ai_ads.complete_creative import video_spec_from_concept
    from app.services.ai_ads.schemas import CreativeConceptModel, ProductContext

    spec = video_spec_from_concept(
        CreativeConceptModel(concept_name="UGC", hook="Feel the courage", headline="Courage Bracelet"),
        ProductContext(product_id="1", title="Courage Bracelet"),
    )
    assert spec.scenes
    assert spec.hook == "Feel the courage"
    assert spec.duration >= 10


def test_heuristic_score_rewards_complete_media():
    from app.services.ai_ads.complete_creative import heuristic_score

    ready = heuristic_score(
        has_media=True,
        hook="Feel the courage",
        headline="Courage Bracelet",
        primary_text="Everyday gold plated bracelet.",
        visual="Close-up product hero",
        winning_notes="close-up ugc",
        portfolio_bucket="winner_variation",
        product_title="Courage Bracelet",
    )
    empty = heuristic_score(
        has_media=False,
        hook="",
        headline="",
        primary_text="",
        visual="",
        winning_notes="",
        portfolio_bucket="experimental",
        product_title="Courage Bracelet",
    )
    assert ready.total > empty.total
    assert ready.breakdown.visual_clarity > empty.breakdown.visual_clarity
