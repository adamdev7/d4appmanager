import logging

import httpx
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value
from app.db.models import GmailAccount, GmailAccountStatus

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


async def refresh_gmail_access_token(refresh_token: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]


async def get_gmail_access_token(db: Session, account: GmailAccount) -> str | None:
    if account.status != GmailAccountStatus.CONNECTED.value:
        return None
    if not account.refresh_token_encrypted:
        return None
    try:
        refresh = decrypt_value(account.refresh_token_encrypted)
        return await refresh_gmail_access_token(refresh)
    except Exception as exc:
        logger.warning("Gmail token refresh failed for %s: %s", account.email, exc)
        return None
