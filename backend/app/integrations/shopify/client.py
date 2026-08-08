import hashlib
import hmac
import base64
import logging
import re
import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


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
        name: str | None = None,
        query: str | None = None,
        ids: str | None = None,
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
        if name:
            params["name"] = name
        if query:
            params["query"] = query
        if ids:
            params["ids"] = ids
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{self.admin_api_base}/orders.json",
                params=params,
                headers={"X-Shopify-Access-Token": self.access_token},
            )
            resp.raise_for_status()
            return list(resp.json().get("orders") or [])

    async def find_orders_by_name(self, order_number: str, *, limit: int = 10) -> list[dict]:
        """
        Find orders by customer-facing name (#1042 / 1042).

        Shopify's REST `name=` filter is unreliable with the default `#` prefix
        (often returns unrelated recent orders or nothing). We try several
        query forms, always filter client-side for an exact name match, then
        fall back to GraphQL and a recent-order scan.
        """
        from app.tracking.payload_parser import normalize_order_number, order_name_matches

        bare = normalize_order_number(order_number)
        if not bare:
            return []
        hashed = f"#{bare}"

        async def _exact(orders: list[dict]) -> list[dict]:
            return [o for o in orders if order_name_matches(str(o.get("name") or ""), bare)]

        attempts: list[dict[str, str | int]] = [
            {"query": f"name:{hashed}", "status": "any", "limit": limit},
            {"query": f"name:{bare}", "status": "any", "limit": limit},
            {"name": hashed, "status": "any", "limit": limit},
            {"name": bare, "status": "any", "limit": limit},
        ]
        for params in attempts:
            try:
                kwargs = {k: v for k, v in params.items()}
                matched = await _exact(await self.list_orders(**kwargs))  # type: ignore[arg-type]
                if matched:
                    return matched
            except Exception:
                logger.debug(
                    "Shopify order name search attempt failed for %s params=%s",
                    self.shop_domain,
                    params,
                    exc_info=True,
                )

        gql_ids = await self._graphql_order_ids_by_name(hashed, bare)
        if gql_ids:
            found: list[dict] = []
            for oid in gql_ids[:limit]:
                try:
                    found.append(await self.get_order(oid))
                except Exception:
                    continue
            matched = await _exact(found)
            if matched:
                return matched

        try:
            recent = await self.list_orders(limit=100, status="any")
            matched = await _exact(recent)
            if matched:
                return matched
        except Exception:
            pass
        return []

    async def _graphql_order_ids_by_name(self, hashed: str, bare: str) -> list[str]:
        """Return Shopify numeric order ids matching the customer-facing name."""
        if not self.access_token:
            return []
        query = """
        query OrdersByName($q: String!) {
          orders(first: 5, query: $q) {
            edges { node { legacyResourceId name } }
          }
        }
        """
        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
        ids: list[str] = []
        async with httpx.AsyncClient(timeout=45) as client:
            for q in (f"name:{hashed}", f"name:{bare}", hashed, bare):
                try:
                    resp = await client.post(
                        f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json",
                        headers=headers,
                        json={"query": query, "variables": {"q": q}},
                    )
                    resp.raise_for_status()
                    edges = (
                        ((resp.json().get("data") or {}).get("orders") or {}).get("edges") or []
                    )
                    for edge in edges:
                        node = (edge or {}).get("node") or {}
                        oid = str(node.get("legacyResourceId") or "").strip()
                        name = str(node.get("name") or "")
                        from app.tracking.payload_parser import order_name_matches

                        if oid and order_name_matches(name, bare) and oid not in ids:
                            ids.append(oid)
                    if ids:
                        return ids
                except Exception:
                    continue
        return ids

    async def get_order(self, order_id: str | int) -> dict:
        """Fetch a single order by numeric Shopify id."""
        if not self.access_token:
            raise ValueError("No access token")
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(
                f"{self.admin_api_base}/orders/{order_id}.json",
                headers={"X-Shopify-Access-Token": self.access_token},
            )
            resp.raise_for_status()
            return resp.json()["order"]

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

    async def create_fulfillment_event(
        self,
        fulfillment_id: str,
        *,
        status: str = "delivered",
        message: str | None = None,
        order_id: str | None = None,
    ) -> dict:
        """Mark a fulfillment shipment status (e.g. delivered) via Admin API.

        Prefers GraphQL ``fulfillmentEventCreate``; falls back to REST when
        ``order_id`` is available. Requires the ``write_fulfillments`` scope.
        """
        if not self.access_token:
            raise ValueError("No access token")

        fid = str(fulfillment_id).strip()
        if not fid:
            raise ValueError("fulfillment_id is required")

        graphql_status = status.strip().upper().replace(" ", "_")
        gid = fid if fid.startswith("gid://") else f"gid://shopify/Fulfillment/{fid}"
        event_input: dict = {
            "fulfillmentId": gid,
            "status": graphql_status,
        }
        if message:
            event_input["message"] = message

        mutation = """
        mutation fulfillmentEventCreate($fulfillmentEvent: FulfillmentEventInput!) {
          fulfillmentEventCreate(fulfillmentEvent: $fulfillmentEvent) {
            fulfillmentEvent { id status }
            userErrors { field message }
          }
        }
        """
        headers = {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json",
                headers=headers,
                json={"query": mutation, "variables": {"fulfillmentEvent": event_input}},
            )
            if resp.status_code < 400:
                payload = resp.json()
                errors = payload.get("errors") or []
                result = (payload.get("data") or {}).get("fulfillmentEventCreate") or {}
                user_errors = result.get("userErrors") or []
                if not errors and not user_errors and result.get("fulfillmentEvent"):
                    return result["fulfillmentEvent"]
                # Access / scope issues — don't silently fall back with a bad token
                combined = " ".join(
                    str(e.get("message") or e) for e in (errors + user_errors)
                ).lower()
                if "access" in combined or "scope" in combined or "permission" in combined:
                    raise PermissionError(combined or "Shopify denied fulfillment event create")
                if user_errors or errors:
                    # Fall through to REST if we have order_id
                    if not order_id:
                        raise RuntimeError(combined or "fulfillmentEventCreate failed")
                else:
                    # Unexpected empty success — try REST
                    if not order_id:
                        raise RuntimeError("fulfillmentEventCreate returned no event")
            elif order_id is None:
                resp.raise_for_status()

            if not order_id:
                raise RuntimeError("Could not create fulfillment event")

            rest_status = status.strip().lower().replace(" ", "_")
            rest_body: dict = {"event": {"status": rest_status}}
            if message:
                rest_body["event"]["message"] = message
            rest_resp = await client.post(
                f"{self.admin_api_base}/orders/{order_id}/fulfillments/{fid}/events.json",
                headers=headers,
                json=rest_body,
            )
            rest_resp.raise_for_status()
            return rest_resp.json().get("fulfillment_event") or rest_resp.json()

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
