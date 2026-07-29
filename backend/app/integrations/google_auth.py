"""Google OAuth for platform sign-in / sign-up (openid email profile only)."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import httpx
from jose import JWTError, jwt

from app.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_STATE_TYPE = "google_auth"
_STATE_TTL_MINUTES = 10


class GoogleAuthClient:
    @staticmethod
    def create_state() -> str:
        expire = datetime.now(UTC) + timedelta(minutes=_STATE_TTL_MINUTES)
        payload = {
            "type": _STATE_TYPE,
            "nonce": secrets.token_urlsafe(16),
            "exp": expire,
        }
        return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    @staticmethod
    def verify_state(state: str) -> bool:
        try:
            payload = jwt.decode(
                state, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
            )
            return payload.get("type") == _STATE_TYPE
        except JWTError:
            return False

    @staticmethod
    def build_authorize_url(state: str) -> str:
        if not settings.google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_auth_redirect_uri,
            "response_type": "code",
            "scope": settings.google_auth_scopes,
            "access_type": "online",
            "prompt": "select_account",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    @staticmethod
    async def exchange_code_for_token(code: str) -> dict[str, Any]:
        if not settings.google_client_id or not settings.google_client_secret:
            raise ValueError("Google OAuth credentials are not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_auth_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def fetch_userinfo(access_token: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()
