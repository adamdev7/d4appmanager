import hashlib
import hmac
import base64
import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings


class ShopifyClient:
    def __init__(self, shop_domain: str, access_token: str | None = None) -> None:
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "").strip("/")
        if not self.shop_domain.endswith(".myshopify.com"):
            if "." not in self.shop_domain:
                self.shop_domain = f"{self.shop_domain}.myshopify.com"
        self.access_token = access_token
        self.api_version = settings.shopify_api_version

    @property
    def admin_api_base(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}"

    def build_install_url(self, state: str) -> str:
        if not settings.shopify_client_id:
            raise ValueError("SHOPIFY_CLIENT_ID is not configured")
        params = {
            "client_id": settings.shopify_client_id,
            "scope": settings.shopify_scopes,
            "redirect_uri": settings.shopify_redirect_uri,
            "state": state,
        }
        return f"https://{self.shop_domain}/admin/oauth/authorize?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> dict:
        if not settings.shopify_client_id or not settings.shopify_client_secret:
            raise ValueError("Shopify OAuth credentials are not configured")
        url = f"https://{self.shop_domain}/admin/oauth/access_token"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                json={
                    "client_id": settings.shopify_client_id,
                    "client_secret": settings.shopify_client_secret,
                    "code": code,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def get_shop(self) -> dict:
        if not self.access_token:
            raise ValueError("No access token")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.admin_api_base}/shop.json",
                headers={"X-Shopify-Access-Token": self.access_token},
            )
            resp.raise_for_status()
            return resp.json()["shop"]

    async def register_webhook(self, topic: str, address: str) -> dict:
        if not self.access_token:
            raise ValueError("No access token")
        payload = {"webhook": {"topic": topic, "address": address, "format": "json"}}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.admin_api_base}/webhooks.json",
                headers={"X-Shopify-Access-Token": self.access_token},
                json=payload,
            )
            resp.raise_for_status()
            return resp.json()["webhook"]

    @staticmethod
    def verify_webhook_hmac(body: bytes, hmac_header: str) -> bool:
        if not settings.shopify_client_secret:
            return False
        digest = hmac.new(
            settings.shopify_client_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).digest()
        computed = base64.b64encode(digest).decode()
        return hmac.compare_digest(computed, hmac_header)

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)
