"""Public app credentials stay the default. A second pair is limited to named accounts.

Shopify signs each install and webhook with the secret of the app that was opened.
The matching secret picks the client id used for OAuth. The reviewer's public app
never matches the private secret, so that install keeps using the public app.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass

from app.config import settings

PUBLIC = "public"
PRIVATE = "private"


@dataclass(frozen=True)
class ShopifyAppCredentials:
    kind: str
    client_id: str
    client_secret: str


def public_credentials() -> ShopifyAppCredentials | None:
    client_id = (settings.shopify_client_id or "").strip()
    secret = (settings.shopify_client_secret or "").strip()
    if not client_id or not secret:
        return None
    return ShopifyAppCredentials(PUBLIC, client_id, secret)


def private_credentials() -> ShopifyAppCredentials | None:
    client_id = (settings.shopify_private_client_id or "").strip()
    secret = (settings.shopify_private_client_secret or "").strip()
    if not client_id or not secret:
        return None
    return ShopifyAppCredentials(PRIVATE, client_id, secret)


def private_account_emails() -> set[str]:
    return {
        item.strip().lower()
        for item in (settings.shopify_private_account_emails or "").split(",")
        if item.strip()
    }


def user_may_use_private_app(user) -> bool:
    email = (getattr(user, "email", None) or "").strip().lower()
    return bool(email) and email in private_account_emails()


def query_hmac_valid(params: dict[str, str], secret: str) -> bool:
    supplied = str(params.get("hmac") or "")
    if not supplied or not secret or len(supplied) != 64:
        return False
    message = "&".join(
        f"{key}={value}"
        for key, value in sorted(params.items())
        if key not in ("hmac", "signature")
    )
    computed = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed, supplied)


def credentials_for_query(params: dict[str, str]) -> ShopifyAppCredentials | None:
    """Public secret wins when both could match, so the review app stays on its own client."""
    public = public_credentials()
    if public and query_hmac_valid(params, public.client_secret):
        return public
    private = private_credentials()
    if private and query_hmac_valid(params, private.client_secret):
        return private
    return None


def webhook_hmac_valid(body: bytes, hmac_header: str, secret: str) -> bool:
    if not hmac_header or not secret:
        return False
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).digest()
    computed = base64.b64encode(digest).decode()
    if len(computed) != len(hmac_header):
        return False
    return hmac.compare_digest(computed, hmac_header)


def webhook_signed_by_known_app(body: bytes, hmac_header: str) -> bool:
    public = public_credentials()
    if public and webhook_hmac_valid(body, hmac_header, public.client_secret):
        return True
    private = private_credentials()
    return bool(private and webhook_hmac_valid(body, hmac_header, private.client_secret))


def credentials_for_store(store) -> ShopifyAppCredentials | None:
    """Refresh and reconnect with the app that issued this store's token."""
    if getattr(store, "shopify_app", None) == PRIVATE:
        private = private_credentials()
        if private:
            return private
    return public_credentials()
