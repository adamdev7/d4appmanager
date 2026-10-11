import asyncio
import hashlib
import hmac
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import get_verified_user
from app.config import settings
from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import ShopifyPendingInstall, Store, User
from app.db.session import Base, get_db
from app.integrations.shopify import client as shopify_client
from app.integrations.shopify.client import (
    ShopifyClient,
    nest_bulk_rows,
    order_to_rest,
    product_to_rest,
)
from app.routes import stores
from app.services import store_service
from app.services.store_service import scopes_cover

SECRET = "test-shopify-secret"
SHOP = "luxory.myshopify.com"


def signed(params: dict[str, str]) -> dict[str, str]:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    digest = hmac.new(SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()
    return {**params, "hmac": digest}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "shopify_client_id", "client-123")
    monkeypatch.setattr(settings, "shopify_client_secret", SECRET)
    monkeypatch.setattr(settings, "shopify_public_url", "https://appmanager.store")
    monkeypatch.setattr(settings, "frontend_url", "https://appmanager.store")
    monkeypatch.setattr(store_service, "seed_store_automation_defaults", lambda db, store_id: None)

    async def fake_exchange(self, code):
        return {
            "access_token": f"token-{code}",
            "scope": settings.shopify_scopes,
            "expires_in": 3600,
            "refresh_token": f"refresh-{code}",
            "refresh_token_expires_in": 7776000,
        }

    async def fake_shop(self):
        return {
            "name": "Luxory",
            "myshopify_domain": self.shop_domain,
            "currency": "cad",
            "iana_timezone": "America/Toronto",
            "plan_display_name": "Basic",
        }

    webhooks: list[str] = []

    async def fake_webhook(self, topic, address):
        webhooks.append(topic)
        return {}

    monkeypatch.setattr(ShopifyClient, "exchange_code_for_token", fake_exchange)
    monkeypatch.setattr(ShopifyClient, "get_shop", fake_shop)
    monkeypatch.setattr(ShopifyClient, "register_webhook", fake_webhook)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(email="owner@example.com", password_hash="x", full_name="Owner", is_verified=True)
    db.add(user)
    db.commit()

    app = FastAPI()
    app.include_router(stores.router, prefix="/api/v1/stores")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_verified_user] = lambda: user
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    return client, db, user, webhooks


def launch_params(shop: str = SHOP) -> dict[str, str]:
    return signed({"shop": shop, "timestamp": str(int(time.time())), "host": "YWRtaW4"})


def test_launch_for_new_shop_redirects_straight_to_oauth(env):
    client, *_ = env
    resp = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    assert resp.status_code == 302
    location = urlparse(resp.headers["location"])
    assert location.netloc == SHOP and location.path == "/admin/oauth/authorize"
    query = parse_qs(location.query)
    assert query["client_id"] == ["client-123"]
    assert query["redirect_uri"] == ["https://appmanager.store/api/v1/stores/shopify/callback"]
    assert client.cookies.get(store_service.SHOPIFY_STATE_COOKIE) == query["state"][0]


def test_launch_rejects_bad_signature(env):
    client, *_ = env
    params = launch_params()
    params["hmac"] = "0" * 64
    assert client.get("/api/v1/stores/shopify/launch", params=params).status_code == 400


def test_launch_rejects_non_shopify_domain(env):
    client, *_ = env
    resp = client.get("/api/v1/stores/shopify/launch", params=launch_params("evil.example.com"))
    assert resp.status_code == 400


def test_launch_for_connected_shop_opens_dashboard(env):
    client, db, user, _ = env
    db.add(
        Store(
            owner_id=user.id,
            shop_domain=SHOP,
            name="Luxory",
            status="connected",
            access_token_encrypted=encrypt_value("t"),
            granted_scopes=settings.shopify_scopes,
        )
    )
    db.commit()
    resp = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    assert resp.status_code == 302
    assert resp.headers["location"] == "https://appmanager.store/dashboard"


def test_launch_reauthorizes_when_new_scopes_are_missing(env):
    client, db, user, _ = env
    db.add(
        Store(
            owner_id=user.id,
            shop_domain=SHOP,
            name="Luxory",
            status="connected",
            access_token_encrypted=encrypt_value("t"),
            granted_scopes="read_orders",
        )
    )
    db.commit()
    resp = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    assert urlparse(resp.headers["location"]).path == "/admin/oauth/authorize"


def test_install_from_shopify_then_claim_attaches_store(env):
    client, db, user, webhooks = env
    launch = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    state = parse_qs(urlparse(launch.headers["location"]).query)["state"][0]

    callback = client.get(
        "/api/v1/stores/shopify/callback",
        params=signed({"shop": SHOP, "code": "abc", "state": state, "timestamp": str(int(time.time()))}),
    )
    assert callback.status_code == 302
    target = urlparse(callback.headers["location"])
    assert target.path == "/settings/stores"
    claim = parse_qs(target.query)["shopify_claim"][0]
    assert db.scalar(select(Store)) is None
    assert db.scalar(select(ShopifyPendingInstall)).shop_domain == SHOP

    resp = client.post("/api/v1/stores/shopify/claim", json={"claim": claim})
    assert resp.status_code == 200
    store = db.scalar(select(Store))
    assert store.owner_id == user.id
    assert store.status == "connected"
    assert decrypt_value(store.access_token_encrypted) == "token-abc"
    assert decrypt_value(store.refresh_token_encrypted) == "refresh-abc"
    assert store.currency == "CAD"
    assert "orders/create" in webhooks
    assert db.scalar(select(ShopifyPendingInstall)) is None

    again = client.post("/api/v1/stores/shopify/claim", json={"claim": claim})
    assert again.status_code == 400


def test_callback_without_matching_state_cookie_is_rejected(env):
    client, *_ = env
    launch = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    state = parse_qs(urlparse(launch.headers["location"]).query)["state"][0]
    client.cookies.clear()
    resp = client.get(
        "/api/v1/stores/shopify/callback",
        params=signed({"shop": SHOP, "code": "abc", "state": state, "timestamp": str(int(time.time()))}),
    )
    assert resp.status_code == 400


def test_callback_still_lands_in_app_when_shop_lookup_fails(env, monkeypatch):
    client, db, *_ = env

    async def broken_shop(self):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(ShopifyClient, "get_shop", broken_shop)
    launch = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    state = parse_qs(urlparse(launch.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/stores/shopify/callback",
        params=signed({"shop": SHOP, "code": "abc", "state": state, "timestamp": str(int(time.time()))}),
    )
    assert callback.status_code == 302
    assert "shopify_claim=" in callback.headers["location"]
    pending = db.scalar(select(ShopifyPendingInstall))
    assert pending.shop_domain == SHOP
    assert decrypt_value(pending.access_token_encrypted) == "token-abc"
    assert decrypt_value(pending.refresh_token_encrypted) == "refresh-abc"


def test_code_exchange_requests_expiring_offline_token(monkeypatch):
    sent: dict = {}

    async def fake_request(self, data):
        sent.update(data)
        return {}

    monkeypatch.setattr(ShopifyClient, "_token_request", fake_request)
    asyncio.run(ShopifyClient(SHOP).exchange_code_for_token("c"))
    assert sent == {"code": "c", "expiring": "1"}


def _mock_shopify_http(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )


def test_graphql_refreshes_expired_token_and_saves_it(env, monkeypatch):
    _, db, user, _ = env
    store = Store(
        owner_id=user.id,
        shop_domain=SHOP,
        name="Luxory",
        status="connected",
        access_token_encrypted=encrypt_value("old"),
        refresh_token_encrypted=encrypt_value("r1"),
    )
    db.add(store)
    db.commit()
    monkeypatch.setattr(store_service, "SessionLocal", sessionmaker(bind=db.get_bind()))

    async def fake_refresh(self, refresh_token):
        assert refresh_token == "r1"
        return {"access_token": "new", "refresh_token": "r2", "expires_in": 3600}

    monkeypatch.setattr(ShopifyClient, "refresh_access_token", fake_refresh)

    def handler(request):
        if request.headers["X-Shopify-Access-Token"] == "old":
            return httpx.Response(401, text='{"errors":"[API] Invalid API key or access token"}')
        return httpx.Response(200, json={"data": {"shop": {"name": "Luxory"}}})

    _mock_shopify_http(monkeypatch, handler)
    shopify = ShopifyClient(SHOP, "old")
    assert asyncio.run(shopify.graphql("{ shop { name } }")) == {"shop": {"name": "Luxory"}}
    assert shopify.access_token == "new"
    db.refresh(store)
    assert decrypt_value(store.access_token_encrypted) == "new"
    assert decrypt_value(store.refresh_token_encrypted) == "r2"


def test_graphql_error_includes_shopify_response_body(monkeypatch):
    def handler(request):
        return httpx.Response(403, text='{"errors":"[API] This action requires merchant approval"}')

    _mock_shopify_http(monkeypatch, handler)
    with pytest.raises(httpx.HTTPStatusError, match="HTTP 403.*requires merchant approval"):
        asyncio.run(ShopifyClient(SHOP, "t").graphql("{ shop { name } }"))


def test_reinstall_updates_existing_store_token(env):
    client, db, user, _ = env
    db.add(Store(owner_id=user.id, shop_domain=SHOP, name="Old", status="disconnected"))
    db.commit()
    launch = client.get("/api/v1/stores/shopify/launch", params=launch_params())
    state = parse_qs(urlparse(launch.headers["location"]).query)["state"][0]
    callback = client.get(
        "/api/v1/stores/shopify/callback",
        params=signed({"shop": SHOP, "code": "new", "state": state, "timestamp": str(int(time.time()))}),
    )
    assert "connected=1" in callback.headers["location"]
    store = db.scalar(select(Store))
    db.refresh(store)
    assert store.status == "connected"
    assert decrypt_value(store.access_token_encrypted) == "token-new"
    assert store.name == "Luxory"


def test_reauthorize_uses_the_stores_own_domain(env):
    client, db, user, _ = env
    store = Store(owner_id=user.id, shop_domain=SHOP, name="Luxory", status="disconnected")
    db.add(store)
    db.commit()
    resp = client.post(f"/api/v1/stores/{store.id}/shopify/reauthorize")
    assert urlparse(resp.json()["authorize_url"]).netloc == SHOP


def test_scopes_cover_treats_write_as_read():
    assert scopes_cover("write_orders,read_products", "read_orders,read_products")
    assert not scopes_cover("read_orders", "read_orders,read_inventory")
    assert not scopes_cover(None, "read_orders")


def test_order_to_rest_matches_webhook_shape():
    node = {
        "id": "gid://shopify/Order/1001",
        "legacyResourceId": "1001",
        "name": "#1042",
        "number": 42,
        "email": "a@b.com",
        "createdAt": "2026-10-01T10:00:00Z",
        "displayFinancialStatus": "PARTIALLY_REFUNDED",
        "displayFulfillmentStatus": "PARTIALLY_FULFILLED",
        "currencyCode": "CAD",
        "presentmentCurrencyCode": "USD",
        "tags": ["vip", "wholesale"],
        "clientIp": "1.2.3.4",
        "customAttributes": [{"key": "_fbp", "value": "fb.1.2"}],
        "totalPriceSet": {
            "shopMoney": {"amount": "50.00", "currencyCode": "CAD"},
            "presentmentMoney": {"amount": "37.00", "currencyCode": "USD"},
        },
        "totalRefundedSet": {"shopMoney": {"amount": "5.00"}},
        "customer": {
            "legacyResourceId": "77",
            "firstName": "Ada",
            "defaultEmailAddress": {"emailAddress": "a@b.com"},
        },
        "customerJourneySummary": {"lastVisit": {"landingPage": "https://x/?fbclid=1"}},
        "fulfillments": [
            {
                "legacyResourceId": "9",
                "status": "SUCCESS",
                "displayStatus": "IN_TRANSIT",
                "trackingInfo": [{"number": "TRK1", "company": "UPS", "url": "https://ups/TRK1"}],
            }
        ],
        "shippingLines": {"nodes": [{"title": "Standard", "originalPriceSet": {"shopMoney": {"amount": "7.50"}}}]},
        "lineItems": {
            "nodes": [
                {
                    "id": "gid://shopify/LineItem/5",
                    "title": "Bracelet",
                    "quantity": 2,
                    "variant": {"id": "gid://shopify/ProductVariant/12"},
                    "product": {"id": "gid://shopify/Product/34"},
                    "originalUnitPriceSet": {"shopMoney": {"amount": "20.00", "currencyCode": "CAD"}},
                    "image": {"url": "https://cdn/img.png"},
                }
            ]
        },
    }
    order = order_to_rest(node)
    assert order["id"] == 1001 and order["order_number"] == 42
    assert order["financial_status"] == "partially_refunded"
    assert order["fulfillment_status"] == "partial"
    assert order["total_price"] == "50.00"
    assert order["total_price_set"]["presentment_money"] == {"amount": "37.00", "currency_code": "USD"}
    assert order["tags"] == "vip, wholesale"
    assert order["note_attributes"] == [{"name": "_fbp", "value": "fb.1.2"}]
    assert order["client_details"] == {"browser_ip": "1.2.3.4"}
    assert order["landing_site"] == "https://x/?fbclid=1"
    assert order["customer"]["id"] == 77 and order["customer"]["email"] == "a@b.com"
    assert order["refunds"][0]["transactions"][0] == {"kind": "refund", "status": "success", "amount": "5.00"}
    assert order["shipping_lines"] == [{"title": "Standard", "price": "7.50"}]
    item = order["line_items"][0]
    assert (item["product_id"], item["variant_id"], item["price"]) == (34, 12, "20.00")
    assert item["image"] == {"src": "https://cdn/img.png"}
    fulfillment = order["fulfillments"][0]
    assert fulfillment["id"] == 9 and fulfillment["status"] == "success"
    assert fulfillment["shipment_status"] == "in_transit"
    assert fulfillment["tracking_number"] == "TRK1" and fulfillment["tracking_company"] == "UPS"


def test_product_to_rest_keeps_rest_fields():
    product = product_to_rest(
        {
            "legacyResourceId": "34",
            "title": "Bracelet",
            "handle": "bracelet",
            "status": "ACTIVE",
            "tags": ["gold"],
            "media": {"nodes": [{"id": "gid://shopify/MediaImage/8", "image": {"url": "https://cdn/p.png"}}, {}]},
            "variants": {
                "nodes": [
                    {"legacyResourceId": "13", "position": 2, "price": "25.00", "inventoryItem": {"tracked": False}},
                    {"legacyResourceId": "12", "position": 1, "price": "20.00", "inventoryQuantity": 4, "inventoryItem": {"tracked": True}},
                ]
            },
        }
    )
    assert product["id"] == 34 and product["status"] == "active" and product["tags"] == "gold"
    assert product["image"]["src"] == "https://cdn/p.png" and len(product["images"]) == 1
    assert [v["id"] for v in product["variants"]] == [12, 13]
    assert product["variants"][0]["inventory_management"] == "shopify"
    assert product["variants"][1]["inventory_management"] is None


def test_nest_bulk_rows_rebuilds_connections():
    rows = [
        {"id": "gid://shopify/Order/1", "name": "#1"},
        {"__typename": "LineItem", "id": "gid://shopify/LineItem/10", "__parentId": "gid://shopify/Order/1"},
        {"__typename": "ShippingLine", "id": None, "__parentId": "gid://shopify/Order/1"},
        {"id": "gid://shopify/LineItem/11", "__parentId": "gid://shopify/Order/1"},
        {"id": "gid://shopify/Order/2", "name": "#2"},
        {"__parentId": "gid://shopify/Order/2"},
    ]
    roots = nest_bulk_rows(rows, shopify_client._BULK_ORDER_CHILDREN)
    assert [r["name"] for r in roots] == ["#1", "#2"]
    assert len(roots[0]["lineItems"]["nodes"]) == 2
    assert len(roots[0]["shippingLines"]["nodes"]) == 1
    assert "lineItems" not in roots[1]


def test_orders_search_builds_shopify_query_syntax():
    search = ShopifyClient._orders_search(
        created_at_min="2026-01-01T00:00:00Z",
        financial_status="paid",
        name='#10"42',
        ids="1,2",
    )
    assert search == (
        "created_at:>='2026-01-01T00:00:00Z' financial_status:paid name:\"#1042\" (id:1 OR id:2)"
    )
