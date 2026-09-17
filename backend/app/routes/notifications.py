"""Owner notification settings. WhatsApp connection lives here — not on module PUT."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.notifications.whatsapp import (
    WhatsAppConfigError,
    format_connection_test_message,
    get_or_create_whatsapp_connection,
    save_whatsapp_connection,
    send_user_whatsapp,
    whatsapp_public_payload,
)

router = APIRouter()


class WhatsAppConnectionUpdate(BaseModel):
    phone: str | None = None
    api_key: str | None = None


class WhatsAppTestResponse(BaseModel):
    ok: bool
    message: str
    whatsapp_configured: bool = False
    whatsapp_phone: str = ""
    whatsapp_api_key_hint: str | None = None
    whatsapp_last_error: str | None = None
    whatsapp_setup_url: str = ""
    whatsapp_allow_message: str = ""
    whatsapp_connected_modules: list[str] = []


def _save_or_400(db: Session, user: User, body: WhatsAppConnectionUpdate) -> None:
    try:
        save_whatsapp_connection(db, user, phone=body.phone, api_key=body.api_key)
    except WhatsAppConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/whatsapp")
async def get_whatsapp_settings(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return whatsapp_public_payload(db, user)


@router.put("/whatsapp")
async def update_whatsapp_settings(
    body: WhatsAppConnectionUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _save_or_400(db, user, body)
    db.commit()
    return whatsapp_public_payload(db, user)


@router.post("/whatsapp/test", response_model=WhatsAppTestResponse)
async def test_whatsapp_settings(
    body: WhatsAppConnectionUpdate | None = None,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    """Save number/key if provided, then send a test WhatsApp."""
    payload = body or WhatsAppConnectionUpdate()
    if payload.phone is not None or payload.api_key:
        _save_or_400(db, user, payload)
        db.commit()

    conn = get_or_create_whatsapp_connection(db, user)
    if not conn.phone:
        raise HTTPException(
            status_code=400,
            detail="Enter your WhatsApp number with the country code (example: +1 514 555 0100) and save.",
        )
    if not conn.api_key_encrypted:
        raise HTTPException(
            status_code=400,
            detail="Paste the CallMeBot API key you received on WhatsApp and save before testing.",
        )
    result = await send_user_whatsapp(db, user, text=format_connection_test_message())
    public = whatsapp_public_payload(db, user)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "WhatsApp test failed.")
    return WhatsAppTestResponse(
        ok=True,
        message="Test sent. Check WhatsApp — you should see a message from CallMeBot.",
        **public,
    )
