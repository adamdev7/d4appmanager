"""Weekly AI Ads automation: per-store schedule, one run per week, catch-up, and step outcomes."""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AIAdsWeeklyRun,
    CreativeAsset,
    CreativeGenerationJob,
    Store,
    StoreAIAdsSettings,
    StoreStatus,
    User,
)
from app.db.session import Base
from app.services.ai_ads import weekly_runs

TORONTO = ZoneInfo("America/Toronto")


def _factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _store(db, *, timezone="UTC", **settings_kwargs) -> Store:
    user = User(email="owner@example.com", password_hash="x", full_name="Owner", is_verified=True)
    db.add(user)
    db.flush()
    store = Store(
        owner_id=user.id,
        shop_domain="luxory.myshopify.com",
        name="Luxory",
        status=StoreStatus.CONNECTED.value,
        timezone=timezone,
        access_token_encrypted="token",
    )
    db.add(store)
    db.flush()
    defaults = dict(
        weekly_generation_enabled=True,
        generation_day="sunday",
        image_count=4,
        video_count=1,
        brand_style="warm light",
        default_audience="new moms",
        meta_page_id=None,
        whatsapp_weekly_alerts_enabled=True,
    )
    defaults.update(settings_kwargs)
    db.add(StoreAIAdsSettings(store_id=store.id, **defaults))
    db.commit()
    return store


# ------------------------------------------------------------------ schedule math


def test_latest_slot_is_sunday_six_am_store_time():
    # Wednesday 2026-09-30 15:00 UTC -> previous Sunday 2026-09-27 06:00 Toronto.
    now = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    slot = weekly_runs.latest_slot(now, "sunday", "America/Toronto", 6)
    assert slot == datetime(2026, 9, 27, 6, 0, tzinfo=TORONTO)
    assert weekly_runs.next_slot(now, "sunday", "America/Toronto", 6) == datetime(2026, 10, 4, 6, 0, tzinfo=TORONTO)


def test_latest_slot_before_six_on_the_day_points_to_last_week():
    # Sunday 05:30 Toronto is before the slot, so the latest slot is the previous Sunday.
    now = datetime(2026, 10, 4, 5, 30, tzinfo=TORONTO)
    slot = weekly_runs.latest_slot(now, "sunday", "America/Toronto", 6)
    assert slot.date().isoformat() == "2026-09-27"


def test_weekday_parsing_accepts_names_and_defaults():
    assert weekly_runs.weekday_index("Sunday") == 6
    assert weekly_runs.weekday_index("sun") == 6
    assert weekly_runs.weekday_index("0") == 6
    assert weekly_runs.weekday_index("monday") == 0


def test_store_timezone_falls_back_to_toronto_when_unset():
    assert weekly_runs.store_timezone_name(SimpleNamespace(timezone="UTC")) == "America/Toronto"
    assert weekly_runs.store_timezone_name(SimpleNamespace(timezone="")) == "America/Toronto"
    assert weekly_runs.store_timezone_name(SimpleNamespace(timezone="Europe/Paris")) == "Europe/Paris"
    assert weekly_runs.store_timezone_name(SimpleNamespace(timezone="Not/AZone")) == "America/Toronto"


# ------------------------------------------------------------------ scheduling


def test_scheduler_runs_once_per_week_and_catches_up():
    factory = _factory()
    db = factory()
    store = _store(db)
    wednesday = datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    with patch.object(weekly_runs, "start_run") as start:
        first = weekly_runs.schedule_due_runs(db, now=wednesday)
        assert len(first) == 1
        run = db.get(AIAdsWeeklyRun, first[0])
        assert run.trigger == "catch_up"
        assert run.schedule_key == run.week_key
        # Mark it done so the "already running" guard is not what blocks the second call.
        run.status = "SUCCEEDED"
        db.commit()
        again = weekly_runs.schedule_due_runs(db, now=wednesday)
        assert again == []
        assert start.call_count == 1
    assert db.query(AIAdsWeeklyRun).filter_by(store_id=store.id).count() == 1


def test_scheduler_ignores_disabled_stores_and_meta_page_id_is_not_required():
    factory = _factory()
    db = factory()
    _store(db, weekly_generation_enabled=False)
    with patch.object(weekly_runs, "start_run"):
        assert weekly_runs.schedule_due_runs(db, now=datetime(2026, 9, 30, 15, tzinfo=UTC)) == []


def test_on_time_run_is_labelled_schedule():
    factory = _factory()
    db = factory()
    _store(db)
    sunday_morning = datetime(2026, 10, 4, 6, 1, tzinfo=TORONTO)
    with patch.object(weekly_runs, "start_run"):
        ids = weekly_runs.schedule_due_runs(db, now=sunday_morning)
    assert db.get(AIAdsWeeklyRun, ids[0]).trigger == "schedule"


def test_manual_run_does_not_consume_the_weekly_slot():
    factory = _factory()
    db = factory()
    store = _store(db)
    manual = weekly_runs.create_run(db, store.id, trigger="manual")
    assert manual.schedule_key is None
    manual.status = "SUCCEEDED"
    db.commit()
    with patch.object(weekly_runs, "start_run"):
        ids = weekly_runs.schedule_due_runs(db, now=datetime(2026, 9, 30, 15, tzinfo=UTC))
    assert len(ids) == 1


# ------------------------------------------------------------------ execution


def _run_execute(factory, run_id, *, api_key="sk-test", meta_client=None, product=None, plans=None):
    orch = MagicMock()
    orch.meta_client.return_value = meta_client
    orch.shopify_client.return_value = None
    orch.sync_meta = AsyncMock(return_value={"ads": 3})
    orch.analyze_creatives = AsyncMock()
    with (
        patch.object(weekly_runs, "SessionLocal", factory),
        patch.object(weekly_runs, "resolve_openai_api_key", return_value=api_key),
        patch.object(weekly_runs, "imaging_available", return_value=True),
        patch.object(weekly_runs, "pick_product", return_value=product),
        patch.object(weekly_runs, "_director_plans", AsyncMock(return_value=plans or [])),
        patch.object(weekly_runs, "enqueue_generation_job") as enqueue,
        patch("app.services.ai_ads.orchestrator.AdsAIOrchestrator", return_value=orch),
    ):
        asyncio.run(weekly_runs.execute_run(run_id))
    return enqueue, orch


def test_missing_openai_key_fails_visibly():
    factory = _factory()
    db = factory()
    store = _store(db)
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    enqueue, _ = _run_execute(factory, run.id, api_key=None)
    db.expire_all()
    run = db.get(AIAdsWeeklyRun, run.id)
    assert run.status == "FAILED"
    assert "OpenAI API key" in run.error_message
    assert not enqueue.called
    row = db.query(StoreAIAdsSettings).filter_by(store_id=store.id).one()
    assert "OpenAI API key" in row.last_weekly_error


def test_meta_not_connected_warns_and_still_queues_generation():
    factory = _factory()
    db = factory()
    store = _store(db)
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    product = SimpleNamespace(shopify_product_id="111", title="Baby Carrier")
    enqueue, orch = _run_execute(factory, run.id, meta_client=None, product=product)
    db.expire_all()
    run = db.get(AIAdsWeeklyRun, run.id)
    steps = {s["key"]: s for s in weekly_runs.load_steps(run)}
    assert steps["meta_sync"]["status"] == "warning"
    # No Shopify client in this test, so the cached catalog is used and noted.
    assert steps["products"]["status"] == "warning"
    assert "cached products" in steps["products"]["detail"]
    assert run.status == "RUNNING"
    assert run.job_id and enqueue.called
    assert not orch.sync_meta.called
    job = db.get(CreativeGenerationJob, run.job_id)
    request = json.loads(job.request_json)
    assert request["source"] == "weekly_automation"
    assert request["image_count"] == 4 and request["video_count"] == 1
    assert request["brand_style"] == "warm light"
    assert request["audience"] == "new moms"
    assert request["weekly_run_id"] == run.id


def test_meta_sync_error_does_not_abort_the_batch():
    factory = _factory()
    db = factory()
    store = _store(db)
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    product = SimpleNamespace(shopify_product_id="111", title="Baby Carrier")
    orch_meta = object()
    orch = MagicMock()
    orch.meta_client.return_value = orch_meta
    orch.shopify_client.return_value = None
    orch.sync_meta = AsyncMock(side_effect=RuntimeError("token expired"))
    with (
        patch.object(weekly_runs, "SessionLocal", factory),
        patch.object(weekly_runs, "resolve_openai_api_key", return_value="sk"),
        patch.object(weekly_runs, "imaging_available", return_value=True),
        patch.object(weekly_runs, "pick_product", return_value=product),
        patch.object(weekly_runs, "_director_plans", AsyncMock(return_value=[])),
        patch.object(weekly_runs, "enqueue_generation_job") as enqueue,
        patch("app.services.ai_ads.orchestrator.AdsAIOrchestrator", return_value=orch),
    ):
        asyncio.run(weekly_runs.execute_run(run.id))
    db.expire_all()
    run = db.get(AIAdsWeeklyRun, run.id)
    steps = {s["key"]: s for s in weekly_runs.load_steps(run)}
    assert steps["meta_sync"]["status"] == "warning"
    assert enqueue.called


def test_no_product_with_photos_fails_with_clear_message():
    factory = _factory()
    db = factory()
    store = _store(db)
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    _run_execute(factory, run.id, product=None)
    db.expire_all()
    run = db.get(AIAdsWeeklyRun, run.id)
    assert run.status == "FAILED"
    assert "photos" in run.error_message


# ------------------------------------------------------------------ finalize


def _job_with_assets(db, store, *, status, ready_images, failed_images=0, ready_videos=0):
    job = CreativeGenerationJob(store_id=store.id, user_id=store.owner_id, status=status, request_json="{}")
    db.add(job)
    db.flush()
    for _ in range(ready_images):
        db.add(CreativeAsset(store_id=store.id, job_id=job.id, type="IMAGE", status="READY"))
    for _ in range(failed_images):
        db.add(CreativeAsset(store_id=store.id, job_id=job.id, type="IMAGE", status="FAILED"))
    for _ in range(ready_videos):
        db.add(CreativeAsset(store_id=store.id, job_id=job.id, type="VIDEO", status="READY"))
    db.commit()
    return job


def _running_run(db, store, job):
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    run.status = "RUNNING"
    run.job_id = job.id
    run.images_requested = 4
    run.videos_requested = 1
    db.commit()
    return run


def test_finalize_marks_success_and_records_whatsapp():
    factory = _factory()
    db = factory()
    store = _store(db)
    job = _job_with_assets(db, store, status="COMPLETED", ready_images=4, ready_videos=1)
    run = _running_run(db, store, job)
    weekly_runs.finalize_run_for_job(db, job, whatsapp=("ok", "Recap sent on WhatsApp."))
    assert run.status == "SUCCEEDED"
    assert (run.images_generated, run.videos_generated) == (4, 1)
    steps = {s["key"]: s for s in weekly_runs.load_steps(run)}
    assert steps["whatsapp"]["status"] == "ok"
    assert steps["stills"]["status"] == "ok"


def test_finalize_partial_when_some_creatives_fail_and_whatsapp_failure_is_non_fatal():
    factory = _factory()
    db = factory()
    store = _store(db)
    job = _job_with_assets(db, store, status="PARTIAL", ready_images=2, failed_images=2, ready_videos=1)
    run = _running_run(db, store, job)
    weekly_runs.finalize_run_for_job(db, job, whatsapp=("failed", "No number saved"))
    assert run.status == "PARTIAL"
    steps = {s["key"]: s for s in weekly_runs.load_steps(run)}
    assert steps["stills"]["status"] == "warning"
    assert steps["whatsapp"]["status"] == "warning"


def test_finalize_is_noop_for_non_weekly_jobs():
    factory = _factory()
    db = factory()
    store = _store(db)
    job = _job_with_assets(db, store, status="COMPLETED", ready_images=1)
    assert weekly_runs.finalize_run_for_job(db, job) is None


def test_director_brief_creates_one_job_per_product():
    factory = _factory()
    db = factory()
    store = _store(db)
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    plans = [
        {
            "product_id": "111",
            "product_title": "Baby Carrier",
            "image_count": 2,
            "video_count": 0,
            "styles": ["UGC"],
            "director_concepts": [{"suggestion_id": "s1", "hook": "Hands free", "image_count": 2, "video_count": 0}],
        },
        {
            "product_id": "222",
            "product_title": "Name Necklace",
            "image_count": 1,
            "video_count": 1,
            "styles": ["UNBOXING"],
            "director_concepts": [{"suggestion_id": "s2", "hook": "Her name", "image_count": 1, "video_count": 1}],
        },
    ]
    enqueue, _ = _run_execute(factory, run.id, plans=plans)
    db.expire_all()
    run = db.get(AIAdsWeeklyRun, run.id)
    job_ids = weekly_runs.run_job_ids(run)
    assert len(job_ids) == 2 and enqueue.call_count == 2
    assert (run.images_requested, run.videos_requested) == (3, 1)
    assert "Baby Carrier" in run.product_title and "Name Necklace" in run.product_title
    second = json.loads(db.get(CreativeGenerationJob, job_ids[1]).request_json)
    assert second["product_id"] == "222"
    assert second["styles"] == ["UNBOXING"]
    assert second["director_concepts"][0]["hook"] == "Her name"


def test_finalize_waits_for_every_job_of_a_multi_product_run():
    factory = _factory()
    db = factory()
    store = _store(db)
    first = _job_with_assets(db, store, status="COMPLETED", ready_images=2)
    second = _job_with_assets(db, store, status="RUNNING", ready_images=0)
    run = _running_run(db, store, first)
    run.job_ids_json = json.dumps([first.id, second.id])
    run.images_requested, run.videos_requested = 3, 1
    db.commit()
    weekly_runs.finalize_run_for_job(db, first)
    assert run.status == "RUNNING"
    second.status = "COMPLETED"
    db.add(CreativeAsset(store_id=store.id, job_id=second.id, type="IMAGE", status="READY"))
    db.add(CreativeAsset(store_id=store.id, job_id=second.id, type="VIDEO", status="READY"))
    db.commit()
    assert weekly_runs.run_for_job(db, second.id).id == run.id
    weekly_runs.finalize_run_for_job(db, second, whatsapp=("ok", "Recap sent on WhatsApp."))
    assert run.status == "SUCCEEDED"
    assert (run.images_generated, run.videos_generated) == (3, 1)


def test_fallback_batch_is_trimmed_to_the_weekly_credit_cap():
    from app.db.models import AIDirectorSettings

    factory = _factory()
    db = factory()
    store = _store(db)
    db.add(AIDirectorSettings(store_id=store.id, weekly_credit_cap_usd=1.0))
    db.commit()
    run = weekly_runs.create_run(db, store.id, trigger="manual")
    product = SimpleNamespace(shopify_product_id="111", title="Baby Carrier")
    row = db.query(StoreAIAdsSettings).filter_by(store_id=store.id).one()
    with patch.object(weekly_runs, "pick_product", return_value=product):
        plan = weekly_runs._fallback_plan(db, run, store, MagicMock(), row, 4, 1)
    assert plan["video_count"] == 0
    assert 1 <= plan["image_count"] < 4


def test_set_step_adds_missing_director_step_in_order():
    run = AIAdsWeeklyRun(store_id="s", trigger="manual", week_key="2026-W40", status="RUNNING")
    run.steps_json = json.dumps(
        [{"key": k, "label": k, "status": "pending", "detail": "", "at": None} for k in ("preflight", "products", "stills")]
    )
    weekly_runs.set_step(run, "director", "ok", "3 concepts")
    keys = [s["key"] for s in weekly_runs.load_steps(run)]
    assert keys == ["preflight", "products", "director", "stills"]


def test_reconcile_frees_the_week_when_restart_interrupted_before_job():
    factory = _factory()
    db = factory()
    store = _store(db)
    with patch.object(weekly_runs, "start_run"):
        ids = weekly_runs.schedule_due_runs(db, now=datetime(2026, 9, 30, 15, tzinfo=UTC))
    weekly_runs.reconcile_runs(db)
    run = db.get(AIAdsWeeklyRun, ids[0])
    assert run.status == "FAILED"
    assert run.schedule_key is None
    with patch.object(weekly_runs, "start_run"):
        retry = weekly_runs.schedule_due_runs(db, now=datetime(2026, 9, 30, 15, 5, tzinfo=UTC))
    assert len(retry) == 1
