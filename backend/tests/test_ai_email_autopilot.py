"""Autopilot gating: which settings rows get scanned, and when it pauses itself."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_email_assistant import automation_worker
from app.ai_email_assistant.openai_errors import OpenAIServiceError
from app.ai_email_assistant.order_context import find_customer_orders
from app.ai_email_assistant.services.assistant_service import (
    AIEmailAssistantService,
    is_per_message_gmail_failure,
)
from app.db.models import (
    AIEmailAssistantSettings,
    AIEmailReply,
    GmailAccount,
    InboxEmail,
    InboxEmailStatus,
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


def test_manual_run_finishes_in_the_background():
    finished = asyncio.Event()

    async def fake_run(settings_id, *, force=False):
        await finished.wait()
        return {"ok": True, "processed": True, "stopped": False}

    async def scenario():
        with patch.object(automation_worker, "run_automation_for_settings", fake_run):
            first = await automation_worker.start_manual_automation("settings-1")
            second = await automation_worker.start_manual_automation("settings-1")
            assert first is True
            assert second is False
            assert automation_worker.manual_run_status("settings-1")["status"] == "running"
            finished.set()
            for _ in range(50):
                status = automation_worker.manual_run_status("settings-1")
                if status["status"] == "done":
                    assert status["ok"] is True
                    return
                await asyncio.sleep(0.01)
        raise AssertionError("manual run did not finish")

    asyncio.run(scenario())


def test_one_gmail_rejection_does_not_pause_autopilot():
    assert is_per_message_gmail_failure(
        502, "Failed to send reply via Gmail: Invalid thread_id value"
    )
    assert not is_per_message_gmail_failure(
        502,
        "Failed to send reply via Gmail: Reconnect Gmail in Settings, then turn autopilot back on.",
    )
    assert not is_per_message_gmail_failure(502, "OpenAI is temporarily unavailable.")


def _inbox(db, user, store, account, *, subject, thread, received_at, status="new"):
    row = InboxEmail(
        user_id=user.id,
        store_id=store.id,
        gmail_account_id=account.id,
        gmail_message_id=f"msg-{thread}",
        thread_id=thread,
        sender="Buyer <buyer@example.com>",
        sender_email="buyer@example.com",
        subject=subject,
        body_text="Where is my order?",
        status=status,
        received_at=received_at,
    )
    db.add(row)
    db.flush()
    return row


def test_autopilot_keeps_going_after_one_gmail_send_failure():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    account = GmailAccount(
        owner_id=user.id,
        email="store@luxory.com",
        display_name="Luxory",
        status="connected",
    )
    db.add(account)
    db.flush()
    now = datetime.now(UTC)
    first = _inbox(
        db,
        user,
        store,
        account,
        subject="Order update",
        thread="t-fail",
        received_at=now - timedelta(minutes=10),
    )
    second = _inbox(
        db,
        user,
        store,
        account,
        subject="Shipping question",
        thread="t-ok",
        received_at=now - timedelta(minutes=5),
    )
    settings_id = _settings(
        db,
        user,
        store,
        automation_enabled=True,
        auto_send_enabled=True,
    )
    settings_row = db.get(AIEmailAssistantSettings, settings_id)
    seen: list[str] = []

    async def fake_generate(db, user, inbox_email_id, *, store_id=None):
        seen.append(inbox_email_id)
        if inbox_email_id == first.id:
            raise HTTPException(
                status_code=502,
                detail="Failed to send reply via Gmail: Invalid thread_id value",
            )
        return None

    async def still_unread(*args, **kwargs):
        return False

    async def no_duplicate(*args, **kwargs):
        return None

    service = AIEmailAssistantService()
    with patch(
        "app.ai_email_assistant.services.assistant_service.resolve_openai_api_key",
        return_value="sk-test",
    ), patch.object(
        service, "_skip_if_no_longer_unread_in_gmail", still_unread
    ), patch.object(
        service, "_duplicate_skip_reason", no_duplicate
    ), patch.object(service, "generate_and_maybe_send", fake_generate):
        processed = asyncio.run(
            service.process_pending_replies(db, user, settings_row, store_id=store.id)
        )

    assert seen == [first.id, second.id]
    assert processed == 1
    assert db.get(AIEmailAssistantSettings, settings_id).automation_enabled is True
    db.close()


def test_gmail_permission_failure_still_pauses_autopilot():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    account = GmailAccount(
        owner_id=user.id,
        email="store@luxory.com",
        display_name="Luxory",
        status="connected",
    )
    db.add(account)
    db.flush()
    now = datetime.now(UTC)
    first = _inbox(
        db,
        user,
        store,
        account,
        subject="Order update",
        thread="t-auth",
        received_at=now - timedelta(minutes=10),
    )
    _inbox(
        db,
        user,
        store,
        account,
        subject="Shipping question",
        thread="t-later",
        received_at=now - timedelta(minutes=5),
    )
    settings_id = _settings(db, user, store, automation_enabled=True, auto_send_enabled=True)
    settings_row = db.get(AIEmailAssistantSettings, settings_id)
    seen: list[str] = []

    async def fake_generate(db, user, inbox_email_id, *, store_id=None):
        seen.append(inbox_email_id)
        raise HTTPException(
            status_code=502,
            detail=(
                "Failed to send reply via Gmail: Gmail refused to send because this "
                "connection cannot send mail. Reconnect Gmail in Settings, then turn "
                "autopilot back on."
            ),
        )

    async def still_unread(*args, **kwargs):
        return False

    async def no_duplicate(*args, **kwargs):
        return None

    service = AIEmailAssistantService()
    with patch(
        "app.ai_email_assistant.services.assistant_service.resolve_openai_api_key",
        return_value="sk-test",
    ), patch.object(
        service, "_skip_if_no_longer_unread_in_gmail", still_unread
    ), patch.object(
        service, "_duplicate_skip_reason", no_duplicate
    ), patch.object(service, "generate_and_maybe_send", fake_generate):
        with pytest.raises(OpenAIServiceError):
            asyncio.run(
                service.process_pending_replies(db, user, settings_row, store_id=store.id)
            )

    assert seen == [first.id]
    assert db.get(AIEmailAssistantSettings, settings_id).automation_enabled is False
    db.close()


def test_failed_draft_is_resent_on_the_next_run():
    factory = _factory()
    db = factory()
    user, store = _user_store(db)
    account = GmailAccount(
        owner_id=user.id,
        email="store@luxory.com",
        display_name="Luxory",
        status="connected",
    )
    db.add(account)
    db.flush()
    email = _inbox(
        db,
        user,
        store,
        account,
        subject="Where is my order?",
        thread="t-draft",
        received_at=datetime.now(UTC),
        status=InboxEmailStatus.DRAFT_PENDING.value,
    )
    db.add(
        AIEmailReply(
            inbox_email_id=email.id,
            user_id=user.id,
            generated_body="Your order has shipped.",
            status="draft",
            model_used="gpt-4o-mini",
            error_message="Failed to send via Gmail API",
        )
    )
    settings_id = _settings(db, user, store, automation_enabled=True, auto_send_enabled=True)
    settings_row = db.get(AIEmailAssistantSettings, settings_id)
    seen: list[str] = []

    async def fake_generate(db, user, inbox_email_id, *, store_id=None):
        seen.append(inbox_email_id)
        return None

    async def already_read(*args, **kwargs):
        raise AssertionError("a failed draft must be retried even if Gmail already marked it read")

    service = AIEmailAssistantService()
    with patch(
        "app.ai_email_assistant.services.assistant_service.resolve_openai_api_key",
        return_value="sk-test",
    ), patch.object(
        service, "_skip_if_no_longer_unread_in_gmail", already_read
    ), patch.object(service, "generate_and_maybe_send", fake_generate):
        processed = asyncio.run(
            service.process_pending_replies(db, user, settings_row, store_id=store.id)
        )

    assert seen == [email.id]
    assert processed == 1
    db.close()
