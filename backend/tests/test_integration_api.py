from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import (
    AIEmailReply,
    AIReplyStatus,
    InboxEmail,
    InboxEmailStatus,
    MetaCapiEventLog,
    MetaCapiEventStatus,
    OrderTracking,
    Store,
    User,
)
from app.db.session import Base, get_db
from app.routes import integration

KEY = "k" * 40
OWNER = SimpleNamespace(id="u1", email="owner@example.com", is_active=True, is_verified=True)
STORE = SimpleNamespace(
    id="s1",
    name="Luxory",
    shop_domain="luxory.myshopify.com",
    status="connected",
    plan="Basic",
    timezone="America/Toronto",
    currency="CAD",
)


class FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class FakeDb:
    def __init__(self, user=OWNER, stores=(STORE,)):
        self.user = user
        self.stores = list(stores)

    def scalar(self, _query):
        return self.user

    def scalars(self, _query):
        return FakeScalars(self.stores)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "integration_api_key", KEY)
    monkeypatch.setattr(settings, "integration_owner_email", OWNER.email)
    app = FastAPI()
    app.include_router(integration.router, prefix="/api/v1/integration")
    db = FakeDb()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db


def auth(key=KEY):
    return {"Authorization": f"Bearer {key}"}


def test_off_without_a_key(client, monkeypatch):
    http, _ = client
    monkeypatch.setattr(settings, "integration_api_key", "")
    assert http.get("/api/v1/integration/stores", headers=auth()).status_code == 503


def test_rejects_missing_or_wrong_key(client):
    http, _ = client
    assert http.get("/api/v1/integration/stores").status_code == 401
    assert http.get("/api/v1/integration/stores", headers=auth("x" * 40)).status_code == 401


def test_needs_a_verified_owner(client):
    http, db = client
    db.user = SimpleNamespace(**{**vars(OWNER), "is_verified": False})
    assert http.get("/api/v1/integration/stores", headers=auth()).status_code == 503


def test_lists_owner_stores_without_secrets(client):
    http, _ = client
    body = http.get("/api/v1/integration/stores", headers=auth()).json()
    assert body["stores"][0]["name"] == "Luxory"
    assert "access_token_encrypted" not in body["stores"][0]


def test_sales_maps_periods_and_trims_the_dashboard(client, monkeypatch):
    http, _ = client
    seen = []

    async def fake_dashboard(db, user, store_id, period="30d", **kwargs):
        seen.append((store_id, period, kwargs))
        return {
            "currency": "CAD",
            "date_range": {"since": "2026-10-05", "until": "2026-10-05"},
            "summary": {"revenue": 120.5, "orders": 3, "aov": 40.17, "cogs": 30, "stripe_balance": {"x": 1}},
            "connections": {"shopify": True},
        }

    monkeypatch.setattr(integration._analytics, "get_dashboard", fake_dashboard)
    body = http.get("/api/v1/integration/sales?period=yesterday", headers=auth()).json()
    assert seen == [("s1", "1d", {})]
    store = body["stores"][0]
    assert store["revenue"] == 120.5 and store["orders"] == 3
    assert "stripe_balance" not in store and "cogs" not in store
    assert store["window"]["meaning"] == "yesterday"

    http.get("/api/v1/integration/sales?period=today", headers=auth())
    _, period, kwargs = seen[-1]
    assert period == "custom" and kwargs["custom_since"] == kwargs["custom_until"]


def test_unknown_store_is_404(client):
    http, _ = client
    assert http.get("/api/v1/integration/sales?store=nope", headers=auth()).status_code == 404


def test_rejects_unknown_period(client):
    http, _ = client
    assert http.get("/api/v1/integration/sales?period=decade", headers=auth()).status_code == 422


def test_briefing_flags_what_needs_the_owner(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.now(UTC)
    user = User(email=OWNER.email, password_hash="x", full_name="Owner", is_verified=True)
    db.add(user)
    db.flush()
    store = Store(owner_id=user.id, shop_domain="luxory.myshopify.com", name="Luxory", status="connected", timezone="America/Toronto", currency="CAD")
    db.add(store)
    db.flush()

    def inbox(n, status, received_at, **extra):
        row = InboxEmail(
            user_id=user.id,
            store_id=store.id,
            gmail_account_id="g1",
            gmail_message_id=f"m{n}",
            thread_id=f"t{n}",
            sender="Customer <c@example.com>",
            sender_email="c@example.com",
            subject=f"Subject {n}",
            status=status,
            received_at=received_at,
            **extra,
        )
        db.add(row)
        return row

    inbox(1, InboxEmailStatus.MANUAL_REVIEW.value, now - timedelta(days=2), skip_reason="Disputed charge")
    inbox(2, InboxEmailStatus.DRAFT_PENDING.value, now - timedelta(hours=1))
    failed = inbox(3, InboxEmailStatus.NEW.value, now - timedelta(hours=2))
    db.flush()
    db.add(AIEmailReply(inbox_email_id=failed.id, user_id=user.id, status=AIReplyStatus.FAILED.value, created_at=now - timedelta(hours=1)))
    db.add(MetaCapiEventLog(store_id=store.id, shopify_order_id="1", status=MetaCapiEventStatus.FAILED.value, created_at=now - timedelta(hours=3)))
    db.add(
        OrderTracking(
            store_id=store.id,
            order_number_display="#1001",
            order_number_normalized="1001",
            customer_email="c@example.com",
            status="pending",
            order_placed_at=now - timedelta(days=6),
        )
    )
    db.commit()

    async def fake_dashboard(*args, **kwargs):
        return {"currency": "CAD", "summary": {"revenue": 200.0, "orders": 4, "net_profit": -15.0}, "insights": []}

    async def fake_ads(*args, **kwargs):
        return {"currency": "CAD", "meta_configured": True, "summary": {"spend": 100.0, "platform_roas": 0.8}, "alerts": []}

    monkeypatch.setattr(integration._analytics, "get_dashboard", fake_dashboard)
    monkeypatch.setattr(integration._ads, "get_dashboard", fake_ads)
    monkeypatch.setattr(settings, "integration_api_key", KEY)
    monkeypatch.setattr(settings, "integration_owner_email", OWNER.email)
    app = FastAPI()
    app.include_router(integration.router, prefix="/api/v1/integration")
    app.dependency_overrides[get_db] = lambda: db

    body = TestClient(app).get("/api/v1/integration/briefing", headers=auth()).json()
    report = body["stores"][0]
    titles = [p["title"] for p in report["problems"]]
    assert "1 email waiting for your manual review" in titles
    assert "1 AI email reply failed to send this week" in titles
    assert "1 AI draft waiting for approval" in titles
    assert "1 purchase event failed to reach Meta in 24h" in titles
    assert "1 order still without tracking after 4 days" in titles
    assert "Losing money today so far" in titles
    assert "Ads are returning less than they cost" in titles
    assert report["problems"][0]["severity"] == "high"
    email = next(s for s in report["sections"] if s["title"] == "AI email assistant")
    assert email["items"][0]["title"] == "Subject 1"
    assert "c@example.com" not in str(body)
