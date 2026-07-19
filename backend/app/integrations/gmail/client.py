import secrets
from urllib.parse import urlencode

import httpx

from app.config import settings

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"


class GmailClient:
    @staticmethod
    def build_authorize_url(state: str) -> str:
        if not settings.google_client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured")
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": settings.google_scopes,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    @staticmethod
    async def exchange_code_for_token(code: str) -> dict:
        if not settings.google_client_id or not settings.google_client_secret:
            raise ValueError("Google OAuth credentials are not configured")
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_client_id,
                    "client_secret": settings.google_client_secret,
                    "redirect_uri": settings.google_redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def fetch_userinfo(access_token: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def generate_state() -> str:
        return secrets.token_urlsafe(32)
