"""Autopilot gating: which settings rows get scanned, and when it pauses itself."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_email_assistant import automation_worker
from app.ai_email_assistant.order_context import find_customer_orders
from app.db.models import (
    AIEmailAssistantSettings,
    OrderTracking,
    Store,
    StoreStatus,
    User,
)
from app.db.session import Base


def _factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _user_store(db, *, domain="luxory.myshopify.com") -> tuple[User, Store]:
    user = db.query(User).first()
    if user is None:
        user = User(
            email="owner@example.com",
            password_hash="x",
            full_name="Owner",
            is_verified=True,
        )
        db.add(user)
        db.flush()
    store = Store(
        owner_id=user.id,
        shop_domain=domain,
        name="Luxory",
        status=StoreStatus.CONNECTED.value,
    )
    db.add(store)
    db.commit()
    return user, store


def _settings(db, user, store, **overrides) -> str:
    row = AIEmailAssistantSettings(user_id=user.id, store_id=store.id, **overrides)
    db.add(row)
    db.commit()
    return row.id


def test_autopilot_skips_when_disabled():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    settings_id = _settings(db, user, store, automation_enabled=False)
    db.close()

    with patch.object(automation_worker, "SessionLocal", factory):
        result = asyncio.run(automation_worker.run_automation_for_settings(settings_id))

    assert result == {"skipped": True, "reason": "automation disabled"}


def test_autopilot_pauses_itself_without_an_openai_key():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    settings_id = _settings(db, user, store, automation_enabled=True)
    db.close()

    with patch.object(automation_worker, "SessionLocal", factory), patch.object(
        automation_worker, "is_openai_configured", return_value=False
    ):
        result = asyncio.run(automation_worker.run_automation_for_settings(settings_id))

    assert result["stopped"] is True
    assert "OpenAI API key" in result["error"]

    check = factory()
    assert check.get(AIEmailAssistantSettings, settings_id).automation_enabled is False
    check.close()


def test_only_due_rows_are_scanned():
    factory = _factory()
    db = factory()
    now = datetime.now(UTC)

    user, store = _user_store(db)
    due_id = _settings(
        db,
        user,
        store,
        automation_enabled=True,
        automation_interval_minutes=15,
        automation_last_run_at=now - timedelta(minutes=30),
    )
    # A second store keeps the unique (user, store) constraint satisfied.
    _, other_store = _user_store(db, domain="second.myshopify.com")
    not_due_id = _settings(
        db,
        user,
        other_store,
        automation_enabled=True,
        automation_interval_minutes=15,
        automation_last_run_at=now - timedelta(minutes=2),
    )
    db.close()

    scanned: list[str] = []

    async def fake_run(settings_id, *, force=False):
        scanned.append(settings_id)
        return {"ok": True}

    with patch.object(automation_worker, "SessionLocal", factory), patch.object(
        automation_worker, "run_automation_for_settings", fake_run
    ):
        asyncio.run(automation_worker.run_due_automations())

    assert due_id in scanned
    assert not_due_id not in scanned


def test_rows_that_never_ran_are_due_immediately():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    settings_id = _settings(
        db, user, store, automation_enabled=True, automation_last_run_at=None
    )
    db.close()

    scanned: list[str] = []

    async def fake_run(settings_id, *, force=False):
        scanned.append(settings_id)
        return {"ok": True}

    with patch.object(automation_worker, "SessionLocal", factory), patch.object(
        automation_worker, "run_automation_for_settings", fake_run
    ):
        asyncio.run(automation_worker.run_due_automations())

    assert scanned == [settings_id]


def test_legacy_rows_without_a_store_are_never_scanned():
    factory = _factory()
    db = factory()
    user, _ = _user_store(db)
    db.add(AIEmailAssistantSettings(user_id=user.id, store_id=None, automation_enabled=True))
    db.commit()
    db.close()

    scanned: list[str] = []

    async def fake_run(settings_id, *, force=False):
        scanned.append(settings_id)
        return {"ok": True}

    with patch.object(automation_worker, "SessionLocal", factory), patch.object(
        automation_worker, "run_automation_for_settings", fake_run
    ):
        asyncio.run(automation_worker.run_due_automations())

    assert scanned == []


def test_orders_match_by_sender_and_by_quoted_order_number():
    factory = _factory()
    db = factory()
    _, store = _user_store(db)

    db.add(
        OrderTracking(
            store_id=store.id,
            order_number_display="#1045",
            order_number_normalized="1045",
            customer_email="omw4973@outlook.com",
            tracking_number="YT2625500704564137",
            carrier="YunExpress",
            status="in_transit",
            timeline_json=json.dumps([]),
        )
    )
    db.add(
        OrderTracking(
            store_id=store.id,
            order_number_display="#2001",
            order_number_normalized="2001",
            customer_email="someone.else@example.com",
            tracking_number=None,
            status="pending",
            timeline_json=json.dumps([]),
        )
    )
    db.commit()

    by_sender = asyncio.run(
        find_customer_orders(
            db,
            store,
            customer_email="omw4973@outlook.com",
            subject="Where is my order?",
            body="No number here",
            live_lookup=False,
        )
    )
    assert [m.row.order_number_display for m in by_sender] == ["#1045"]
    assert by_sender[0].match_reason == "customer_email"

    # An order number quoted in the body is matched even when the sender differs.
    by_quote = asyncio.run(
        find_customer_orders(
            db,
            store,
            customer_email="new.address@example.com",
            subject="Question about order #2001",
            body="Any update?",
            live_lookup=False,
        )
    )
    assert [m.row.order_number_display for m in by_quote] == ["#2001"]
    assert by_quote[0].match_reason == "order_number_in_email"
    db.close()
