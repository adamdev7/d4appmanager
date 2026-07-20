import hashlib
import hmac
import base64
import re
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

    async def list_orders(
        self,
        *,
        limit: int = 50,
        status: str = "any",
        since_id: str | None = None,
        created_at_min: str | None = None,
        created_at_max: str | None = None,
        financial_status: str | None = None,
    ) -> list[dict]:
        """Fetch recent orders from this Shopify store (Admin REST)."""
        if not self.access_token:
            raise ValueError("No access token")
        params: dict[str, str | int] = {
            "status": status,
            "limit": min(max(limit, 1), 250),
        }
        if since_id:
            params["since_id"] = since_id
        if created_at_min:
            params["created_at_min"] = created_at_min
        if created_at_max:
            params["created_at_max"] = created_at_max
        if financial_status:
            params["financial_status"] = financial_status
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{self.admin_api_base}/orders.json",
                params=params,
                headers={"X-Shopify-Access-Token": self.access_token},
            )
            resp.raise_for_status()
            return list(resp.json().get("orders") or [])

    async def list_all_orders_in_range(
        self,
        *,
        created_at_min: str | None = None,
        created_at_max: str | None = None,
        financial_status: str = "any",
        max_pages: int = 20,
    ) -> list[dict]:
        """Paginate through orders in a date range (up to max_pages * 250)."""
        all_orders: list[dict] = []
        since_id: str | None = None
        for _ in range(max_pages):
            batch = await self.list_orders(
                limit=250,
                status="any",
                since_id=since_id,
                created_at_min=created_at_min,
                created_at_max=created_at_max,
                financial_status=financial_status,
            )
            if not batch:
                break
            all_orders.extend(batch)
            since_id = str(batch[-1]["id"])
            if len(batch) < 250:
                break
        return all_orders

    async def list_products(self, *, limit: int = 250) -> list[dict]:
        """Fetch products with variants from Shopify."""
        if not self.access_token:
            raise ValueError("No access token")
        all_products: list[dict] = []
        page_info: str | None = None
        async with httpx.AsyncClient(timeout=45) as client:
            for _ in range(10):
                params: dict[str, str | int] = {"limit": min(limit, 250)}
                if page_info:
                    params = {"limit": min(limit, 250), "page_info": page_info}
                resp = await client.get(
                    f"{self.admin_api_base}/products.json",
                    params=params,
                    headers={"X-Shopify-Access-Token": self.access_token},
                )
                resp.raise_for_status()
                batch = list(resp.json().get("products") or [])
                all_products.extend(batch)
                link = resp.headers.get("Link", "")
                if 'rel="next"' not in link:
                    break
                next_part = [p for p in link.split(",") if 'rel="next"' in p]
                if not next_part:
                    break
                match = re.search(r"page_info=([^>&]+)", next_part[0])
                page_info = match.group(1) if match else None
                if not page_info:
                    break
        return all_products

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
