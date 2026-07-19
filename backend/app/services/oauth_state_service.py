import json
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.db.models import OAuthState
from app.integrations.gmail.client import GmailClient
from app.integrations.shopify.client import ShopifyClient


class OAuthStateService:
    @staticmethod
    def create(db: Session, provider: str, user_id: str, extra: dict | None = None, minutes: int = 10) -> str:
        state = (
            ShopifyClient.generate_state()
            if provider == "shopify"
            else GmailClient.generate_state()
        )
        db.add(
            OAuthState(
                state=state,
                provider=provider,
                user_id=user_id,
                extra=json.dumps(extra) if extra else None,
                expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
            )
        )
        db.commit()
        return state

    @staticmethod
    def consume(db: Session, state: str, provider: str) -> OAuthState | None:
        row = (
            db.query(OAuthState)
            .filter(OAuthState.state == state, OAuthState.provider == provider)
            .first()
        )
        if not row:
            return None
        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            db.delete(row)
            db.commit()
            return None
        db.delete(row)
        db.commit()
        return row
