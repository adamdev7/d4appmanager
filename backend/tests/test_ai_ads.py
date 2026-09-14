import json
from pathlib import Path
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


def test_owned_asset_hides_other_account_creatives():
    service = AIAdsService()
    owner = SimpleNamespace(id="user-1")
    other = SimpleNamespace(id="user-2")
    store = SimpleNamespace(id="store-1", owner_id="user-1")
    asset = SimpleNamespace(id="c1", store_id="store-1", user_id="user-2")
    db = MagicMock()
    db.get.side_effect = lambda model, key: store if key == "store-1" else asset
    with pytest.raises(HTTPException) as exc:
        service._owned_asset(db, owner, "store-1", "c1")
    assert exc.value.status_code == 404
    db.get.side_effect = lambda model, key: store if key == "store-1" else SimpleNamespace(
        id="c1", store_id="store-1", user_id="user-1"
    )
    assert service._owned_asset(db, owner, "store-1", "c1").user_id == "user-1"
    with pytest.raises(HTTPException):
        service._owned_asset(db, other, "store-1", "c1")


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


def test_asset_store_delete_only_own_folder(tmp_path, monkeypatch):
    from app.services.ai_ads import asset_store as store_mod

    monkeypatch.setattr(store_mod, "_UPLOADS", tmp_path)
    store = store_mod.CreativeAssetStore("store-1")
    saved = store.save_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 20, mime_type="image/png", prefix="gen")
    assert Path(saved["path"]).is_file()
    assert store.delete_local(saved["relative_path"]) is True
    assert not Path(saved["path"]).is_file()
    outsider = tmp_path.parent / "not-this.png"
    outsider.write_bytes(b"nope")
    assert store.delete_local(str(outsider)) is False
    assert outsider.is_file()


def test_image_provider_saves_bytes():
    import asyncio

    from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
    from app.services.ai_ads.schemas import ImageGenerationRequest

    png = b"\x89PNG\r\n\x1a\n" + b"x" * 20
    client = SimpleNamespace(generate_image_b64=AsyncMock(return_value=(png, "image/png")))
    store = MagicMock()
    store.save_bytes.return_value = {
        "relative_path": "ai-ads/s/gen.png",
        "public_url": "/uploads/ai-ads/s/gen.png",
    }
    provider = OpenAIImageProvider(client, store, model="gpt-image-2")
    result = asyncio.run(
        provider.generate(
            ImageGenerationRequest(prompt="product on marble", aspect_ratio="1:1"),
            identity_images=[(png, "image/png")],
        )
    )
    assert result.status == "completed"
    assert result.preview_url.endswith("gen.png")
    client.generate_image_b64.assert_awaited()
    kwargs = client.generate_image_b64.await_args.kwargs
    assert kwargs["references"]


def test_image_provider_failure_is_typed():
    import asyncio

    from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
    from app.services.ai_ads.schemas import ImageGenerationRequest

    client = SimpleNamespace(generate_image_b64=AsyncMock(side_effect=RuntimeError("boom")))
    provider = OpenAIImageProvider(client, MagicMock(), model="x")
    with pytest.raises(ImageGenerationError):
        asyncio.run(
            provider.generate(
                ImageGenerationRequest(prompt="x"),
                identity_images=[(b"\x89PNG\r\n\x1a\n" + b"x" * 20, "image/png")],
            )
        )


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
    from app.services.ai_ads.complete_creative import clamp_generation_counts, resolve_generation_counts

    assert clamp_generation_counts(40, 40) == (8, 4)
    assert clamp_generation_counts(3, 2) == (3, 2)
    assert clamp_generation_counts(-1, 0) == (0, 0)
    assert clamp_generation_counts(0, 2) == (0, 2)
    assert clamp_generation_counts(5, 0) == (5, 0)
    assert resolve_generation_counts(0, 0, default_images=3, default_videos=2) == (0, 0)
    assert resolve_generation_counts(None, 0, default_images=3, default_videos=2) == (3, 0)
    assert resolve_generation_counts(0, None, default_images=3, default_videos=2) == (0, 2)


def test_complete_image_prompt_includes_product_and_winners():
    from app.services.ai_ads.complete_creative import build_image_prompt
    from app.services.ai_ads.schemas import ProductContext

    prompt = build_image_prompt(
        product=ProductContext(product_id="1", title="Courage Bracelet", description="Gold plated"),
        visual_direction="Close-up on clasp",
        winning_notes="ugc close-up",
        aspect_ratio="4:5",
        variation_index=0,
        variation_count=5,
    )
    assert "Courage Bracelet" in prompt
    assert "ugc close-up" in prompt
    assert "4:5" in prompt
    assert "identity lock" in prompt.lower()
    assert "do not invent a different" in prompt.lower()
    assert "unique still 1 of 5" in prompt.lower()
    assert "assigned style" in prompt.lower()


def test_promotional_style_builds_offer_ad_not_catalog_retouch():
    from app.services.ai_ads.complete_creative import build_image_prompt
    from app.services.ai_ads.schemas import ProductContext

    prompt = build_image_prompt(
        product=ProductContext(product_id="1", title="Courage Bracelet", price=49.0, currency="USD"),
        visual_direction="",
        styles=["PROMOTIONAL"],
        variation_index=0,
        variation_count=1,
    )
    assert "PROMOTIONAL" in prompt
    assert "offer" in prompt.lower()
    assert "discount" in prompt.lower()
    assert "49" in prompt
    assert "catalog" in prompt.lower() or "listing" in prompt.lower()


def test_diversify_concepts_makes_five_distinct_image_prompts():
    from app.services.ai_ads.complete_creative import diversify_concepts, image_shot_recipe
    from app.services.ai_ads.schemas import CreativeConceptModel, ProductContext

    product = ProductContext(product_id="1", title="Courage Bracelet")
    clones = [
        CreativeConceptModel(
            concept_name=f"Clone {i}",
            type="IMAGE",
            visual_direction="Show the actual product clearly.",
            image_prompt="Photorealistic advertising photo of Courage Bracelet, product hero, clean background.",
        )
        for i in range(5)
    ]
    styles = ["PROMOTIONAL", "UGC", "LIFESTYLE"]
    out = diversify_concepts(clones, product, media_type="IMAGE", styles=styles)
    prompts = [c.image_prompt for c in out]
    assert len(prompts) == 5
    assert len(set(prompts)) == 5
    assert image_shot_recipe(0, styles) in prompts[0]
    assert image_shot_recipe(1, styles) in prompts[1]
    assert out[0].style == "PROMOTIONAL"
    assert out[1].style == "UGC"
    assert "ORIGINAL STILL 1 of 5" in prompts[0]
    assert "ORIGINAL STILL 5 of 5" in prompts[4]


def test_diversify_concepts_makes_distinct_video_storyboards():
    from app.services.ai_ads.complete_creative import diversify_concepts, video_story_recipe
    from app.services.ai_ads.schemas import CreativeConceptModel, ProductContext

    product = ProductContext(product_id="1", title="Courage Bracelet")
    clones = [
        CreativeConceptModel(concept_name=f"Vid {i}", type="VIDEO", visual_direction="Show the product.")
        for i in range(3)
    ]
    out = diversify_concepts(clones, product, media_type="VIDEO")
    visuals = [c.visual_direction for c in out]
    assert len(set(visuals)) == 3
    assert video_story_recipe(0).split(":")[0] in visuals[0] or "ORIGINAL VIDEO 1" in (out[0].scenes[0].visual if out[0].scenes else "")


def test_video_prompt_demands_original_storyboard():
    from app.services.ai_ads.complete_creative import build_video_prompt, video_spec_from_concept
    from app.services.ai_ads.schemas import CreativeConceptModel, ProductContext

    spec = video_spec_from_concept(
        CreativeConceptModel(concept_name="UGC", hook="Feel the courage", headline="Courage Bracelet"),
        ProductContext(product_id="1", title="Courage Bracelet"),
    )
    prompt = build_video_prompt(
        product=ProductContext(product_id="1", title="Courage Bracelet"),
        spec=spec,
        variation_index=1,
        variation_count=2,
    )
    assert "unique video 2 of 2" in prompt.lower()
    assert "do not recreate" in prompt.lower()


def test_generate_image_b64_uses_product_photos_as_identity():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient

    client = AdsOpenAIClient("sk-test", store_id="s")
    with patch.object(client, "_image_edits", new=AsyncMock(return_value=(b"e", "image/png"))) as edits:
        with patch.object(client, "_image_generations", new=AsyncMock()) as gen:
            out = asyncio.run(
                client.generate_image_b64(
                    prompt="new ad with exact product",
                    model="gpt-image-2",
                    references=[(b"abc", "image/jpeg")],
                )
            )
    assert out == (b"e", "image/png")
    edits.assert_awaited()
    gen.assert_not_awaited()


def test_generate_image_b64_skips_edits_without_references():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient

    client = AdsOpenAIClient("sk-test", store_id="s")
    with patch.object(client, "_image_edits", new=AsyncMock()) as edits:
        with patch.object(client, "_image_generations", new=AsyncMock(return_value=(b"x", "image/png"))) as gen:
            out = asyncio.run(
                client.generate_image_b64(
                    prompt="new ad",
                    model="gpt-image-2",
                )
            )
    assert out == (b"x", "image/png")
    edits.assert_not_awaited()
    gen.assert_awaited()


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


def test_generation_service_can_enqueue_jobs():
    from app.services.ai_ads import service as ai_ads_service

    assert callable(ai_ads_service.enqueue_generation_job)


def test_append_job_progress_builds_log():
    from app.services.ai_ads.job_progress import append_job_progress, parse_job_log

    job = SimpleNamespace(progress_step="", progress_message="", progress_pct=0, progress_log_json="[]")
    append_job_progress(job, step="plan", title="Writing ads", detail="Drafting hooks and scenes", pct=42)
    append_job_progress(
        job, step="image", title="Generating image 1 of 2", detail="Rendering the hero still", pct=70
    )
    log = parse_job_log(job)
    assert job.progress_step == "image"
    assert job.progress_message == "Generating image 1 of 2"
    assert job.progress_pct == 70
    assert len(log) == 2
    assert "hero still" in log[-1]["detail"]


def test_image_size_maps_for_gpt_image_and_dalle():
    from app.services.ai_ads.providers.openai_image import resolve_image_size

    assert resolve_image_size("gpt-image-2", "4:5")[0] == "1024x1536"
    assert resolve_image_size("gpt-image-2", "16:9")[0] == "1536x1024"
    assert resolve_image_size("dall-e-3", "9:16")[0] == "1024x1792"


def test_store_destination_url_uses_shop_domain():
    from app.services.ai_ads.service import _store_destination_url

    assert _store_destination_url(SimpleNamespace(shop_domain="luxory.myshopify.com")) == "https://luxory.myshopify.com"
    assert _store_destination_url(SimpleNamespace(shop_domain="https://luxory.online/")) == "https://luxory.online"


def test_generation_request_model_has_unique_fields():
    from app.models.ai_ads import AIAdsGenerationJobRequest, AIAdsSettingsUpdate

    assert list(AIAdsGenerationJobRequest.model_fields).count("styles") == 1
    assert list(AIAdsSettingsUpdate.model_fields).count("brand_style") == 1
    zero = AIAdsGenerationJobRequest(product_id="1", image_count=0, video_count=0)
    assert zero.image_count == 0
    assert zero.video_count == 0


def test_preview_url_normalizes_local_paths():
    from app.services.ai_ads.service import _preview

    assert _preview("ai-ads/s/gen.png") == "/uploads/ai-ads/s/gen.png"
    assert _preview("/uploads/ai-ads/s/gen.png") == "/uploads/ai-ads/s/gen.png"
    assert _preview(None, "https://cdn.example/p.jpg") == "https://cdn.example/p.jpg"


def test_compact_meta_item_includes_offer_look():
    from app.services.ai_ads.complete_creative import compact_meta_item, winning_style_notes

    item = compact_meta_item(
        {
            "id": "c1",
            "ad_name": "Wrist lifestyle",
            "copy": {"headline": "Feel the courage", "primary_text": "Everyday wear"},
            "dna": {
                "visual": {
                    "offer_look": "lifestyle wrist close-up",
                    "product_depicted": "black leather wrap with silver clasp",
                    "setting": "window light indoor",
                    "visual_hook": "hand at chin",
                },
                "copy": {"hook_type": "identity"},
            },
            "performance": {"roas": 2.1, "ctr": 1.4},
        }
    )
    assert item["offer_look"] == "lifestyle wrist close-up"
    assert "silver clasp" in item["product_in_ad"]
    notes = winning_style_notes([item])
    assert "lifestyle wrist close-up" in notes
    motion = winning_style_notes([item], sku_safe=True)
    assert "silver clasp" not in motion
    assert "window light indoor" in motion


def test_appearance_lock_formats_vision_output():
    from app.services.ai_ads.complete_creative import format_appearance_lock
    from app.services.ai_ads.schemas import ProductAppearanceLock

    lock = ProductAppearanceLock(
        summary="Black leather wrap bracelet",
        materials="leather",
        colors="black with silver hardware",
        hardware="brushed silver magnetic clasp",
        construction="double wrap",
        distinguishing_details="contrast stitching",
    )
    text = format_appearance_lock(lock)
    assert "leather" in text
    assert "magnetic clasp" in text


def test_product_reference_urls_uses_catalog_photos():
    from app.services.ai_ads.complete_creative import product_reference_urls
    from app.services.ai_ads.schemas import ProductContext, ProductImage

    product = ProductContext(
        product_id="1",
        title="Courage Bracelet",
        images=[
            ProductImage(src="https://cdn.example/p.jpg"),
            ProductImage(src="https://cdn.example/p2.jpg"),
            ProductImage(src="https://cdn.example/p3.jpg"),
            ProductImage(src="https://cdn.example/p4.jpg"),
        ],
    )
    assert product_reference_urls(product) == [
        "https://cdn.example/p.jpg",
        "https://cdn.example/p2.jpg",
        "https://cdn.example/p3.jpg",
    ]
    product.brand_context = {"identity_data_urls": ["data:image/jpeg;base64,abc"]}
    assert product_reference_urls(product) == ["data:image/jpeg;base64,abc"]


def test_job_card_exposes_progress_fields():
    from app.db.models import CreativeGenerationJob
    from app.services.ai_ads.service import _job_card

    job = CreativeGenerationJob(
        store_id="s", user_id="u", status="RUNNING", total_items=2, completed_items=0
    )
    job.progress_step = "image"
    job.progress_pct = 70
    job.progress_message = "Generating image 1 of 2"
    job.progress_log_json = json.dumps(
        [
            {
                "at": "2026-09-13T12:00:00+00:00",
                "step": "image",
                "title": "Generating image 1 of 2",
                "detail": "Rendering",
                "pct": 70,
            }
        ]
    )
    card = _job_card(job)
    assert card["progress_pct"] == 70
    assert card["progress_step"] == "image"
    assert card["thinking"] == "Rendering"
    assert card["progress_log"][0]["title"].startswith("Generating")
    assert "worker_alive" in card
    job.request_json = json.dumps({"image_count": 3, "video_count": 1, "placement": "feed"})
    card = _job_card(job)
    assert card["image_count"] == 3
    assert card["video_count"] == 1
    assert card["placement"] == "feed"


def _console_job(**kwargs):
    from app.db.models import CreativeGenerationJob

    job = CreativeGenerationJob(
        store_id=kwargs.pop("store_id", "s1"),
        user_id=kwargs.pop("user_id", "u1"),
        status=kwargs.pop("status", "RUNNING"),
        product_id=kwargs.pop("product_id", "11"),
        request_json=kwargs.pop(
            "request_json", json.dumps({"product_id": "11", "image_count": 1, "video_count": 1})
        ),
        total_items=kwargs.pop("total_items", 2),
        completed_items=kwargs.pop("completed_items", 0),
    )
    job.progress_pct = kwargs.pop("progress_pct", 42)
    for key, value in kwargs.items():
        setattr(job, key, value)
    return job


def test_cancel_flag_roundtrip():
    from app.services.ai_ads.job_runner import clear_cancel, is_cancel_requested, request_cancel

    request_cancel("job-x")
    assert is_cancel_requested("job-x") is True
    clear_cancel("job-x")
    assert is_cancel_requested("job-x") is False


def test_stop_generation_job_marks_cancelled():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job()
    db = MagicMock()
    user = SimpleNamespace(id="u1")
    with (
        patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")),
        patch("app.services.ai_ads.service.request_cancel") as cancel,
    ):
        db.get.return_value = job
        card = svc.stop_generation_job(db, user, "s1", job.id)
    cancel.assert_called_once_with(job.id)
    assert job.status == "CANCELLED"
    assert card["status"] == "CANCELLED"
    assert "Stopped" in (job.error_message or "")


def test_stop_generation_job_is_idempotent_when_already_halted():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job(status="CANCELLED", error_message="already")
    db = MagicMock()
    with (
        patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")),
        patch("app.services.ai_ads.service.request_cancel"),
    ):
        db.get.return_value = job
        card = svc.stop_generation_job(db, SimpleNamespace(id="u1"), "s1", job.id)
    assert job.status == "CANCELLED"
    assert card["status"] == "CANCELLED"


def test_restart_generation_job_clones_brief():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job(status="CANCELLED")
    db = MagicMock()
    with (
        patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")),
        patch.object(svc, "create_generation_job", return_value={"id": "new-job", "status": "QUEUED"}) as create,
        patch.object(svc, "stop_generation_job"),
    ):
        db.get.return_value = job
        card = svc.restart_generation_job(db, SimpleNamespace(id="u1"), "s1", job.id)
    create.assert_called_once()
    body = create.call_args.args[3]
    assert body["product_id"] == "11"
    assert card["id"] == "new-job"


def test_nudge_generation_job_reenqueues_dead_worker():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job(status="RUNNING")
    db = MagicMock()
    with (
        patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")),
        patch("app.services.ai_ads.service.is_job_running", return_value=False),
        patch("app.services.ai_ads.service.enqueue_generation_job") as enqueue,
        patch("app.services.ai_ads.service.resolve_openai_api_key", return_value="sk-test"),
    ):
        db.get.return_value = job
        card = svc.nudge_generation_job(db, SimpleNamespace(id="u1"), "s1", job.id)
    assert job.status == "QUEUED"
    enqueue.assert_called_once()
    assert card["nudge"] == "enqueued"


def test_nudge_generation_job_rejects_cancelled():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job(status="CANCELLED")
    db = MagicMock()
    with patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")):
        db.get.return_value = job
        with pytest.raises(HTTPException) as exc:
            svc.nudge_generation_job(db, SimpleNamespace(id="u1"), "s1", job.id)
    assert exc.value.status_code == 400


def test_kick_if_stuck_skips_cancelled():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = SimpleNamespace(id="j1", status="CANCELLED")
    with patch("app.services.ai_ads.service.enqueue_generation_job") as enqueue:
        svc._kick_if_stuck(MagicMock(), SimpleNamespace(id="u1"), job)
    enqueue.assert_not_called()


def test_sweep_generation_job_deletes_leftovers_only():
    from app.services.ai_ads.service import AIAdsService

    svc = AIAdsService()
    job = _console_job()
    leftover = SimpleNamespace(id="asset-fail", status="FAILED")
    db = MagicMock()
    db.scalars.return_value.all.return_value = [leftover]
    with (
        patch.object(svc, "ensure_store", return_value=SimpleNamespace(id="s1", owner_id="u1")),
        patch.object(svc, "delete_creative", return_value={"ok": True, "deleted_id": leftover.id}) as delete,
        patch.object(svc, "get_job", return_value={"id": job.id, "creatives": []}),
    ):
        db.get.return_value = job
        card = svc.sweep_generation_job(db, SimpleNamespace(id="u1"), "s1", job.id)
    delete.assert_called_once()
    assert card["swept_count"] == 1


def test_generation_cancelled_is_not_retryable():
    from app.services.ai_ads.exceptions import GenerationCancelled

    err = GenerationCancelled()
    assert err.retryable is False
    assert err.code == "CANCELLED"


def test_video_size_and_seconds_for_meta_reels():
    from app.services.ai_ads.providers.openai_video import clamp_video_seconds, resolve_video_size

    assert resolve_video_size("9:16")[0] == "720x1280"
    assert resolve_video_size("16:9")[0] == "1280x720"
    assert clamp_video_seconds(15) == "12"
    assert clamp_video_seconds(8) == "8"


def test_build_video_prompt_is_product_faithful():
    from app.services.ai_ads.complete_creative import build_video_prompt, video_spec_from_concept
    from app.services.ai_ads.schemas import CreativeConceptModel, ProductContext

    product = ProductContext(product_id="1", title="Courage Bracelet")
    spec = video_spec_from_concept(
        CreativeConceptModel(concept_name="UGC", hook="Feel the courage", headline="Courage Bracelet"),
        product,
    )
    prompt = build_video_prompt(product=product, spec=spec)
    assert "Courage Bracelet" in prompt
    assert "first frame" in prompt.lower()
    assert "do not replace" in prompt.lower()
    assert "identity only" not in prompt.lower()


def test_image_provider_refuses_to_invent_without_product_photos():
    import asyncio

    from app.services.ai_ads.providers.openai_image import OpenAIImageProvider
    from app.services.ai_ads.schemas import ImageGenerationRequest

    client = SimpleNamespace(generate_image_b64=AsyncMock())
    provider = OpenAIImageProvider(client, MagicMock(), model="gpt-image-2")
    with pytest.raises(ImageGenerationError, match="product photos"):
        asyncio.run(provider.generate(ImageGenerationRequest(prompt="fake bracelet")))
    client.generate_image_b64.assert_not_called()


def test_is_mp4_detects_ftyp():
    from app.services.ai_ads.media_io import is_mp4

    assert is_mp4(b"\x00\x00\x00\x18ftypisom" + b"x" * 20)
    assert not is_mp4(b"not a video")
    assert not is_mp4(b"")


def test_fit_image_bytes_matches_requested_size():
    from io import BytesIO

    from PIL import Image

    from app.services.ai_ads.media_io import fit_image_bytes, fit_references

    img = Image.new("RGB", (1200, 400), (200, 40, 40))
    src = BytesIO()
    img.save(src, format="JPEG")
    out, mime = fit_image_bytes(src.getvalue(), 1024, 1536, fmt="PNG")
    assert mime == "image/png"
    fitted = Image.open(BytesIO(out))
    assert fitted.size == (1024, 1536)

    video, video_mime = fit_image_bytes(src.getvalue(), 720, 1280, mode="contain")
    assert video_mime == "image/jpeg"
    letterboxed = Image.open(BytesIO(video))
    assert letterboxed.size == (720, 1280)

    refs = fit_references([(src.getvalue(), "image/jpeg")], "1024x1536", fmt="PNG")
    assert len(refs) == 1
    assert Image.open(BytesIO(refs[0][0])).size == (1024, 1536)

    skipped = fit_references([(b"not-an-image", "image/jpeg")], "720x1280")
    assert skipped == []

    from app.services.ai_ads.media_io import prefer_jpeg_url, prepare_video_still, shopify_still_candidates

    shopify = prefer_jpeg_url("https://cdn.shopify.com/s/files/1/x/courage.png?v=9")
    assert "format=pjpg" in shopify
    assert "width=" not in shopify
    variants = shopify_still_candidates("//cdn.shopify.com/s/files/1/x/courage.png?v=9")
    assert variants[0].startswith("https://")
    assert "format=pjpg" in variants[0]
    shop_variants = shopify_still_candidates(
        "https://cdn.shopify.com/s/files/1/x/courage.png?v=9",
        shop_domain="luxory.myshopify.com",
    )
    assert any("/cdn/shop/files/courage.png" in item for item in shop_variants)
    assert not any("/cdn/shop/products/" in item for item in shop_variants)
    assert len(shop_variants) <= 5
    transformed = shopify_still_candidates(
        "https://cdn.shopify.com/s/files/1/x/ChatGPTImage4oct.2025_15_40_38_1400x.png.jpg?v=9",
        shop_domain="luxory.myshopify.com",
    )
    assert any("ChatGPTImage4oct.2025_15_40_38.png" in item and "_1400x" not in item for item in transformed)
    assert "format=pjpg" in transformed[0]

    from app.services.ai_ads.media_io import archive_image_bytes, bytes_to_data_url

    archived, archived_mime = archive_image_bytes(src.getvalue(), max_side=200)
    assert archived_mime == "image/jpeg"
    assert Image.open(BytesIO(archived)).size[0] <= 200
    data_url = bytes_to_data_url(src.getvalue(), max_side=120)
    assert data_url.startswith("data:image/jpeg;base64,")
    still, still_mime = prepare_video_still([(src.getvalue(), "image/jpeg")], 720, 1280)
    assert still_mime == "image/jpeg"
    assert Image.open(BytesIO(still)).size == (720, 1280)

    rgba = Image.new("RGBA", (640, 480), (12, 80, 40, 255))
    png = BytesIO()
    rgba.save(png, format="PNG")
    prepared, _ = prepare_video_still([(png.getvalue(), "image/png")], 720, 1280)
    assert Image.open(BytesIO(prepared)).size == (720, 1280)


def test_archive_converts_png_and_webp_to_compressed_jpeg():
    from io import BytesIO

    from PIL import Image

    from app.services.ai_ads.media_io import archive_image_bytes

    rgba = Image.new("RGBA", (1800, 1200), (200, 40, 80, 180))
    png = BytesIO()
    rgba.save(png, format="PNG")
    archived, mime = archive_image_bytes(png.getvalue(), max_side=1400)
    assert mime == "image/jpeg"
    out = Image.open(BytesIO(archived))
    assert out.format == "JPEG"
    assert out.mode == "RGB"
    assert max(out.size) <= 1400
    assert archived[:3] == b"\xff\xd8\xff"
    assert len(archived) < len(png.getvalue()) or len(png.getvalue()) < 50_000

    palette = rgba.convert("P", palette=Image.Palette.ADAPTIVE, colors=32)
    pal = BytesIO()
    palette.save(pal, format="PNG")
    pal_archived, pal_mime = archive_image_bytes(pal.getvalue())
    assert pal_mime == "image/jpeg"
    assert Image.open(BytesIO(pal_archived)).mode == "RGB"

    webp = BytesIO()
    Image.new("RGB", (400, 300), (9, 90, 40)).save(webp, format="WEBP")
    webp_archived, webp_mime = archive_image_bytes(webp.getvalue())
    assert webp_mime == "image/jpeg"
    assert Image.open(BytesIO(webp_archived)).size == (400, 300)


def test_video_provider_rejects_non_mp4_download():
    import asyncio

    from app.services.ai_ads.exceptions import VideoProviderError
    from app.services.ai_ads.providers.openai_video import OpenAIVideoProvider

    client = SimpleNamespace(
        create_video=AsyncMock(return_value={"id": "video_1", "status": "queued"}),
        get_video=AsyncMock(return_value={"id": "video_1", "status": "completed"}),
        download_video_bytes=AsyncMock(return_value=b'{"status":"ok"}'),
    )
    provider = OpenAIVideoProvider(client, MagicMock(), model="sora-2")
    spec = {
        "prompt": "product hero",
        "format": "9:16",
        "duration": 8,
        "input_reference": (b"sku-bytes", "image/jpeg"),
    }
    with pytest.raises(VideoProviderError, match="playable MP4"):
        asyncio.run(provider.generate_video(spec))


def test_create_video_sends_multipart_even_without_reference():
    import asyncio

    from app.services.ai_ads.openai_client import AdsOpenAIClient

    captured: dict = {}

    class FakeResp:
        status_code = 200
        text = '{"id":"v1","status":"queued"}'
        content = b'{"id":"v1","status":"queued"}'

        def json(self):
            return {"id": "v1", "status": "queued"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, data=None, files=None, json=None):
            captured["url"] = url
            captured["data"] = data
            captured["files"] = files
            captured["json"] = json
            return FakeResp()

    with patch("app.services.ai_ads.openai_client.httpx.AsyncClient", FakeClient):
        client = AdsOpenAIClient("sk-test", store_id="s")
        out = asyncio.run(client.create_video(prompt="Courage Bracelet on a wrist", model="sora-2"))
    assert out["id"] == "v1"
    assert captured["data"] is None
    assert captured["json"] is None
    assert captured["files"]
    fields = {name: value for name, value in captured["files"]}
    assert fields["model"] == (None, "sora-2")
    assert fields["size"] == (None, "720x1280")

    from io import BytesIO

    from PIL import Image

    img = Image.new("RGB", (400, 400), (180, 40, 40))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    captured.clear()
    with patch("app.services.ai_ads.openai_client.httpx.AsyncClient", FakeClient):
        out = asyncio.run(
            client.create_video(
                prompt="Keep this Courage Bracelet on screen",
                model="sora-2",
                input_reference=(buf.getvalue(), "image/jpeg"),
            )
        )
    assert out["id"] == "v1"
    names = [name for name, _ in captured["files"]]
    assert "input_reference" in names


def test_video_provider_requires_product_photo():
    import asyncio

    from app.services.ai_ads.exceptions import VideoProviderError
    from app.services.ai_ads.providers.openai_video import OpenAIVideoProvider

    provider = OpenAIVideoProvider(SimpleNamespace(), MagicMock(), model="sora-2")
    with pytest.raises(VideoProviderError, match="product photo"):
        asyncio.run(provider.generate_video({"prompt": "product hero", "format": "9:16", "duration": 8}))


def test_openai_video_provider_saves_mp4():
    import asyncio

    from app.services.ai_ads.providers.openai_video import OpenAIVideoProvider

    client = SimpleNamespace(
        create_video=AsyncMock(return_value={"id": "video_1", "status": "queued"}),
        get_video=AsyncMock(return_value={"id": "video_1", "status": "completed"}),
        download_video_bytes=AsyncMock(return_value=b"\x00\x00\x00\x18ftypisom" + b"x" * 40),
    )
    store = MagicMock()
    store.save_bytes.return_value = {
        "relative_path": "ai-ads/s/vid.mp4",
        "public_url": "/uploads/ai-ads/s/vid.mp4",
    }
    provider = OpenAIVideoProvider(client, store, model="sora-2")
    result = asyncio.run(
        provider.generate_video(
            {
                "prompt": "product hero",
                "format": "9:16",
                "duration": 8,
                "input_reference": (b"sku-bytes", "image/jpeg"),
            }
        )
    )
    assert result["status"] == "completed"
    assert result["local_path"].endswith(".mp4")
    client.create_video.assert_awaited()
    store.save_bytes.assert_called_once()


def test_publisher_story_uses_uploaded_image_hash():
    from app.services.ai_ads.publisher import MetaCreativePublisher

    publisher = MetaCreativePublisher(MagicMock(), "store-1")
    asset = SimpleNamespace(headline="Glow", hook="Glow now", primary_text="Shop the serum", cta="SHOP_NOW")
    story = publisher._story_spec(
        asset,
        page="page1",
        link="https://shop.example",
        media={"image_hash": "abc123"},
    )
    assert story["link_data"]["image_hash"] == "abc123"
    assert story["link_data"]["link"] == "https://shop.example"


def test_asset_card_exposes_rendered_video_url():
    from app.db.models import CreativeAsset
    from app.services.ai_ads.service import _asset_card

    asset = CreativeAsset(store_id="s", user_id="u", type="VIDEO", status="READY")
    asset.local_path = "ai-ads/s/vid.mp4"
    asset.preview_url = "ai-ads/s/poster.png"
    card = _asset_card(asset)
    assert card["video_url"] == "/uploads/ai-ads/s/vid.mp4"
    assert card["preview_url"] == "/uploads/ai-ads/s/poster.png"
    assert card["has_rendered_media"] is True


def test_catalog_fingerprint_changes_when_photos_change():
    from app.services.ai_ads.product_catalog import image_fingerprint, image_key, images_needing_download

    first = [{"id": 11, "src": "https://cdn.shopify.com/p.jpg?v=1", "updated_at": "2026-01-01"}]
    second = [{"id": 11, "src": "https://cdn.shopify.com/p.jpg?v=2", "updated_at": "2026-01-02"}]
    added = first + [{"id": 12, "src": "https://cdn.shopify.com/p2.jpg?v=1"}]
    assert image_fingerprint(first) != image_fingerprint(second)
    assert image_fingerprint(first) != image_fingerprint(added)
    assert image_key(first[0]) == "11"

    wanted = [("11", "https://cdn.shopify.com/p.jpg?v=2"), ("12", "https://cdn.shopify.com/p2.jpg?v=1")]
    cached = {"11": ("https://cdn.shopify.com/p.jpg?v=1", True)}
    assert images_needing_download(wanted, cached) == ["11", "12"]
    unchanged = {"11": ("https://cdn.shopify.com/p.jpg?v=2", True), "12": ("https://cdn.shopify.com/p2.jpg?v=1", True)}
    assert images_needing_download(wanted, unchanged) == []
    missing_file = {"11": ("https://cdn.shopify.com/p.jpg?v=2", False)}
    assert "11" in images_needing_download(wanted[:1], missing_file)


def test_catalog_ensure_skips_unchanged_photos(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace

    from PIL import Image

    from app.services.ai_ads.asset_store import CreativeAssetStore
    from app.services.ai_ads.product_catalog import ShopifyProductCatalog

    jpeg = tmp_path / "seed.jpg"
    Image.new("RGB", (80, 80), (12, 80, 40)).save(jpeg, format="JPEG")
    raw_bytes = jpeg.read_bytes()

    fetches: list[str] = []

    async def fake_fetch(url, **kwargs):
        fetches.append(url)
        return raw_bytes, "image/jpeg"

    monkeypatch.setattr("app.services.ai_ads.product_catalog.fetch_image_bytes", fake_fetch)

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeDB:
        def __init__(self):
            self.products = {}
            self.images = {}
            self.added = []

        def scalar(self, query):
            return None

        def scalars(self, query):
            return FakeQuery(list(self.images.values()))

        def add(self, row):
            self.added.append(row)
            image_key = getattr(row, "image_key", None)
            if image_key:
                self.images[image_key] = row
            pid = getattr(row, "shopify_product_id", None)
            if pid and hasattr(row, "image_fingerprint"):
                self.products[pid] = row

        def flush(self):
            return None

        def commit(self):
            return None

        def delete(self, row):
            key = getattr(row, "image_key", None)
            if key:
                self.images.pop(key, None)

    store = SimpleNamespace(id="store-1", shop_domain="d4.myshopify.com", currency="USD", name="D4")
    assets = CreativeAssetStore("store-1")
    assets.dir = tmp_path / "uploads"
    assets.dir.mkdir(parents=True, exist_ok=True)
    catalog = ShopifyProductCatalog(FakeDB(), store, assets)

    original_get = catalog.get_product_row
    original_listed = catalog.listed_images

    def get_row(product_id):
        return catalog.db.products.get(str(product_id))

    def listed(product_id):
        return [img for img in catalog.db.images.values() if img.shopify_product_id == str(product_id)]

    catalog.get_product_row = get_row
    catalog.listed_images = listed

    product = {
        "id": 99,
        "title": "Courage",
        "handle": "courage",
        "images": [{"id": 11, "src": "https://cdn.shopify.com/p.jpg?v=1", "position": 1, "width": 800, "height": 800}],
    }
    first = asyncio.run(catalog.ensure_product_images(product))
    assert len(first) == 1
    assert len(fetches) == 1
    second = asyncio.run(catalog.ensure_product_images(product))
    assert len(second) == 1
    assert len(fetches) == 1
    product["images"][0]["src"] = "https://cdn.shopify.com/p.jpg?v=2"
    third = asyncio.run(catalog.ensure_product_images(product))
    assert len(third) == 1
    assert len(fetches) == 2
    _ = original_get, original_listed


def test_catalog_stores_manual_photos_once(tmp_path):
    from types import SimpleNamespace

    from PIL import Image

    from app.services.ai_ads.asset_store import CreativeAssetStore
    from app.services.ai_ads.product_catalog import ShopifyProductCatalog

    jpeg = tmp_path / "ring.jpg"
    Image.new("RGB", (80, 80), (200, 40, 80)).save(jpeg, format="JPEG")
    raw_bytes = jpeg.read_bytes()

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeDB:
        def __init__(self):
            self.products = {}
            self.images = {}

        def scalar(self, query):
            return None

        def scalars(self, query):
            return FakeQuery(list(self.images.values()))

        def add(self, row):
            image_key = getattr(row, "image_key", None)
            if image_key:
                self.images[image_key] = row
            pid = getattr(row, "shopify_product_id", None)
            if pid and hasattr(row, "image_fingerprint"):
                self.products[pid] = row

        def flush(self):
            return None

        def commit(self):
            return None

        def delete(self, row):
            key = getattr(row, "image_key", None)
            if key:
                self.images.pop(key, None)

    store = SimpleNamespace(id="store-1", shop_domain="d4.myshopify.com", currency="USD", name="D4")
    assets = CreativeAssetStore("store-1")
    assets.dir = tmp_path / "uploads"
    assets.dir.mkdir(parents=True, exist_ok=True)
    catalog = ShopifyProductCatalog(FakeDB(), store, assets)
    catalog.get_product_row = lambda product_id: catalog.db.products.get(str(product_id))
    catalog.listed_images = lambda product_id: [
        img for img in catalog.db.images.values() if img.shopify_product_id == str(product_id)
    ]

    def picker(pid):
        imgs = catalog.listed_images(pid)
        photos = [catalog.assets.public_url(img.local_path) for img in imgs if img.local_path]
        return {
            "id": str(pid),
            "title": "",
            "price": None,
            "currency": None,
            "image": photos[0] if photos else None,
            "photos": photos,
            "product_url": None,
            "photos_cached": bool(photos),
        }

    catalog.product_picker_card = picker

    card = catalog.store_manual_photos("9864947138808", [raw_bytes])
    assert card["photos_cached"] is True
    assert len(card["photos"]) == 1
    assert catalog.cached_identity_bytes("9864947138808", limit=1)
    assert any(str(key).startswith("manual_") for key in catalog.db.images)

    png_path = tmp_path / "ring.png"
    Image.new("RGBA", (120, 80), (10, 20, 30, 200)).save(png_path, format="PNG")
    png_card = catalog.store_manual_photos("9864947138808", [png_path.read_bytes()])
    assert len(png_card["photos"]) == 2
    stored = catalog.cached_identity_bytes("9864947138808", limit=2)
    assert all(mime == "image/jpeg" for _raw, mime in stored)

    again = catalog.store_manual_photos("9864947138808", [raw_bytes])
    assert len(again["photos"]) == 2
    try:
        catalog.store_manual_photos("nope", [b"not-an-image"])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_upload_limits_raise_starlette_part_size():
    import inspect

    from starlette.formparsers import MultiPartParser
    from starlette.requests import Request

    from app.core.upload_limits import MAX_UPLOAD_PART_BYTES, install

    install()
    assert MultiPartParser.max_part_size == MAX_UPLOAD_PART_BYTES
    default = inspect.signature(Request.form).parameters["max_part_size"].default
    assert default == MAX_UPLOAD_PART_BYTES


def test_catalog_adopts_orphan_disk_photos(tmp_path):
    from types import SimpleNamespace

    from PIL import Image

    from app.services.ai_ads.asset_store import CreativeAssetStore
    from app.services.ai_ads.product_catalog import ShopifyProductCatalog

    class FakeQuery:
        def __init__(self, rows):
            self._rows = rows

        def where(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self._rows

    class FakeDB:
        def __init__(self):
            self.products = {}
            self.images = {}

        def scalar(self, query):
            return None

        def scalars(self, query):
            return FakeQuery(list(self.images.values()))

        def add(self, row):
            image_key = getattr(row, "image_key", None)
            if image_key:
                self.images[image_key] = row
            pid = getattr(row, "shopify_product_id", None)
            if pid and hasattr(row, "image_fingerprint"):
                self.products[pid] = row

        def flush(self):
            return None

        def commit(self):
            return None

        def delete(self, row):
            key = getattr(row, "image_key", None)
            if key:
                self.images.pop(key, None)

    store = SimpleNamespace(id="store-1", shop_domain="d4.myshopify.com", currency="USD", name="D4")
    assets = CreativeAssetStore("store-1")
    assets.dir = tmp_path / "uploads"
    assets.dir.mkdir(parents=True, exist_ok=True)
    orphan = assets.dir / "sku_99_orphanhash.jpg"
    Image.new("RGB", (40, 40), (12, 80, 40)).save(orphan, format="JPEG")
    catalog = ShopifyProductCatalog(FakeDB(), store, assets)
    catalog.db.products["99"] = SimpleNamespace(shopify_product_id="99", title="Ring")
    catalog.get_product_row = lambda product_id: catalog.db.products.get(str(product_id))
    catalog.listed_images = lambda product_id: [
        img for img in catalog.db.images.values() if img.shopify_product_id == str(product_id)
    ]
    assert catalog.adopt_orphan_disk_photos() == 1
    assert catalog.listed_images("99")
