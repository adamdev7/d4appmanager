import base64
import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.db.models import OrderTracking, Store, User, WebhookLog
from app.db.session import Base, get_db
from app.routes import webhooks

SECRET = "test-shopify-secret"
SHOP = "luxory.myshopify.com"


def post(client, topic: str, payload: dict, *, secret: str = SECRET):
    body = json.dumps(payload).encode()
    digest = base64.b64encode(hmac.new(secret.encode(), body, hashlib.sha256).digest()).decode()
    return client.post(
        "/api/v1/webhooks/shopify",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Shopify-Topic": topic,
            "X-Shopify-Shop-Domain": SHOP,
            "X-Shopify-Hmac-Sha256": digest,
        },
    )


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "shopify_client_secret", SECRET)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="owner@example.com", password_hash="x", full_name="Owner", is_verified=True)
    db.add(user)
    db.flush()
    store = Store(owner_id=user.id, shop_domain=SHOP, name="Luxory", status="connected")
    db.add(store)
    db.flush()
    for number, email, order_id in (("1001", "ada@example.com", "11"), ("1002", "bob@example.com", "22")):
        db.add(
            OrderTracking(
                store_id=store.id,
                shopify_order_id=order_id,
                order_number_display=f"#{number}",
                order_number_normalized=number,
                customer_email=email,
                status="pending",
                timeline_json="[]",
            )
        )
    db.commit()

    app = FastAPI()
    app.include_router(webhooks.router, prefix="/api/v1/webhooks")
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app), db, store


@pytest.mark.parametrize("topic", ["customers/data_request", "customers/redact", "shop/redact"])
def test_compliance_webhooks_reject_bad_signature(env, topic):
    client, *_ = env
    resp = post(client, topic, {"shop_domain": SHOP}, secret="wrong")
    assert resp.status_code == 401


def test_data_request_is_acknowledged_without_storing_pii(env):
    client, db, _ = env
    resp = post(
        client,
        "customers/data_request",
        {"shop_domain": SHOP, "customer": {"email": "ada@example.com"}, "data_request": {"id": 9}},
    )
    assert resp.status_code == 200
    log = db.scalar(select(WebhookLog).where(WebhookLog.topic == "customers/data_request"))
    assert log is not None and log.payload_preview == ""


def test_customer_redact_removes_only_that_customer(env):
    client, db, _ = env
    resp = post(
        client,
        "customers/redact",
        {"shop_domain": SHOP, "customer": {"id": 5, "email": "ADA@example.com"}, "orders_to_redact": [11]},
    )
    assert resp.status_code == 200
    remaining = [row.customer_email for row in db.scalars(select(OrderTracking)).all()]
    assert remaining == ["bob@example.com"]


def test_shop_redact_removes_the_store(env):
    client, db, _ = env
    resp = post(client, "shop/redact", {"shop_id": 1, "shop_domain": SHOP})
    assert resp.status_code == 200
    db.expire_all()
    assert db.scalar(select(Store).where(Store.shop_domain == SHOP)) is None


def test_compliance_webhook_for_unknown_shop_still_returns_ok(env):
    client, *_ = env
    body = {"shop_domain": "other.myshopify.com", "customer": {"email": "x@example.com"}}
    resp = post(client, "customers/redact", body)
    assert resp.status_code == 200
