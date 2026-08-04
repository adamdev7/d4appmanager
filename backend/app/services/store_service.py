import json
import logging

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import encrypt_value
from app.db.models import Store, StoreStatus, User
from app.integrations.shopify.client import ShopifyClient
from app.email_automation.default_templates import seed_store_automation_defaults
from app.email_automation.webhook_topics import AUTOMATION_WEBHOOK_TOPICS
from app.models.store import StoreSettingsUpdate
from app.services.oauth_state_service import OAuthStateService

logger = logging.getLogger(__name__)


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

    def begin_shopify_install(self, db: Session, user: User, shop: str) -> str:
        if not settings.shopify_client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Shopify is not configured. Set SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET in .env",
            )
        shop_domain = shop.strip().lower()
        client = ShopifyClient(shop_domain)
        state = OAuthStateService.create(db, "shopify", user.id, {"shop": client.shop_domain})
        # Shopify OAuth redirect is always the production host unless a tunnel is opted in
        redirect = settings.shopify_redirect_uri
        if "appmanager.store" not in redirect and not settings.shopify_allow_dev_tunnel:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Shopify OAuth is misconfigured: redirect must use https://appmanager.store",
            )
        return client.build_install_url(state)

    async def complete_shopify_oauth(
        self, db: Session, shop: str, code: str, state: str
    ) -> tuple[User, Store]:
        oauth = OAuthStateService.consume(db, state, "shopify")
        if not oauth:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

        user = db.get(User, oauth.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

        client = ShopifyClient(shop)
        token_data = await client.exchange_code_for_token(code)
        access_token = token_data["access_token"]
        client.access_token = access_token

        shop_data = await client.get_shop()
        shop_domain = shop_data.get("myshopify_domain") or client.shop_domain

        store = db.scalar(select(Store).where(Store.shop_domain == shop_domain))
        if store and store.owner_id != user.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This store is already connected to another account",
            )

        if not store:
            store = Store(owner_id=user.id, name=shop_data.get("name", shop_domain), shop_domain=shop_domain)
            db.add(store)

        store.name = shop_data.get("name", store.name)
        store.access_token_encrypted = encrypt_value(access_token)
        store.status = StoreStatus.CONNECTED.value
        store.plan = shop_data.get("plan_display_name", "Shopify")
        store.timezone = shop_data.get("iana_timezone", "UTC")
        store.currency = str(shop_data.get("currency") or "USD").upper()
        db.commit()
        db.refresh(store)

        webhook_url = (
            f"{settings.shopify_webhook_base}{settings.api_prefix}/webhooks/shopify"
        )
        for topic in AUTOMATION_WEBHOOK_TOPICS:
            try:
                await client.register_webhook(topic, webhook_url)
            except Exception:
                pass  # may already exist

        seed_store_automation_defaults(db, store.id)

        return user, store

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
