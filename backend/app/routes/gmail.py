from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.config import settings
from app.db.models import User
from app.db.session import get_db
from app.models.gmail_account import GmailEmailSettings
from app.services.gmail_service import GmailService

router = APIRouter()
_gmail = GmailService()


@router.get("/accounts")
async def list_accounts(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _gmail.list_accounts(db, user, store_id)


@router.get("/oauth/authorize")
async def oauth_authorize(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    url = _gmail.begin_oauth(db, user, store_id)
    return {"authorize_url": url}


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: Session = Depends(get_db),
):
    _, account = await _gmail.complete_oauth(db, code, state)
    return RedirectResponse(
        f"{settings.frontend_url}/settings/gmail?connected=1&account_id={account.id}"
    )


@router.post("/accounts/{account_id}/disconnect")
async def disconnect_account(
    account_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if not _gmail.disconnect_account(db, user, account_id):
        raise HTTPException(status_code=404, detail="Account not found")
    return {"message": "Account disconnected"}


@router.get("/settings")
async def get_email_settings(
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _gmail.get_email_settings(db, user, store_id)


@router.put("/settings")
async def update_email_settings(
    data: GmailEmailSettings,
    store_id: str | None = Query(default=None),
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return _gmail.update_email_settings(db, user, data, store_id)
