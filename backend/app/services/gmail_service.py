from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import encrypt_value
from app.db.models import (
    GmailAccount,
    GmailAccountStatus,
    GmailStoreLink,
    Store,
    User,
    UserEmailSettings,
)
from app.integrations.gmail.client import GmailClient
from app.models.gmail_account import GmailEmailSettings
from app.services.oauth_state_service import OAuthStateService


class GmailService:
    def list_accounts(self, db: Session, user: User, store_id: str | None = None) -> list[dict]:
        accounts = db.scalars(
            select(GmailAccount).where(GmailAccount.owner_id == user.id).order_by(GmailAccount.email)
        ).all()
        result = []
        for acc in accounts:
            linked = [link.store_id for link in acc.store_links]
            if store_id and store_id not in linked:
                continue
            result.append(self._serialize(acc, linked))
        return result

    def _serialize(self, acc: GmailAccount, store_ids: list[str]) -> dict:
        return {
            "id": acc.id,
            "email": acc.email,
            "display_name": acc.display_name,
            "status": acc.status,
            "is_default_sender": acc.is_default_sender,
            "store_ids": store_ids,
        }

    def begin_oauth(self, db: Session, user: User, store_id: str | None = None) -> str:
        if not settings.google_client_id:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env",
            )
        extra = {"store_id": store_id} if store_id else {}
        state = OAuthStateService.create(db, "google", user.id, extra)
        return GmailClient.build_authorize_url(state)

    async def complete_oauth(self, db: Session, code: str, state: str) -> tuple[User, GmailAccount]:
        oauth = OAuthStateService.consume(db, state, "google")
        if not oauth:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

        user = db.get(User, oauth.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User not found")

        token_data = await GmailClient.exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 3600)

        if not refresh_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google did not return a refresh token. Revoke app access and try again with consent.",
            )

        userinfo = await GmailClient.fetch_userinfo(access_token)
        email = userinfo.get("email", "").lower()
        name = userinfo.get("name", email)

        account = db.scalar(
            select(GmailAccount).where(GmailAccount.owner_id == user.id, GmailAccount.email == email)
        )
        if not account:
            has_default = db.scalar(
                select(GmailAccount).where(
                    GmailAccount.owner_id == user.id, GmailAccount.is_default_sender.is_(True)
                )
            )
            account = GmailAccount(
                owner_id=user.id,
                email=email,
                display_name=name,
                is_default_sender=has_default is None,
            )
            db.add(account)

        account.display_name = name
        account.status = GmailAccountStatus.CONNECTED.value
        account.access_token_encrypted = encrypt_value(access_token)
        account.refresh_token_encrypted = encrypt_value(refresh_token)
        account.token_expires_at = datetime.now(UTC) + timedelta(seconds=int(expires_in))
        db.commit()
        db.refresh(account)

        if oauth.extra:
            import json

            extra = json.loads(oauth.extra)
            store_id = extra.get("store_id")
            if store_id:
                store = db.get(Store, store_id)
                if store and store.owner_id == user.id:
                    exists = db.scalar(
                        select(GmailStoreLink).where(
                            GmailStoreLink.gmail_account_id == account.id,
                            GmailStoreLink.store_id == store_id,
                        )
                    )
                    if not exists:
                        db.add(GmailStoreLink(gmail_account_id=account.id, store_id=store_id))
                        db.commit()

        return user, account

    def disconnect_account(self, db: Session, user: User, account_id: str) -> bool:
        account = db.get(GmailAccount, account_id)
        if not account or account.owner_id != user.id:
            return False
        account.status = GmailAccountStatus.DISCONNECTED.value
        account.refresh_token_encrypted = None
        account.access_token_encrypted = None
        db.commit()
        return True

    def _email_settings_query(self, user_id: str, store_id: str | None):
        q = select(UserEmailSettings).where(UserEmailSettings.user_id == user_id)
        if store_id is None:
            return q.where(UserEmailSettings.store_id.is_(None))
        return q.where(UserEmailSettings.store_id == store_id)

    def get_email_settings(self, db: Session, user: User, store_id: str | None = None) -> GmailEmailSettings:
        row = db.scalar(self._email_settings_query(user.id, store_id))
        if not row:
            row = UserEmailSettings(user_id=user.id, store_id=store_id)
            db.add(row)
            db.commit()
            db.refresh(row)
        return GmailEmailSettings(
            reply_to=row.reply_to,
            signature_html=row.signature_html or "",
            track_opens=row.track_opens,
            track_clicks=row.track_clicks,
            daily_send_limit=row.daily_send_limit,
        )

    def update_email_settings(
        self, db: Session, user: User, data: GmailEmailSettings, store_id: str | None = None
    ) -> GmailEmailSettings:
        row = db.scalar(self._email_settings_query(user.id, store_id))
        if not row:
            row = UserEmailSettings(user_id=user.id, store_id=store_id)
            db.add(row)
        row.reply_to = str(data.reply_to) if data.reply_to else None
        row.signature_html = data.signature_html
        row.track_opens = data.track_opens
        row.track_clicks = data.track_clicks
        row.daily_send_limit = data.daily_send_limit
        db.commit()
        return data
