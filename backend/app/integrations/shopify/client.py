import asyncio
import json
import logging
import re
import secrets
import time
from urllib.parse import urlencode

import httpx

from app.config import settings
from app.integrations.shopify.credentials import (
    ShopifyAppCredentials,
    credentials_for_query,
    public_credentials,
    webhook_signed_by_known_app,
)

logger = logging.getLogger(__name__)

SHOP_DOMAIN_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9\-]*\.myshopify\.com$")

# Requested query cost must stay under Shopify's 1000-point single-query limit.
_ORDER_PAGE_SIZE = 5
_PRODUCT_PAGE_SIZE = 8
# Larger reads go through bulk operations instead of paginated queries.
_PAGINATED_ORDER_LIMIT = 25
_PAGINATED_PRODUCT_LIMIT = 50

_SHIPMENT_STATUSES = {
    "label_printed",
    "label_purchased",
    "attempted_delivery",
    "ready_for_pickup",
    "picked_up",
    "carrier_picked_up",
    "confirmed",
    "in_transit",
    "out_for_delivery",
    "delivered",
    "delayed",
    "failure",
}

_ADDRESS_FIELDS = (
    "firstName lastName name company address1 address2 city province provinceCode "
    "zip country countryCodeV2 phone"
)

_ORDER_FIELDS = f"""
  id
  legacyResourceId
  name
  number
  email
  phone
  createdAt
  updatedAt
  processedAt
  cancelledAt
  cancelReason
  closedAt
  displayFinancialStatus
  displayFulfillmentStatus
  currencyCode
  presentmentCurrencyCode
  note
  tags
  sourceName
  test
  paymentGatewayNames
  clientIp
  statusPageUrl
  customAttributes {{ key value }}
  totalPriceSet {{ shopMoney {{ amount currencyCode }} presentmentMoney {{ amount currencyCode }} }}
  currentTotalPriceSet {{ shopMoney {{ amount currencyCode }} presentmentMoney {{ amount currencyCode }} }}
  subtotalPriceSet {{ shopMoney {{ amount }} }}
  totalTaxSet {{ shopMoney {{ amount }} }}
  totalDiscountsSet {{ shopMoney {{ amount }} }}
  totalRefundedSet {{ shopMoney {{ amount }} }}
  customer {{
    id
    legacyResourceId
    firstName
    lastName
    defaultEmailAddress {{ emailAddress }}
    defaultPhoneNumber {{ phoneNumber }}
  }}
  shippingAddress {{ {_ADDRESS_FIELDS} }}
  billingAddress {{ {_ADDRESS_FIELDS} }}
  customerJourneySummary {{
    firstVisit {{ landingPage referrerUrl }}
    lastVisit {{ landingPage referrerUrl }}
  }}
"""

_FULFILLMENT_FIELDS = """
  id
  legacyResourceId
  status
  displayStatus
  createdAt
  updatedAt
  trackingInfo(first: 3) { number company url }
"""

_LINE_ITEM_FIELDS = """
  __typename
  id
  title
  name
  quantity
  sku
  variantTitle
  variant { id }
  product { id }
  image { url }
  originalUnitPriceSet { shopMoney { amount currencyCode } presentmentMoney { amount currencyCode } }
"""

_SHIPPING_LINE_FIELDS = "__typename id title originalPriceSet { shopMoney { amount } }"


def _order_selection(*, line_items: int, fulfillment_items: int) -> str:
    fulfillment_lines = (
        f"fulfillmentLineItems(first: {fulfillment_items}) "
        "{ nodes { quantity lineItem { title } } }"
        if fulfillment_items
        else ""
    )
    return f"""
  {_ORDER_FIELDS}
  fulfillments(first: 5) {{ {_FULFILLMENT_FIELDS} {fulfillment_lines} }}
  shippingLines(first: 5) {{ nodes {{ {_SHIPPING_LINE_FIELDS} }} }}
  lineItems(first: {line_items}) {{ nodes {{ {_LINE_ITEM_FIELDS} }} }}
"""


_BULK_ORDER_SELECTION = f"""
  {_ORDER_FIELDS}
  fulfillments(first: 5) {{ {_FULFILLMENT_FIELDS} }}
  shippingLines {{ edges {{ node {{ {_SHIPPING_LINE_FIELDS} }} }} }}
  lineItems {{ edges {{ node {{ {_LINE_ITEM_FIELDS} }} }} }}
"""

_PRODUCT_FIELDS = """
  id
  legacyResourceId
  title
  handle
  descriptionHtml
  vendor
  productType
  tags
  status
  createdAt
  updatedAt
  onlineStoreUrl
"""

_MEDIA_FIELDS = "__typename ... on MediaImage { id image { url altText width height } }"

_VARIANT_FIELDS = """
  __typename
  id
  legacyResourceId
  title
  price
  sku
  position
  availableForSale
  inventoryQuantity
  inventoryItem { tracked }
"""


def _product_selection(*, media: int, variants: int) -> str:
    return f"""
  {_PRODUCT_FIELDS}
  media(first: {media}) {{ nodes {{ {_MEDIA_FIELDS} }} }}
  variants(first: {variants}) {{ nodes {{ {_VARIANT_FIELDS} }} }}
"""


_BULK_PRODUCT_SELECTION = f"""
  {_PRODUCT_FIELDS}
  media {{ edges {{ node {{ {_MEDIA_FIELDS} }} }} }}
  variants {{ edges {{ node {{ {_VARIANT_FIELDS} }} }} }}
"""

# Bulk JSONL puts nested connection rows on their own lines; map them back by GID type.
_BULK_ORDER_CHILDREN = {"LineItem": "lineItems", "ShippingLine": "shippingLines"}
_BULK_PRODUCT_CHILDREN = {"ProductVariant": "variants", "MediaImage": "media"}


def _search_value(value: str) -> str:
    cleaned = str(value).replace("\\", "").replace('"', "").strip()
    return f'"{cleaned}"'


def _legacy_int(gid_or_id) -> int | str | None:
    if gid_or_id is None or gid_or_id == "":
        return None
    tail = str(gid_or_id).rsplit("/", 1)[-1].strip()
    if not tail:
        return None
    return int(tail) if tail.isdigit() else tail


def _amount(money_set: dict | None, key: str = "shopMoney") -> str | None:
    return ((money_set or {}).get(key) or {}).get("amount")


def _money_set(money_set: dict | None) -> dict | None:
    if not money_set:
        return None
    out: dict = {}
    for gql_key, rest_key in (("shopMoney", "shop_money"), ("presentmentMoney", "presentment_money")):
        money = money_set.get(gql_key)
        if money:
            out[rest_key] = {"amount": money.get("amount"), "currency_code": money.get("currencyCode")}
    return out or None


def _nodes(conn) -> list[dict]:
    if isinstance(conn, list):
        return [n for n in conn if isinstance(n, dict)]
    if not isinstance(conn, dict):
        return []
    if "nodes" in conn:
        return [n for n in conn.get("nodes") or [] if isinstance(n, dict)]
    return [
        (e or {}).get("node")
        for e in conn.get("edges") or []
        if isinstance((e or {}).get("node"), dict)
    ]


def _address_to_rest(addr: dict | None) -> dict | None:
    if not addr:
        return None
    return {
        "first_name": addr.get("firstName"),
        "last_name": addr.get("lastName"),
        "name": addr.get("name"),
        "company": addr.get("company"),
        "address1": addr.get("address1"),
        "address2": addr.get("address2"),
        "city": addr.get("city"),
        "province": addr.get("province"),
        "province_code": addr.get("provinceCode"),
        "zip": addr.get("zip"),
        "country": addr.get("country"),
        "country_code": addr.get("countryCodeV2"),
        "phone": addr.get("phone"),
    }


def _fulfillment_status_to_rest(display: str | None) -> str | None:
    return {
        "FULFILLED": "fulfilled",
        "PARTIALLY_FULFILLED": "partial",
        "RESTOCKED": "restocked",
    }.get(str(display or "").upper())


def _fulfillment_to_rest(node: dict) -> dict:
    tracking = [t for t in node.get("trackingInfo") or [] if isinstance(t, dict)]
    numbers = [str(t["number"]) for t in tracking if t.get("number")]
    urls = [str(t["url"]) for t in tracking if t.get("url")]
    company = next((str(t["company"]) for t in tracking if t.get("company")), None)
    display = str(node.get("displayStatus") or "").lower()
    items = [
        {"title": ((li.get("lineItem") or {}).get("title")), "quantity": li.get("quantity") or 1}
        for li in _nodes(node.get("fulfillmentLineItems"))
    ]
    return {
        "id": _legacy_int(node.get("legacyResourceId") or node.get("id")),
        "admin_graphql_api_id": node.get("id"),
        "status": str(node.get("status") or "").lower() or None,
        "shipment_status": display if display in _SHIPMENT_STATUSES else None,
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "tracking_company": company,
        "tracking_number": numbers[0] if numbers else None,
        "tracking_numbers": numbers,
        "tracking_url": urls[0] if urls else None,
        "tracking_urls": urls,
        "line_items": items,
    }


def _line_item_to_rest(node: dict) -> dict:
    price_set = node.get("originalUnitPriceSet")
    image_url = (node.get("image") or {}).get("url")
    return {
        "id": _legacy_int(node.get("id")),
        "title": node.get("title"),
        "name": node.get("name"),
        "quantity": node.get("quantity") or 0,
        "sku": node.get("sku"),
        "variant_title": node.get("variantTitle"),
        "variant_id": _legacy_int((node.get("variant") or {}).get("id")),
        "product_id": _legacy_int((node.get("product") or {}).get("id")),
        "price": _amount(price_set),
        "price_set": _money_set(price_set),
        "image": {"src": image_url} if image_url else None,
    }


def order_to_rest(node: dict) -> dict:
    """Map a GraphQL Order to the REST/webhook order shape the rest of the app reads."""
    customer = node.get("customer") or None
    rest_customer = None
    if customer:
        rest_customer = {
            "id": _legacy_int(customer.get("legacyResourceId") or customer.get("id")),
            "email": (customer.get("defaultEmailAddress") or {}).get("emailAddress"),
            "phone": (customer.get("defaultPhoneNumber") or {}).get("phoneNumber"),
            "first_name": customer.get("firstName"),
            "last_name": customer.get("lastName"),
        }

    journey = node.get("customerJourneySummary") or {}
    visit = journey.get("lastVisit") or journey.get("firstVisit") or {}
    refunded = _amount(node.get("totalRefundedSet"))
    refunds = (
        [{"transactions": [{"kind": "refund", "status": "success", "amount": refunded}]}]
        if refunded and float(refunded) > 0
        else []
    )
    name = node.get("name") or ""
    number = node.get("number")
    if number is None:
        digits = re.sub(r"\D", "", name)
        number = int(digits) if digits else None
    client_ip = node.get("clientIp")

    return {
        "id": _legacy_int(node.get("legacyResourceId") or node.get("id")),
        "admin_graphql_api_id": node.get("id"),
        "name": name,
        "order_number": number,
        "email": node.get("email"),
        "contact_email": node.get("email"),
        "phone": node.get("phone"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "processed_at": node.get("processedAt"),
        "cancelled_at": node.get("cancelledAt"),
        "cancel_reason": str(node.get("cancelReason") or "").lower() or None,
        "closed_at": node.get("closedAt"),
        "financial_status": str(node.get("displayFinancialStatus") or "").lower() or None,
        "fulfillment_status": _fulfillment_status_to_rest(node.get("displayFulfillmentStatus")),
        "currency": node.get("currencyCode"),
        "presentment_currency": node.get("presentmentCurrencyCode"),
        "total_price": _amount(node.get("totalPriceSet")),
        "total_price_set": _money_set(node.get("totalPriceSet")),
        "current_total_price": _amount(node.get("currentTotalPriceSet")),
        "current_total_price_set": _money_set(node.get("currentTotalPriceSet")),
        "subtotal_price": _amount(node.get("subtotalPriceSet")),
        "total_tax": _amount(node.get("totalTaxSet")),
        "total_discounts": _amount(node.get("totalDiscountsSet")),
        "note": node.get("note"),
        "tags": ", ".join(node.get("tags") or []),
        "source_name": node.get("sourceName"),
        "test": bool(node.get("test")),
        "payment_gateway_names": list(node.get("paymentGatewayNames") or []),
        "browser_ip": client_ip,
        "client_details": {"browser_ip": client_ip} if client_ip else None,
        "landing_site": visit.get("landingPage"),
        "referring_site": visit.get("referrerUrl"),
        "order_status_url": node.get("statusPageUrl"),
        "note_attributes": [
            {"name": a.get("key"), "value": a.get("value")}
            for a in node.get("customAttributes") or []
            if isinstance(a, dict) and a.get("key")
        ],
        "customer": rest_customer,
        "shipping_address": _address_to_rest(node.get("shippingAddress")),
        "billing_address": _address_to_rest(node.get("billingAddress")),
        "line_items": [_line_item_to_rest(li) for li in _nodes(node.get("lineItems"))],
        "shipping_lines": [
            {"title": s.get("title"), "price": _amount(s.get("originalPriceSet")) or "0"}
            for s in _nodes(node.get("shippingLines"))
        ],
        "fulfillments": [
            _fulfillment_to_rest(f) for f in node.get("fulfillments") or [] if isinstance(f, dict)
        ],
        "refunds": refunds,
    }


def product_to_rest(node: dict) -> dict:
    """Map a GraphQL Product to the REST product shape (images, variants, tags string)."""
    product_id = _legacy_int(node.get("legacyResourceId") or node.get("id"))
    images: list[dict] = []
    for position, media in enumerate(_nodes(node.get("media")), start=1):
        image = media.get("image") or {}
        if not image.get("url"):
            continue
        images.append(
            {
                "id": _legacy_int(media.get("id")),
                "product_id": product_id,
                "src": image.get("url"),
                "alt": image.get("altText"),
                "width": image.get("width"),
                "height": image.get("height"),
                "position": position,
            }
        )
    variants = []
    for v in sorted(_nodes(node.get("variants")), key=lambda x: x.get("position") or 0):
        tracked = bool((v.get("inventoryItem") or {}).get("tracked"))
        variants.append(
            {
                "id": _legacy_int(v.get("legacyResourceId") or v.get("id")),
                "product_id": product_id,
                "title": v.get("title"),
                "price": v.get("price"),
                "sku": v.get("sku"),
                "position": v.get("position"),
                "available": v.get("availableForSale"),
                "inventory_quantity": v.get("inventoryQuantity"),
                "inventory_management": "shopify" if tracked else None,
            }
        )
    return {
        "id": product_id,
        "admin_graphql_api_id": node.get("id"),
        "title": node.get("title"),
        "handle": node.get("handle"),
        "body_html": node.get("descriptionHtml"),
        "vendor": node.get("vendor"),
        "product_type": node.get("productType"),
        "tags": ", ".join(node.get("tags") or []),
        "status": str(node.get("status") or "").lower() or None,
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "online_store_url": node.get("onlineStoreUrl"),
        "images": images,
        "image": images[0] if images else None,
        "variants": variants,
    }


def _raise_for_status(resp: httpx.Response, what: str) -> None:
    """Like ``raise_for_status`` but keeps Shopify's error body so server logs explain 4xx/5xx."""
    if resp.is_success:
        return
    raise httpx.HTTPStatusError(
        f"{what} failed with HTTP {resp.status_code}: {resp.text[:500]}",
        request=resp.request,
        response=resp,
    )


def _token_needs_renewal(resp: httpx.Response) -> bool:
    # 401 = expired token; this 403 = legacy non-expiring token (a 403 for missing scopes is not renewable).
    if resp.status_code == 401:
        return True
    return resp.status_code == 403 and "non-expiring access tokens" in resp.text.lower()


def nest_bulk_rows(rows: list[dict], children: dict[str, str]) -> list[dict]:
    """Rebuild nested connections from bulk JSONL rows linked by ``__parentId``."""
    parents: dict[str, dict] = {}
    roots: list[dict] = []
    for row in rows:
        parent_id = row.pop("__parentId", None)
        row_id = str(row.get("id") or "")
        if parent_id is None:
            roots.append(row)
            if row_id:
                parents[row_id] = row
            continue
        parent = parents.get(str(parent_id))
        type_name = str(row.get("__typename") or "")
        if not type_name and row_id.count("/") >= 4:
            type_name = row_id.split("/")[-2]
        field = children.get(type_name)
        if parent is None or not field:
            continue
        parent.setdefault(field, {"nodes": []})["nodes"].append(row)
    return roots


class ShopifyClient:
    def __init__(
        self,
        shop_domain: str,
        access_token: str | None = None,
        credentials: ShopifyAppCredentials | None = None,
    ) -> None:
        self.shop_domain = shop_domain.replace("https://", "").replace("http://", "").strip("/")
        if not self.shop_domain.endswith(".myshopify.com"):
            if "." not in self.shop_domain:
                self.shop_domain = f"{self.shop_domain}.myshopify.com"
        self.access_token = access_token
        self.credentials = credentials
        self.api_version = settings.shopify_api_version

    def _oauth_credentials(self) -> ShopifyAppCredentials:
        creds = self.credentials or public_credentials()
        if not creds:
            raise ValueError("SHOPIFY_CLIENT_ID is not configured")
        return creds

    @property
    def graphql_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}/graphql.json"

    def build_install_url(self, state: str) -> str:
        creds = self._oauth_credentials()
        params = {
            "client_id": creds.client_id,
            "scope": settings.shopify_scopes,
            "redirect_uri": settings.shopify_redirect_uri,
            "state": state,
        }
        return f"https://{self.shop_domain}/admin/oauth/authorize?{urlencode(params)}"

    async def _token_request(self, data: dict[str, str]) -> dict:
        creds = self._oauth_credentials()
        url = f"https://{self.shop_domain}/admin/oauth/access_token"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                url,
                data={
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    **data,
                },
                headers={"Accept": "application/json"},
            )
            _raise_for_status(resp, f"Shopify token request for {self.shop_domain}")
            return resp.json()

    async def exchange_code_for_token(self, code: str) -> dict:
        # Public apps created after 2026-04-01 get 403s on GraphQL with non-expiring tokens.
        return await self._token_request({"code": code, "expiring": "1"})

    async def refresh_access_token(self, refresh_token: str) -> dict:
        return await self._token_request({"grant_type": "refresh_token", "refresh_token": refresh_token})

    async def migrate_to_expiring_token(self, access_token: str) -> dict:
        """Trade a legacy non-expiring offline token for an expiring one (invalidates the old token)."""
        offline = "urn:shopify:params:oauth:token-type:offline-access-token"
        return await self._token_request(
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": access_token,
                "subject_token_type": offline,
                "requested_token_type": offline,
                "expiring": "1",
            }
        )

    async def _renew_access_token(self) -> bool:
        from app.services.store_service import renew_shopify_token

        fresh = await renew_shopify_token(self.shop_domain, self.access_token or "")
        if not fresh or fresh == self.access_token:
            return False
        self.access_token = fresh
        return True

    async def graphql(
        self,
        query: str,
        variables: dict | None = None,
        *,
        timeout: float = 45,
        max_retries: int = 4,
    ) -> dict:
        """Run an Admin GraphQL operation and return ``data``. Retries when throttled."""
        if not self.access_token:
            raise ValueError("No access token")
        body = {"query": query, "variables": variables or {}}
        renewed = False
        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(max_retries + 1):
                headers = {
                    "X-Shopify-Access-Token": self.access_token,
                    "Content-Type": "application/json",
                }
                resp = await client.post(self.graphql_url, headers=headers, json=body)
                if resp.status_code == 429 and attempt < max_retries:
                    await asyncio.sleep(float(resp.headers.get("Retry-After") or 2))
                    continue
                if not renewed and _token_needs_renewal(resp):
                    renewed = True
                    if await self._renew_access_token():
                        continue
                _raise_for_status(resp, f"Shopify GraphQL request for {self.shop_domain}")
                payload = resp.json()
                errors = payload.get("errors") or []
                throttled = any(
                    ((e or {}).get("extensions") or {}).get("code") == "THROTTLED" for e in errors
                )
                if throttled and attempt < max_retries:
                    await asyncio.sleep(2 * (attempt + 1))
                    continue
                if errors:
                    raise RuntimeError("; ".join(str((e or {}).get("message") or e) for e in errors))
                return payload.get("data") or {}
        raise RuntimeError("Shopify GraphQL request was throttled")

    async def run_bulk_query(
        self,
        query: str,
        children: dict[str, str],
        *,
        timeout_seconds: float = 300,
    ) -> list[dict]:
        """Run a bulk query, wait for it, and return root rows with nested children."""
        started = await self.graphql(
            """
            mutation RunBulk($query: String!) {
              bulkOperationRunQuery(query: $query) {
                bulkOperation { id status }
                userErrors { field message }
              }
            }
            """,
            {"query": query},
        )
        result = started.get("bulkOperationRunQuery") or {}
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise RuntimeError("; ".join(str(e.get("message") or e) for e in user_errors))
        op_id = (result.get("bulkOperation") or {}).get("id")
        if not op_id:
            raise RuntimeError("Shopify did not start the bulk query")

        deadline = time.monotonic() + timeout_seconds
        delay = 1.0
        op: dict = {}
        while True:
            data = await self.graphql(
                """
                query BulkStatus($id: ID!) {
                  bulkOperation(id: $id) { id status errorCode objectCount url partialDataUrl }
                }
                """,
                {"id": op_id},
            )
            op = data.get("bulkOperation") or {}
            status = str(op.get("status") or "")
            if status == "COMPLETED":
                break
            if status in ("FAILED", "CANCELED", "CANCELLED", "EXPIRED"):
                raise RuntimeError(
                    f"Shopify bulk query {status.lower()}: {op.get('errorCode') or 'unknown error'}"
                )
            if time.monotonic() > deadline:
                try:
                    await self.graphql(
                        """
                        mutation CancelBulk($id: ID!) {
                          bulkOperationCancel(id: $id) {
                            bulkOperation { id status }
                            userErrors { field message }
                          }
                        }
                        """,
                        {"id": op_id},
                    )
                except Exception:
                    logger.debug("Could not cancel bulk query %s", op_id, exc_info=True)
                raise TimeoutError("Shopify bulk query took too long")
            await asyncio.sleep(delay)
            delay = min(delay * 1.5, 5.0)

        url = op.get("url")
        if not url:
            return []
        rows: list[dict] = []
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        rows.append(json.loads(line))
        return nest_bulk_rows(rows, children)

    async def get_shop(self) -> dict:
        data = await self.graphql(
            """
            query Shop {
              shop {
                name
                email
                myshopifyDomain
                currencyCode
                ianaTimezone
                plan { publicDisplayName }
              }
            }
            """
        )
        shop = data.get("shop") or {}
        return {
            "name": shop.get("name"),
            "email": shop.get("email"),
            "myshopify_domain": shop.get("myshopifyDomain"),
            "currency": shop.get("currencyCode"),
            "iana_timezone": shop.get("ianaTimezone"),
            "plan_display_name": (shop.get("plan") or {}).get("publicDisplayName"),
        }

    async def register_webhook(self, topic: str, address: str) -> dict:
        data = await self.graphql(
            """
            mutation WebhookCreate(
              $topic: WebhookSubscriptionTopic!
              $webhookSubscription: WebhookSubscriptionInput!
            ) {
              webhookSubscriptionCreate(topic: $topic, webhookSubscription: $webhookSubscription) {
                webhookSubscription { id topic }
                userErrors { field message }
              }
            }
            """,
            {
                "topic": topic.upper().replace("/", "_"),
                "webhookSubscription": {"uri": address, "format": "JSON"},
            },
        )
        result = data.get("webhookSubscriptionCreate") or {}
        user_errors = result.get("userErrors") or []
        if user_errors:
            raise RuntimeError("; ".join(str(e.get("message") or e) for e in user_errors))
        return result.get("webhookSubscription") or {}

    @staticmethod
    def _orders_search(
        *,
        status: str = "any",
        since_id: str | None = None,
        created_at_min: str | None = None,
        created_at_max: str | None = None,
        financial_status: str | None = None,
        name: str | None = None,
        email: str | None = None,
        query: str | None = None,
        ids: str | None = None,
    ) -> str:
        parts: list[str] = []
        if status and status != "any":
            parts.append(f"status:{status}")
        if since_id:
            parts.append(f"id:>{since_id}")
        if created_at_min:
            parts.append(f"created_at:>='{created_at_min}'")
        if created_at_max:
            parts.append(f"created_at:<='{created_at_max}'")
        if financial_status and financial_status != "any":
            parts.append(f"financial_status:{financial_status}")
        if name:
            parts.append(f"name:{_search_value(name)}")
        if email:
            parts.append(f"email:{_search_value(email)}")
        if ids:
            id_terms = [f"id:{i.strip()}" for i in str(ids).split(",") if i.strip()]
            if id_terms:
                parts.append("(" + " OR ".join(id_terms) + ")")
        if query:
            parts.append(query)
        return " ".join(parts)

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
        email: str | None = None,
        query: str | None = None,
        ids: str | None = None,
    ) -> list[dict]:
        """Fetch orders, newest first (oldest first after ``since_id``)."""
        limit = min(max(limit, 1), 250)
        search = self._orders_search(
            status=status,
            since_id=since_id,
            created_at_min=created_at_min,
            created_at_max=created_at_max,
            financial_status=financial_status,
            name=name,
            email=email,
            query=query,
            ids=ids,
        )
        newest_first = not since_id

        if limit > _PAGINATED_ORDER_LIMIT:
            orders = await self._bulk_orders(search)
            orders.sort(key=lambda o: str(o.get("created_at") or ""), reverse=newest_first)
            return orders[:limit]

        gql = f"""
        query Orders($first: Int!, $after: String, $query: String, $reverse: Boolean) {{
          orders(first: $first, after: $after, query: $query, sortKey: CREATED_AT, reverse: $reverse) {{
            pageInfo {{ hasNextPage endCursor }}
            nodes {{ {_order_selection(line_items=15, fulfillment_items=0)} }}
          }}
        }}
        """
        orders: list[dict] = []
        cursor: str | None = None
        while len(orders) < limit:
            data = await self.graphql(
                gql,
                {
                    "first": min(_ORDER_PAGE_SIZE, limit - len(orders)),
                    "after": cursor,
                    "query": search or None,
                    "reverse": newest_first,
                },
            )
            conn = data.get("orders") or {}
            orders.extend(order_to_rest(n) for n in _nodes(conn))
            page_info = conn.get("pageInfo") or {}
            cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage") or not cursor:
                break
        return orders[:limit]

    async def _bulk_orders(self, search: str) -> list[dict]:
        args = f"(query: {json.dumps(search)}, sortKey: CREATED_AT)" if search else "(sortKey: CREATED_AT)"
        bulk = f"{{ orders{args} {{ edges {{ node {{ {_BULK_ORDER_SELECTION} }} }} }} }}"
        rows = await self.run_bulk_query(bulk, _BULK_ORDER_CHILDREN)
        return [order_to_rest(row) for row in rows]

    async def find_orders_by_name(self, order_number: str, *, limit: int = 10) -> list[dict]:
        """Find orders by customer-facing name (#1042 / 1042), exact matches only."""
        from app.tracking.payload_parser import normalize_order_number, order_name_matches

        bare = normalize_order_number(order_number)
        if not bare:
            return []

        def _exact(orders: list[dict]) -> list[dict]:
            return [o for o in orders if order_name_matches(str(o.get("name") or ""), bare)]

        for name in (f"#{bare}", bare):
            try:
                matched = _exact(await self.list_orders(name=name, limit=limit))
                if matched:
                    return matched
            except Exception:
                logger.debug(
                    "Shopify order name search failed for %s name=%s",
                    self.shop_domain,
                    name,
                    exc_info=True,
                )
        return []

    async def find_orders_by_email(self, email: str, *, limit: int = 10) -> list[dict]:
        """Orders whose customer/contact email matches this address."""
        from app.tracking.payload_parser import emails_match, normalize_email, recipient_email

        address = normalize_email(email)
        if not address:
            return []
        for search in (f"email:{_search_value(address)}", f"customer_email:{_search_value(address)}"):
            try:
                orders = await self.list_orders(query=search, limit=limit)
            except Exception:
                logger.debug(
                    "Shopify email search failed for %s", self.shop_domain, exc_info=True
                )
                continue
            matched = [o for o in orders if emails_match(recipient_email(o), address)]
            if matched:
                return matched[:limit]
        return []

    async def get_order(self, order_id: str | int) -> dict:
        """Fetch a single order by numeric Shopify id or GID."""
        oid = str(order_id).strip()
        gid = oid if oid.startswith("gid://") else f"gid://shopify/Order/{oid}"
        data = await self.graphql(
            f"""
            query Order($id: ID!) {{
              order(id: $id) {{ {_order_selection(line_items=50, fulfillment_items=10)} }}
            }}
            """,
            {"id": gid},
        )
        node = data.get("order")
        if not node:
            raise LookupError(f"Order {oid} not found")
        return order_to_rest(node)

    async def list_all_orders_in_range(
        self,
        *,
        created_at_min: str | None = None,
        created_at_max: str | None = None,
        financial_status: str = "any",
        max_pages: int = 20,
    ) -> list[dict]:
        """Every order in a date range (oldest first), capped at ``max_pages * 250``."""
        search = self._orders_search(
            created_at_min=created_at_min,
            created_at_max=created_at_max,
            financial_status=financial_status,
        )
        orders = await self._bulk_orders(search)
        orders.sort(key=lambda o: str(o.get("created_at") or ""))
        return orders[: max(1, max_pages) * 250]

    @staticmethod
    def _checkout_token_from_url(url: str | None) -> str | None:
        if not url:
            return None
        match = re.search(r"/checkouts/(?:ac/)?([0-9a-f]{32,64})", str(url), re.I)
        return match.group(1) if match else None

    @staticmethod
    def _legacy_id_from_gid(gid: str | None) -> str | None:
        if not gid:
            return None
        tail = str(gid).rsplit("/", 1)[-1].strip()
        return tail or None

    @staticmethod
    def _gql_checkout_to_rest(node: dict) -> dict:
        """Map GraphQL AbandonedCheckout node to REST-like dict for CAPI mappers."""
        money = (node.get("totalPriceSet") or {}).get("shopMoney") or {}
        subtotal = (node.get("subtotalPriceSet") or {}).get("shopMoney") or {}
        legacy_id = ShopifyClient._legacy_id_from_gid(node.get("id"))
        token = ShopifyClient._checkout_token_from_url(node.get("abandonedCheckoutUrl"))
        if not token and legacy_id:
            token = legacy_id

        line_items: list[dict] = []
        for item in ((node.get("lineItems") or {}).get("nodes") or []):
            if not isinstance(item, dict):
                continue
            variant = item.get("variant") or {}
            product = variant.get("product") or {}
            unit = ((item.get("originalUnitPriceSet") or {}).get("shopMoney") or {}).get(
                "amount"
            )
            line_items.append(
                {
                    "quantity": item.get("quantity") or 0,
                    "title": item.get("title"),
                    "sku": variant.get("sku"),
                    "variant_id": ShopifyClient._legacy_id_from_gid(variant.get("id")),
                    "product_id": ShopifyClient._legacy_id_from_gid(product.get("id")),
                    "price": unit,
                }
            )

        note_attributes = [
            {"name": attr.get("key"), "value": attr.get("value")}
            for attr in (node.get("customAttributes") or [])
            if isinstance(attr, dict) and attr.get("key")
        ]

        customer = node.get("customer") or {}
        billing = node.get("billingAddress") or {}
        shipping = node.get("shippingAddress") or {}

        def _addr(block: dict) -> dict:
            return {
                "first_name": block.get("firstName"),
                "last_name": block.get("lastName"),
                "address1": block.get("address1"),
                "address2": block.get("address2"),
                "city": block.get("city"),
                "province": block.get("province"),
                "zip": block.get("zip"),
                "country_code": block.get("countryCode"),
                "phone": block.get("phone"),
            }

        checkout: dict = {
            "id": legacy_id,
            "token": token,
            "created_at": node.get("createdAt"),
            "updated_at": node.get("updatedAt"),
            "completed_at": node.get("completedAt"),
            "total_price": money.get("amount"),
            "subtotal_price": subtotal.get("amount") or money.get("amount"),
            "currency": money.get("currencyCode") or subtotal.get("currencyCode") or "USD",
            "landing_site": node.get("abandonedCheckoutUrl"),
            "abandoned_checkout_url": node.get("abandonedCheckoutUrl"),
            "note_attributes": note_attributes,
            "line_items": line_items,
            "email": customer.get("email"),
            "phone": customer.get("phone") or billing.get("phone") or shipping.get("phone"),
            "customer": customer,
            "billing_address": _addr(billing) if billing else None,
            "shipping_address": _addr(shipping) if shipping else None,
        }
        if checkout.get("cart_token") is None and token:
            checkout["cart_token"] = token
        return checkout

    async def list_abandoned_checkouts_in_range(
        self,
        *,
        created_at_min: str,
        max_pages: int = 20,
        page_size: int = 50,
    ) -> list[dict]:
        """Paginate abandoned checkouts created on/after created_at_min (GraphQL)."""
        query_filter = f"created_at:>='{created_at_min}' recovery_state:not_recovered"
        gql = """
        query AbandonedCheckoutsInRange($query: String!, $cursor: String, $first: Int!) {
          abandonedCheckouts(
            first: $first
            after: $cursor
            query: $query
            sortKey: CREATED_AT
            reverse: true
          ) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              createdAt
              updatedAt
              completedAt
              abandonedCheckoutUrl
              note
              customAttributes { key value }
              subtotalPriceSet { shopMoney { amount currencyCode } }
              totalPriceSet { shopMoney { amount currencyCode } }
              billingAddress {
                firstName lastName address1 address2 city province zip countryCode phone
              }
              shippingAddress {
                firstName lastName address1 address2 city province zip countryCode phone
              }
              customer { id email phone firstName lastName }
              lineItems(first: 50) {
                nodes {
                  quantity
                  title
                  variant { id sku product { id } }
                  originalUnitPriceSet { shopMoney { amount } }
                }
              }
            }
          }
        }
        """
        all_checkouts: list[dict] = []
        cursor: str | None = None
        pages = max(1, min(max_pages, 50))
        first = max(1, min(page_size, 50))

        for _ in range(pages):
            data = await self.graphql(
                gql,
                {"query": query_filter, "cursor": cursor, "first": first},
                timeout=60,
            )
            conn = data.get("abandonedCheckouts") or {}
            for node in conn.get("nodes") or []:
                if not isinstance(node, dict) or node.get("completedAt"):
                    continue
                all_checkouts.append(self._gql_checkout_to_rest(node))
            page_info = conn.get("pageInfo") or {}
            cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage") or not cursor:
                break
        return all_checkouts

    async def get_product(self, product_id: str | int) -> dict:
        """Fetch a single product by numeric Shopify id or GID."""
        pid = str(product_id).strip()
        gid = pid if pid.startswith("gid://") else f"gid://shopify/Product/{pid}"
        data = await self.graphql(
            f"""
            query Product($id: ID!) {{
              product(id: $id) {{ {_product_selection(media=20, variants=100)} }}
            }}
            """,
            {"id": gid},
            timeout=20,
        )
        node = data.get("product")
        if not node:
            raise LookupError(f"Product {pid} not found")
        return product_to_rest(node)

    async def list_products(self, *, limit: int = 250, max_items: int | None = None) -> list[dict]:
        """Fetch products with variants and images.

        ``max_items`` stops early so callers do not wait on the full catalog. Small reads are
        paginated; full-catalog reads use a bulk query.
        """
        if max_items is None or max_items > _PAGINATED_PRODUCT_LIMIT:
            bulk = f"{{ products {{ edges {{ node {{ {_BULK_PRODUCT_SELECTION} }} }} }} }}"
            rows = await self.run_bulk_query(bulk, _BULK_PRODUCT_CHILDREN)
            products = [product_to_rest(row) for row in rows]
            return products[:max_items] if max_items is not None else products

        gql = f"""
        query Products($first: Int!, $after: String) {{
          products(first: $first, after: $after) {{
            pageInfo {{ hasNextPage endCursor }}
            nodes {{ {_product_selection(media=5, variants=50)} }}
          }}
        }}
        """
        products: list[dict] = []
        cursor: str | None = None
        page_size = min(max(limit, 1), _PRODUCT_PAGE_SIZE)
        while len(products) < max_items:
            data = await self.graphql(
                gql,
                {"first": min(page_size, max_items - len(products)), "after": cursor},
                timeout=20,
            )
            conn = data.get("products") or {}
            products.extend(product_to_rest(n) for n in _nodes(conn))
            page_info = conn.get("pageInfo") or {}
            cursor = page_info.get("endCursor")
            if not page_info.get("hasNextPage") or not cursor:
                break
        return products[:max_items]

    async def create_fulfillment_event(
        self,
        fulfillment_id: str,
        *,
        status: str = "delivered",
        message: str | None = None,
        order_id: str | None = None,
    ) -> dict:
        """Mark a fulfillment shipment status (e.g. delivered). Requires ``write_fulfillments``."""
        fid = str(fulfillment_id).strip()
        if not fid:
            raise ValueError("fulfillment_id is required")

        event_input: dict = {
            "fulfillmentId": fid if fid.startswith("gid://") else f"gid://shopify/Fulfillment/{fid}",
            "status": status.strip().upper().replace(" ", "_"),
        }
        if message:
            event_input["message"] = message

        try:
            data = await self.graphql(
                """
                mutation fulfillmentEventCreate($fulfillmentEvent: FulfillmentEventInput!) {
                  fulfillmentEventCreate(fulfillmentEvent: $fulfillmentEvent) {
                    fulfillmentEvent { id status }
                    userErrors { field message }
                  }
                }
                """,
                {"fulfillmentEvent": event_input},
                timeout=30,
            )
        except RuntimeError as exc:
            text = str(exc).lower()
            if "access" in text or "scope" in text or "permission" in text:
                raise PermissionError(str(exc)) from exc
            raise

        result = data.get("fulfillmentEventCreate") or {}
        user_errors = result.get("userErrors") or []
        if user_errors:
            combined = " ".join(str(e.get("message") or e) for e in user_errors)
            lowered = combined.lower()
            if "access" in lowered or "scope" in lowered or "permission" in lowered:
                raise PermissionError(combined)
            raise RuntimeError(combined or "fulfillmentEventCreate failed")
        if not result.get("fulfillmentEvent"):
            raise RuntimeError("fulfillmentEventCreate returned no event")
        return result["fulfillmentEvent"]

    @staticmethod
    def verify_webhook_hmac(body: bytes, hmac_header: str) -> bool:
        return webhook_signed_by_known_app(body, hmac_header)

    @staticmethod
    def verify_query_hmac(params: dict[str, str]) -> bool:
        """Verify the ``hmac`` Shopify adds to app-launch and OAuth callback URLs."""
        return credentials_for_query(params) is not None

    @staticmethod
    def is_valid_shop_domain(shop: str | None) -> bool:
        return bool(shop) and bool(SHOP_DOMAIN_RE.match(str(shop)))

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)
