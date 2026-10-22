import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import ShopifyPendingInstall, Store, StoreStatus, User
from app.db.session import SessionLocal
from app.integrations.shopify.client import ShopifyClient
from app.integrations.shopify.credentials import (
    PRIVATE,
    PUBLIC,
    credentials_for_query,
    credentials_for_store,
    private_account_emails,
    user_may_use_private_app,
)
from app.email_automation.default_templates import seed_store_automation_defaults
from app.email_automation.webhook_topics import AUTOMATION_WEBHOOK_TOPICS
from app.models.store import StoreSettingsUpdate
from app.services.oauth_state_service import OAuthStateService

logger = logging.getLogger(__name__)

SHOPIFY_STATE_COOKIE = "shopify_oauth_state"
LAUNCH_STATE_TTL_SECONDS = 600
_LAUNCH_MAX_AGE_SECONDS = 24 * 3600
_CLAIM_TTL = timedelta(hours=1)


def _scope_set(raw: str | None) -> set[str]:
    return {s.strip() for s in (raw or "").split(",") if s.strip()}


def scopes_cover(granted: str | None, required: str | None) -> bool:
    """True when ``granted`` includes every required scope (write_x implies read_x)."""
    have = _scope_set(granted)
    for scope in _scope_set(required):
        if scope in have:
            continue
        if scope.startswith("read_") and f"write_{scope[5:]}" in have:
            continue
        return False
    return True


def _sign(message: str) -> str:
    return hmac.new(
        settings.shopify_client_secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def make_launch_state(shop: str) -> str:
    nonce = secrets.token_urlsafe(16)
    expires = int(time.time()) + LAUNCH_STATE_TTL_SECONDS
    return f"{nonce}.{expires}.{_sign(f'launch|{shop}|{nonce}|{expires}')}"


def verify_launch_state(state: str, shop: str) -> bool:
    parts = (state or "").split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return False
    nonce, expires, signature = parts
    if int(expires) < time.time():
        return False
    return hmac.compare_digest(_sign(f"launch|{shop}|{nonce}|{expires}"), signature)


def _claim_hash(claim: str) -> str:
    return hashlib.sha256(claim.encode("utf-8")).hexdigest()


async def renew_shopify_token(shop_domain: str, stale_token: str) -> str | None:
    """Replace an expired (or legacy non-expiring) offline token with a fresh one and save it."""
    db = SessionLocal()
    try:
        store = db.scalar(select(Store).where(Store.shop_domain == shop_domain))
        if not store or not store.access_token_encrypted:
            return None
        current = decrypt_value(store.access_token_encrypted)
        if current != stale_token:
            return current
        client = ShopifyClient(shop_domain, credentials=credentials_for_store(store))
        if store.refresh_token_encrypted:
            token_data = await client.refresh_access_token(decrypt_value(store.refresh_token_encrypted))
        else:
            token_data = await client.migrate_to_expiring_token(current)
        store.access_token_encrypted = encrypt_value(token_data["access_token"])
        if token_data.get("refresh_token"):
            store.refresh_token_encrypted = encrypt_value(token_data["refresh_token"])
        db.commit()
        return token_data["access_token"]
    except Exception:
        db.rollback()
        logger.exception("Could not renew Shopify access token for %s", shop_domain)
        return None
    finally:
        db.close()


class StoreService:
    def list_stores(self, db: Session, user: User) -> list[dict]:
        stores = db.scalars(select(Store).where(Store.owner_id == user.id).order_by(Store.name)).all()
        return [self._serialize(s) for s in stores]

    def get_store(self, db: Session, user: User, store_id: str) -> dict | None:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            return None
        return self._serialize(store)

    def _serialize(self, store: Store) -> dict:
        return {
            "id": store.id,
            "name": store.name,
            "domain": store.shop_domain,
            "status": store.status,
            "plan": store.plan,
            "timezone": store.timezone,
            "currency": store.currency,
        }

    @staticmethod
    def shopify_install_link(user: User | None = None) -> str | None:
        """Allowlisted accounts get the private app link. Everyone else, including review, stays public."""
        if user and user_may_use_private_app(user):
            private_url = (settings.shopify_private_install_url or "").strip()
            if private_url:
                return private_url
        return settings.shopify_install_url.strip() or None

    @staticmethod
    def _private_app_unavailable() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The private Shopify app is not assigned to an account",
        )

    @staticmethod
    def _private_account_required() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This Shopify app is limited to a specific SkyScale Manager account. Sign in with that account and try again.",
        )

    @staticmethod
    def _keep_private_token(store: Store | None) -> bool:
        """A connected private-app store stays on that token if the public app is opened."""
        return bool(
            store
            and store.shopify_app == PRIVATE
            and store.access_token_encrypted
            and store.status == StoreStatus.CONNECTED.value
        )

    def _reject_private_app_for_other_account(self, db: Session, user: User | None, store: Store | None) -> None:
        if not private_account_emails():
            raise self._private_app_unavailable()
        if user is not None and not user_may_use_private_app(user):
            raise self._private_account_required()
        if store is None:
            return
        owner = db.get(User, store.owner_id)
        if not owner or not user_may_use_private_app(owner):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This store is already connected to another account",
            )

    @staticmethod
    def _require_shopify_configured() -> None:
        if not settings.shopify_client_id or not settings.shopify_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shopify is not configured. Set SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET in .env",
            )
        # Shopify OAuth redirect is always the production host unless a tunnel is opted in
        if "appmanager.store" not in settings.shopify_redirect_uri and not settings.shopify_allow_dev_tunnel:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Shopify OAuth is misconfigured: redirect must use https://appmanager.store",
            )

    def begin_shopify_reauthorize(self, db: Session, user: User, store_id: str) -> str:
        """OAuth URL to re-grant access for a store this account already owns."""
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Store not found")
        self._require_shopify_configured()
        creds = credentials_for_store(store)
        if creds and creds.kind == PRIVATE:
            self._reject_private_app_for_other_account(db, user, store)
        client = ShopifyClient(store.shop_domain, credentials=creds)
        state = OAuthStateService.create(db, "shopify", user.id, {"shop": client.shop_domain})
        return client.build_install_url(state)

    def handle_shopify_launch(self, db: Session, params: dict[str, str]) -> tuple[str, str | None]:
        """Entry point when Shopify opens the app (install or admin launch).

        Returns the redirect URL and, when OAuth is needed, the state to pin in a cookie.
        """
        self._require_shopify_configured()
        shop = str(params.get("shop") or "").strip().lower()
        timestamp = str(params.get("timestamp") or "")
        creds = credentials_for_query(params)
        if (
            not ShopifyClient.is_valid_shop_domain(shop)
            or creds is None
            or not timestamp.isdigit()
            or abs(time.time() - int(timestamp)) > _LAUNCH_MAX_AGE_SECONDS
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Shopify launch request")

        store = db.scalar(select(Store).where(Store.shop_domain == shop))
        if creds.kind == PRIVATE:
            self._reject_private_app_for_other_account(db, None, store)
        elif self._keep_private_token(store):
            return f"{settings.public_frontend_url}/dashboard", None
        same_app = (store.shopify_app or PUBLIC) == creds.kind if store else False
        if (
            store
            and same_app
            and store.access_token_encrypted
            and store.status == StoreStatus.CONNECTED.value
            and scopes_cover(store.granted_scopes, settings.shopify_scopes)
        ):
            return f"{settings.public_frontend_url}/dashboard", None

        state = make_launch_state(shop)
        return ShopifyClient(shop, credentials=creds).build_install_url(state), state

    async def complete_shopify_oauth(
        self, db: Session, params: dict[str, str], state_cookie: str | None
    ) -> str:
        """Finish OAuth and return where to send the browser next."""
        self._require_shopify_configured()
        shop = str(params.get("shop") or "").strip().lower()
        code = str(params.get("code") or "")
        state = str(params.get("state") or "")
        creds = credentials_for_query(params)
        if not ShopifyClient.is_valid_shop_domain(shop) or not code or not state or creds is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Shopify callback")

        user: User | None = None
        oauth = OAuthStateService.consume(db, state, "shopify")
        if oauth:
            extra = json.loads(oauth.extra or "{}")
            if extra.get("shop") and extra["shop"] != shop:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shop does not match this request")
            user = db.get(User, oauth.user_id)
            if not user:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")
        elif not (
            state_cookie
            and hmac.compare_digest(state_cookie, state)
            and verify_launch_state(state, shop)
        ):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

        client = ShopifyClient(shop, credentials=creds)
        store = db.scalar(select(Store).where(Store.shop_domain == shop))
        if creds.kind == PRIVATE:
            self._reject_private_app_for_other_account(db, user, store)
        elif self._keep_private_token(store):
            return f"{settings.public_frontend_url}/dashboard"
        token_data = await client.exchange_code_for_token(code)
        client.access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        scopes = str(token_data.get("scope") or "")
        try:
            shop_data = await client.get_shop()
        except Exception:
            # Keep the token and land the merchant in the app; shop details fill in on the next sync.
            logger.exception("Shopify shop lookup failed after OAuth for %s", client.shop_domain)
            shop_data = {"name": client.shop_domain, "myshopify_domain": client.shop_domain}
        shop_domain = shop_data.get("myshopify_domain") or client.shop_domain
        if shop_domain != shop:
            store = db.scalar(select(Store).where(Store.shop_domain == shop_domain))
            if creds.kind == PRIVATE:
                self._reject_private_app_for_other_account(db, user, store)
        frontend = settings.public_frontend_url

        if user is not None:
            if store and store.owner_id != user.id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="This store is already connected to another account",
                )
            store = await self._connect_store(
                db, client, user.id, store, shop_data, scopes, refresh_token, creds.kind
            )
            return f"{frontend}/settings/stores?connected=1&store_id={store.id}"

        if store:
            store = await self._connect_store(
                db, client, store.owner_id, store, shop_data, scopes, refresh_token, creds.kind
            )
            return f"{frontend}/settings/stores?connected=1&store_id={store.id}"

        claim = self._save_pending_install(
            db, shop_domain, client.access_token, refresh_token, scopes, shop_data, creds.kind
        )
        return f"{frontend}/settings/stores?shopify_claim={claim}"

    async def claim_shopify_install(self, db: Session, user: User, claim: str) -> dict:
        """Attach a shop that installed from Shopify to the signed-in account."""
        row = db.scalar(
            select(ShopifyPendingInstall).where(ShopifyPendingInstall.claim_token_hash == _claim_hash(claim))
        )
        expires = row.expires_at if row else None
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if not row or expires < datetime.now(UTC):
            if row:
                db.delete(row)
                db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This Shopify install link has expired. Open SkyScale Manager from your Shopify admin again.",
            )

        shop_domain = row.shop_domain
        store = db.scalar(select(Store).where(Store.shop_domain == shop_domain))
        if store and store.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This store is already connected to another account",
            )
        app_kind = row.shopify_app or PUBLIC
        if app_kind == PRIVATE and not user_may_use_private_app(user):
            raise self._private_account_required()
        client = ShopifyClient(shop_domain, decrypt_value(row.access_token_encrypted))
        refresh_token = decrypt_value(row.refresh_token_encrypted) if row.refresh_token_encrypted else None
        scopes = row.granted_scopes
        shop_data = json.loads(row.shop_json or "{}")
        db.delete(row)
        db.commit()

        store = await self._connect_store(
            db, client, user.id, store, shop_data, scopes, refresh_token, app_kind
        )
        return self._serialize(store)

    def _save_pending_install(
        self,
        db: Session,
        shop_domain: str,
        access_token: str,
        refresh_token: str | None,
        scopes: str,
        shop_data: dict,
        shopify_app: str = PUBLIC,
    ) -> str:
        claim = secrets.token_urlsafe(32)
        row = db.scalar(select(ShopifyPendingInstall).where(ShopifyPendingInstall.shop_domain == shop_domain))
        if not row:
            row = ShopifyPendingInstall(shop_domain=shop_domain)
            db.add(row)
        row.claim_token_hash = _claim_hash(claim)
        row.access_token_encrypted = encrypt_value(access_token)
        row.refresh_token_encrypted = encrypt_value(refresh_token) if refresh_token else None
        row.granted_scopes = scopes
        row.shopify_app = shopify_app
        row.shop_json = json.dumps(shop_data)
        row.expires_at = datetime.now(UTC) + _CLAIM_TTL
        db.commit()
        return claim

    async def _connect_store(
        self,
        db: Session,
        client: ShopifyClient,
        owner_id: str,
        store: Store | None,
        shop_data: dict,
        scopes: str | None,
        refresh_token: str | None = None,
        shopify_app: str = PUBLIC,
    ) -> Store:
        shop_domain = shop_data.get("myshopify_domain") or client.shop_domain
        if not store:
            store = Store(owner_id=owner_id, name=shop_data.get("name") or shop_domain, shop_domain=shop_domain)
            db.add(store)

        store.name = shop_data.get("name") or store.name
        store.access_token_encrypted = encrypt_value(client.access_token or "")
        store.refresh_token_encrypted = encrypt_value(refresh_token) if refresh_token else None
        store.granted_scopes = scopes or None
        store.shopify_app = shopify_app
        store.status = StoreStatus.CONNECTED.value
        store.plan = shop_data.get("plan_display_name") or "Shopify"
        store.timezone = shop_data.get("iana_timezone") or "UTC"
        store.currency = str(shop_data.get("currency") or "USD").upper()
        db.commit()
        db.refresh(store)

        webhook_url = f"{settings.shopify_webhook_base}{settings.api_prefix}/webhooks/shopify"
        for topic in AUTOMATION_WEBHOOK_TOPICS:
            try:
                await client.register_webhook(topic, webhook_url)
            except Exception:
                logger.debug("Webhook %s not registered for %s (may already exist)", topic, shop_domain, exc_info=True)

        seed_store_automation_defaults(db, store.id)
        return store

    def update_settings(
        self, db: Session, user: User, store_id: str, data: StoreSettingsUpdate
    ) -> dict | None:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            return None
        if data.name is not None:
            store.name = data.name
        if data.timezone is not None:
            store.timezone = data.timezone
        if data.currency is not None:
            store.currency = str(data.currency).strip().upper() or store.currency
        db.commit()
        db.refresh(store)
        return self._serialize(store)

    def disconnect_store(self, db: Session, user: User, store_id: str) -> bool:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            return False
        store.access_token_encrypted = None
        store.refresh_token_encrypted = None
        store.status = StoreStatus.DISCONNECTED.value
        db.commit()
        return True

    def delete_store(self, db: Session, user: User, store_id: str) -> bool:
        store = db.get(Store, store_id)
        if not store or store.owner_id != user.id:
            return False
        # Use a Core DELETE so PostgreSQL ON DELETE CASCADE/SET NULL runs.
        # ORM session.delete() was nulling email_templates.store_id (NOT NULL) and 500ing.
        try:
            result = db.execute(
                delete(Store).where(Store.id == store_id, Store.owner_id == user.id)
            )
            db.commit()
            return (result.rowcount or 0) > 0
        except Exception:
            db.rollback()
            logger.exception("Failed to delete store %s", store_id)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Could not delete store because related data could not be removed. Try again or contact support.",
            ) from None
