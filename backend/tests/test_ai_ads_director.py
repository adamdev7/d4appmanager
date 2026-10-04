"""Creative Director: calendar, costs, guardrails, novelty, board/brief selection, fatigue, pipeline, actions."""

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AIAdsPlaybookEntry,
    AIDirectorReport,
    AIDirectorSettings,
    AIDirectorSuggestion,
    ShopifyCatalogProduct,
    Store,
    StoreAIAdsSettings,
    StoreStatus,
    User,
)
from app.db.session import Base
from app.services.ai_ads import ad_types
from app.services.ai_ads.complete_creative import STYLE_PLAYBOOKS
from app.services.ai_ads.director import calendar, context as ctx, costs, engine, memory, service
from app.services.ai_ads.director.schemas import (
    BriefPick,
    ChallengeResult,
    ConceptReview,
    CritiqueResult,
    DirectorConcept,
    IdeationResult,
    WeeklyBrief,
)


def _product(pid="1", **overrides):
    base = {
        "id": pid,
        "title": f"Necklace {pid}",
        "stock": "in_stock",
        "inventory": 20,
        "excluded": False,
        "below_margin_floor": False,
        "margin_pct": 70,
        "has_photos": True,
        "units_90d": 5,
    }
    base.update(overrides)
    return base


def _context(*products, never_do=None, offers=None):
    return {
        "products": list(products) or [_product()],
        "brand": {"never_do": never_do or []},
        "confirmed_offers": offers or [],
        "meta": {},
        "calendar": {"upcoming": []},
    }


def _concept(**overrides):
    base = {
        "concept_name": "Morning light gift",
        "ad_type": "LIFESTYLE",
        "product_id": "1",
        "image_count": 1,
        "video_count": 0,
        "hook": "Her name, in gold, every morning",
        "angle": "personal meaning",
        "test_variable": "angle",
    }
    base.update(overrides)
    return base


# ------------------------------------------------------------------ registry, calendar, costs


def test_ideation_fills_missing_concept_name():
    result = IdeationResult.model_validate(
        {
            "concepts": [
                {
                    "ad_type": "UGC",
                    "product_id": "1",
                    "hook": "She films the unboxing at the kitchen table",
                    "offer_ideas": [],
                },
                {"ad_type": "PRODUCT_DEMO", "name": "Clasp close-up", "hook": "Watch the clasp"},
                {"ad_type": "LIFESTYLE", "concept_name": "  Morning light  ", "hook": "Gold on the dresser"},
            ],
            "audience_ideas": [],
            "offer_ideas": [],
        }
    )
    assert result.concepts[0].concept_name == "She films the unboxing at the kitchen table"
    assert result.concepts[1].concept_name == "Clasp close-up"
    assert result.concepts[2].concept_name == "Morning light"


def test_ideation_accepts_audience_type_and_input_value():
    result = IdeationResult.model_validate(
        {
            "concepts": [],
            "audience_ideas": [
                {"type": "Interest", "input_value": "Jewelry lovers"},
                {"type": "Lookalike", "input_value": "Engaged shoppers"},
                {"type": "Retargeting", "input_value": "Website visitors"},
                {"type": "Broad", "input_value": "All jewelry buyers"},
            ],
            "offer_ideas": [{"name": "Free shipping over 75", "id": "offer-1"}],
        }
    )
    assert [(a.name, a.segment_type) for a in result.audience_ideas] == [
        ("Jewelry lovers", "interest"),
        ("Engaged shoppers", "lookalike"),
        ("Website visitors", "retargeting"),
        ("All jewelry buyers", "broad"),
    ]
    assert result.offer_ideas[0].label == "Free shipping over 75"
    assert result.offer_ideas[0].offer_id == "offer-1"


def test_director_models_accept_messy_output():
    ideas = IdeationResult.model_validate(
        {
            "concepts": [
                {
                    "ad_type": "UGC",
                    "image_count": "2 images",
                    "video_count": None,
                    "is_wildcard": "yes",
                    "claims": "14k gold",
                    "offer_ids": "offer-1",
                    "data_points": None,
                    "script": "She films the clasp in the first second",
                    "hook": "Look at the clasp",
                },
                None,
            ],
            "audience_ideas": None,
            "offer_ideas": "Free shipping",
        }
    )
    concept = ideas.concepts[0]
    assert concept.concept_name == "Look at the clasp"
    assert concept.image_count == 2
    assert concept.video_count == 0
    assert concept.is_wildcard is True
    assert concept.claims == ["14k gold"]
    assert concept.offer_ids == ["offer-1"]
    assert concept.script is not None
    assert concept.script.first_two_seconds == "She films the clasp in the first second"
    assert ideas.audience_ideas == []
    assert ideas.offer_ideas[0].label == "Free shipping"

    critique = CritiqueResult.model_validate(
        {
            "reviews": [
                {"brand_fit": "4/5", "keep": "false", "verdict": "Repetitive"},
                {"i": "1", "novelty": "high"},
            ],
            "brief": {"picks": [{"reason": "Best gift angle"}, "not a pick"], "summary": ["Line one", "Line two"]},
            "playbook_updates": [
                {"id": "hyp-1", "status": "Supported", "evidence": "CTR rose"},
                {"evidence": "no id"},
            ],
        }
    )
    assert critique.reviews[0].index == 0
    assert critique.reviews[0].brand_fit == 4
    assert critique.reviews[0].keep is False
    assert critique.reviews[1].index == 1
    assert critique.reviews[1].novelty == 3
    assert [(p.index, p.reason) for p in critique.brief.picks] == [(0, "Best gift angle"), (1, "not a pick")]
    assert critique.brief.summary == "Line one\nLine two"
    assert [(u.hypothesis_id, u.status) for u in critique.playbook_updates] == [("hyp-1", "supported")]

    challenge = ChallengeResult.model_validate(
        {
            "verdict": "Reconsider",
            "notes": "Angle already ran.",
            "alternative": "Try a macro clasp shot instead of another lifestyle frame.",
        }
    )
    assert challenge.verdict == "reconsider"
    assert challenge.notes == ["Angle already ran."]
    assert challenge.alternative is not None
    assert "macro clasp" in challenge.alternative.why


def test_every_ad_type_maps_to_a_renderable_style():
    for t in ad_types.AD_TYPES.values():
        assert ad_types.renderable(t), t.id
        assert t.style in STYLE_PLAYBOOKS, t.id
    assert ad_types.get_ad_type("nope").id == "LIFESTYLE"


def test_clamp_media_respects_type_media_and_limits():
    image_only = next(t for t in ad_types.AD_TYPES.values() if "VIDEO" not in t.media)
    assert ad_types.clamp_media(image_only, 9, 3)[1] == 0
    assert ad_types.clamp_media(image_only, 9, 3)[0] == 4
    images, videos = ad_types.clamp_media(ad_types.get_ad_type("UGC"), 0, 0)
    assert images + videos >= 1


def test_calendar_lookahead_in_october_includes_black_friday_and_christmas():
    upcoming = calendar.upcoming_occasions(date(2026, 10, 5), lookahead_days=84)
    keys = [o["key"] for o in upcoming]
    assert "black_friday" in keys and "christmas" in keys
    assert "valentines" not in keys
    bf = next(o for o in upcoming if o["key"] == "black_friday")
    assert bf["date"] == "2026-11-27"
    assert bf["window"] == "prep_now"
    assert [o["days_until"] for o in upcoming] == sorted(o["days_until"] for o in upcoming)


def test_calendar_marks_active_season_in_market():
    upcoming = calendar.upcoming_occasions(date(2026, 7, 1))
    wedding = next(o for o in upcoming if o["key"] == "wedding_season")
    assert wedding["window"] == "in_market"


def test_cost_estimate_and_budget_remaining():
    assert costs.estimate_generation_usd(0, 0) == 0
    one = costs.estimate_generation_usd(1, 0)
    assert costs.estimate_generation_usd(2, 1) > one > 0
    db = MagicMock()
    db.scalars.return_value.all.return_value = [
        SimpleNamespace(request_json=json.dumps({"image_count": 2, "video_count": 0}))
    ]
    budget = costs.budget_payload(db, "s", 10)
    assert budget["spent_usd"] == costs.estimate_generation_usd(2, 0)
    assert budget["remaining_usd"] == round(10 - budget["spent_usd"], 2)
    assert costs.budget_payload(db, "s", 0)["remaining_usd"] is None


def test_week_start_is_monday_midnight():
    start = costs.week_start(datetime(2026, 10, 1, 15, 30, tzinfo=UTC))
    assert start.weekday() == 0 and start.hour == 0 and start.day == 28


# ------------------------------------------------------------------ Shopify helpers


def test_inventory_counts_only_tracked_variants():
    raw = [
        {"id": "gid://shopify/Product/1", "variants": [
            {"inventory_management": "shopify", "inventory_quantity": 2},
            {"inventory_management": "shopify", "inventory_quantity": -3},
        ]},
        {"id": 2, "variants": [{"inventory_management": None, "inventory_quantity": 0}]},
    ]
    inv = ctx.inventory_from_products(raw)
    assert inv["1"] == 2
    assert inv["2"] is None
    assert ctx.stock_status(0, 3) == "out"
    assert ctx.stock_status(3, 3) == "low"
    assert ctx.stock_status(10, 3) == "in_stock"
    assert ctx.stock_status(None, 3) == "unknown"


def test_summarize_orders_skips_cancelled_and_splits_recent():
    now = datetime(2026, 10, 1, tzinfo=UTC)
    orders = [
        {"total_price": "100", "created_at": (now - timedelta(days=5)).isoformat(),
         "line_items": [{"product_id": 1, "quantity": 2, "price": "50"}]},
        {"total_price": "60", "created_at": (now - timedelta(days=60)).isoformat(),
         "line_items": [{"product_id": 1, "quantity": 1, "price": "60"}]},
        {"total_price": "999", "cancelled_at": "x", "line_items": [{"product_id": 1, "quantity": 9, "price": "1"}]},
    ]
    out = ctx.summarize_orders(orders, now=now)
    assert out["orders"] == 2 and out["aov"] == 80
    row = out["by_product"]["1"]
    assert row["units"] == 3 and row["units_30d"] == 2
    assert row["revenue"] == 160


def test_detect_fatigue_rising_frequency_falling_ctr():
    snap = lambda **k: SimpleNamespace(**{"spend": 50, "roas": 1.0, **k})  # noqa: E731
    snaps = {
        "tired": [snap(frequency=4.0, ctr=0.8), snap(frequency=2.5, ctr=1.4)],
        "fresh": [snap(frequency=1.4, ctr=1.6), snap(frequency=1.3, ctr=1.5)],
        "tiny": [snap(frequency=6.0, ctr=0.1, spend=2)],
    }
    out = ctx.detect_fatigue(snaps)
    assert [f["creative_id"] for f in out] == ["tired"]


# ------------------------------------------------------------------ guardrails


def test_guard_blocks_out_of_stock_low_stock_excluded_and_margin():
    texts = {}
    for product, word in [
        (_product(stock="out"), "out of stock"),
        (_product(stock="low", inventory=2), "low on stock"),
        (_product(excluded=True), "exclude"),
        (_product(below_margin_floor=True), "margin floor"),
    ]:
        blocked, _ = engine.guard_concept(_concept(), _context(product), texts)
        assert blocked and word in blocked
    blocked, _ = engine.guard_concept(_concept(product_id="missing"), _context(), texts)
    assert blocked


def test_guard_blocks_fake_testimonials_and_never_do():
    blocked, _ = engine.guard_concept(_concept(hook="I've worn it for 6 months, 5 stars"), _context(), {})
    assert blocked and "testimonial" in blocked
    blocked, _ = engine.guard_concept(_concept(hook="Countdown timer: 2 hours left"), _context(never_do=["countdown timer"]), {})
    assert blocked and "never-do" in blocked


def test_guard_flags_unconfirmed_offers_and_claims():
    concept = _concept(hook="Free shipping and hypoallergenic gold")
    _, flags = engine.guard_concept(concept, _context(), {})
    codes = {f["code"] for f in flags}
    assert codes == {"requires_confirmation", "unsupported_claim"}
    _, flags = engine.guard_concept(
        concept,
        _context(offers=[{"id": "o1", "label": "Free shipping over $75", "details": ""}]),
        {"1": "Hypoallergenic 14k gold plated"},
    )
    assert flags == []


def test_best_seller_claim_only_for_top_sellers():
    top = _product("1", units_90d=50)
    others = [_product(str(i), units_90d=i) for i in range(2, 6)]
    _, flags = engine.guard_concept(_concept(hook="Our best seller, restocked"), _context(top, *others), {})
    assert not flags
    _, flags = engine.guard_concept(_concept(product_id="2", hook="Our best seller, restocked"), _context(top, *others), {})
    assert any(f["code"] == "unsupported_claim" for f in flags)


def test_missing_photos_is_a_flag_not_a_block():
    blocked, flags = engine.guard_concept(_concept(), _context(_product(has_photos=False)), {})
    assert blocked is None and flags[0]["code"] == "needs_photos"


# ------------------------------------------------------------------ novelty, board, brief


def test_screen_rejects_repeats_of_past_ads_and_in_batch_duplicates():
    past = [{"source": "meta", "hook": "Her name in gold every single morning", "angle": "personal meaning"}]
    ideas = [
        _concept(),
        _concept(concept_name="Desk macro", ad_type="MACRO", hook="Clasp close-up under studio light", angle="craft"),
        _concept(concept_name="Desk macro two", ad_type="MACRO", hook="Clasp close-up under studio light again", angle="craft"),
    ]
    candidates, rejected = engine.screen_candidates(ideas, _context(), past, {})
    assert [c["concept_name"] for c in candidates] == ["Desk macro"]
    reasons = " ".join(r["reason"] for r in rejected)
    assert "past ad" in reasons and "Duplicate" in reasons


def test_similarity_and_novelty():
    assert memory.similarity("gold name necklace", "gold name necklace") == 1
    assert memory.similarity("gold necklace", "") == 0
    score, closest = memory.novelty({"hook": "brand new idea"}, [])
    assert score == 1 and closest is None


def _scored(n, **overrides):
    out = []
    for i in range(n):
        item = _concept(
            concept_name=f"c{i}",
            ad_type=["UGC", "MACRO", "LIFESTYLE", "UNBOXING"][i % 4],
            product_id=str(i % 5),
            hook=f"hook {i}",
        )
        item.update(index=i, score=1 - i / 100, flags=[], image_count=1, video_count=0, **overrides)
        out.append(item)
    return out


def test_board_is_diverse_and_includes_wildcards():
    scored = _scored(14)
    scored[10]["is_wildcard"] = True
    scored[11]["is_wildcard"] = True
    board = engine.select_board(scored, "bold")
    assert engine.BOARD_MIN <= len(board) <= engine.BOARD_MAX
    assert sum(1 for c in board if c.get("is_wildcard")) == 2
    by_type = {}
    for c in board:
        by_type[c["ad_type"]] = by_type.get(c["ad_type"], 0) + 1
    assert max(by_type.values()) <= engine.PER_TYPE_CAP
    safe = engine.select_board(scored, "safe")
    assert sum(1 for c in safe if c.get("is_wildcard")) == 1


def test_brief_follows_critic_picks_and_respects_budget_and_caps():
    board = _scored(6)
    board[5]["flags"] = [{"code": "requires_confirmation", "message": "offer"}]
    critique = CritiqueResult(
        reviews=[],
        brief=WeeklyBrief(headline="Gift season", picks=[BriefPick(index=3, reason="gift peak"), BriefPick(index=5, reason="x")]),
    )
    brief = engine.build_brief(board, critique, remaining_usd=None, max_images=3, max_videos=0)
    assert brief["items"][0]["index"] == 3
    assert all(i["index"] != 5 for i in brief["items"])
    assert brief["total_images"] == 3
    one = costs.estimate_generation_usd(1, 0)
    tight = engine.build_brief(board, None, remaining_usd=one * 2 + 0.001, max_images=6, max_videos=2)
    assert len(tight["items"]) == 2
    assert tight["estimated_cost_usd"] <= one * 2 + 0.001


def test_apply_reviews_drops_rejected_and_uses_improved_hook():
    candidates = [dict(_concept(), novelty=0.9), dict(_concept(hook="other"), novelty=0.2)]
    critique = CritiqueResult(
        reviews=[
            ConceptReview(index=0, predicted_performance=5, improved_hook="Better hook"),
            ConceptReview(index=1, keep=False),
        ]
    )
    scored = engine.apply_reviews(candidates, critique, "balanced")
    assert len(scored) == 1 and scored[0]["hook"] == "Better hook"


def test_alerts_include_fatigue_stock_and_occasions():
    context = _context(_product(stock="low", inventory=1, units_90d=40))
    context["meta"] = {"fatigue": [{"creative_id": "m1", "reason": "Frequency up"}], "clone_candidates": []}
    context["calendar"] = {"upcoming": calendar.upcoming_occasions(date(2026, 10, 20))}
    types = {a["type"] for a in engine.build_alerts(context)}
    assert {"fatigue", "stock", "occasion"} <= types


def test_request_checks_flag_out_of_stock_request():
    notes = engine.request_checks({"product_id": "1", "styles": ["UGC"]}, _context(_product(stock="out")), [])
    assert any("out of stock" in n for n in notes)


# ------------------------------------------------------------------ pipeline + actions (in-memory DB)


def _db():
    engine_ = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine_)
    return sessionmaker(bind=engine_)()


def _seed(db):
    user = User(email="o@example.com", password_hash="x", full_name="Owner", is_verified=True)
    db.add(user)
    db.flush()
    store = Store(
        owner_id=user.id,
        shop_domain="luxory.myshopify.com",
        name="Luxory",
        status=StoreStatus.CONNECTED.value,
        currency="CAD",
        access_token_encrypted="t",
    )
    db.add(store)
    db.flush()
    db.add(StoreAIAdsSettings(store_id=store.id, brand_style="warm", default_audience="women 25-45"))
    for pid in ("1", "2"):
        db.add(ShopifyCatalogProduct(store_id=store.id, shopify_product_id=pid, title=f"Necklace {pid}"))
    db.commit()
    return user, store


def _ideas():
    return IdeationResult(
        concepts=[
            DirectorConcept(concept_name="Name reveal", ad_type="UNBOXING", product_id="1", hook="She opens the box and sees her name",
                            angle="gift", hypothesis="Reveal beats flat lay for gifts", test_variable="format"),
            DirectorConcept(concept_name="Macro clasp", ad_type="MACRO", product_id="2", hook="Look closer at the clasp",
                            angle="craft", hypothesis="Craft angle lifts CTR", test_variable="angle"),
            DirectorConcept(concept_name="Out of stock idea", ad_type="UGC", product_id="3", hook="Totally different words here",
                            angle="ugc"),
            DirectorConcept(concept_name="Wild idea", ad_type="SPLIT_SCREEN", product_id="2", hook="Monday versus Friday energy",
                            angle="mood", is_wildcard=True),
        ],
        audience_ideas=[],
        offer_ideas=[],
    )


def _run_pipeline(db, user, store, critique=None):
    context = _context(_product("1"), _product("2"), _product("3", stock="out"))
    fake = MagicMock()
    fake.ideate = AsyncMock(return_value=_ideas())
    fake.critique = AsyncMock(return_value=critique) if critique else AsyncMock(side_effect=RuntimeError("down"))
    report = service.create_report(db, store.id, trigger="manual")
    with (
        patch.object(service, "build_context", AsyncMock(return_value=context)),
        patch.object(service, "DirectorEngine", return_value=fake),
        patch.object(service, "AdsOpenAIClient"),
    ):
        asyncio.run(service.run_pipeline(db, store, user, "sk", report))
    return report


def test_pipeline_saves_board_brief_and_blocks_out_of_stock():
    db = _db()
    user, store = _seed(db)
    report = _run_pipeline(db, user, store)
    assert report.status == "COMPLETED"
    rows = db.query(AIDirectorSuggestion).filter_by(report_id=report.id).all()
    names = {r.concept_name for r in rows}
    assert "Out of stock idea" not in names
    assert {"Name reveal", "Macro clasp", "Wild idea"} <= names
    wild = next(r for r in rows if r.concept_name == "Wild idea")
    assert wild.is_experiment and wild.kind == "wildcard" and not wild.in_brief
    brief = json.loads(report.brief_json)
    assert brief["items"] and all(i.get("suggestion_id") for i in brief["items"])
    assert any("out of stock" in r["reason"] for r in brief["filtered_out"])
    assert all(r.ad_name.startswith("LUX | ") for r in rows)


def test_new_run_expires_unsaved_ideas_but_keeps_saved_ones():
    db = _db()
    user, store = _seed(db)
    first = _run_pipeline(db, user, store)
    rows = db.query(AIDirectorSuggestion).filter_by(report_id=first.id).all()
    rows[0].status = "SAVED"
    db.commit()
    _run_pipeline(db, user, store)
    db.expire_all()
    statuses = {r.id: r.status for r in db.query(AIDirectorSuggestion).filter_by(report_id=first.id).all()}
    assert statuses[rows[0].id] == "SAVED"
    assert all(s == "EXPIRED" for sid, s in statuses.items() if sid != rows[0].id)


def test_brief_jobs_group_by_product():
    db = _db()
    user, store = _seed(db)
    critique = CritiqueResult(
        reviews=[],
        brief=WeeklyBrief(picks=[BriefPick(index=0, reason="a"), BriefPick(index=1, reason="b")]),
    )
    report = _run_pipeline(db, user, store, critique=critique)
    groups = service.brief_jobs(db, report)
    assert {g["product_id"] for g in groups} <= {"1", "2"}
    for g in groups:
        assert g["image_count"] + g["video_count"] >= 1
        assert all(r.product_id == g["product_id"] for r in g["rows"])


def test_dismiss_records_preference_and_generate_respects_cap():
    db = _db()
    user, store = _seed(db)
    report = _run_pipeline(db, user, store)
    rows = db.query(AIDirectorSuggestion).filter_by(report_id=report.id).all()
    svc = service.DirectorService()

    svc.dismiss(db, user, store.id, rows[0].id, "too salesy")
    pref = db.query(AIAdsPlaybookEntry).filter_by(store_id=store.id, kind="preference").one()
    assert "too salesy" in pref.statement

    director = db.query(AIDirectorSettings).filter_by(store_id=store.id).one()
    director.weekly_credit_cap_usd = 0.01
    db.commit()
    target = rows[1]
    with pytest.raises(HTTPException) as exc:
        svc.generate(db, user, store.id, target.id)
    assert exc.value.status_code == 409

    with patch(
        "app.services.ai_ads.service.AIAdsService.create_generation_job",
        return_value={"job_id": "job-1", "id": "job-1"},
    ) as create:
        out = svc.generate(db, user, store.id, target.id, override_cap=True)
    body = create.call_args.args[3]
    assert body["director_concepts"][0]["suggestion_id"] == target.id
    assert body["styles"] == [ad_types.get_ad_type(target.ad_type).style]
    assert out["suggestion"]["status"] == "GENERATED"
    assert db.query(AIAdsPlaybookEntry).filter_by(suggestion_id=target.id, kind="hypothesis").count() == (
        1 if target.hypothesis else 0
    )


def test_settings_update_sanitizes_lists():
    db = _db()
    _, store = _seed(db)
    row = service.get_director_settings(db, store.id)
    service.update_director_settings(
        db,
        row,
        {
            "aggressiveness": "bold",
            "weekly_credit_cap_usd": -5,
            "never_do": ["  pets ", ""],
            "offers": [{"label": "Free shipping over $75"}, {"label": "  "}],
            "margin_floor_pct": 120,
        },
    )
    card = service.settings_card(row)
    assert card["aggressiveness"] == "bold"
    assert card["weekly_credit_cap_usd"] == 0
    assert card["never_do"] == ["pets"]
    assert [o["label"] for o in card["offers"]] == ["Free shipping over $75"]
    assert card["margin_floor_pct"] == 95


def test_reconcile_marks_interrupted_manual_reports_failed():
    db = _db()
    _, store = _seed(db)
    report = service.create_report(db, store.id, trigger="manual")
    report.status = "RUNNING"
    db.commit()
    service.reconcile_reports(db)
    assert db.get(AIDirectorReport, report.id).status == "FAILED"
