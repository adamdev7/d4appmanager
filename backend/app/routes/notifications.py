"""Owner notification settings. WhatsApp connection lives here — not on module PUT."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.db.models import User
from app.db.session import get_db
from app.notifications.whatsapp import (
    WhatsAppConfigError,
    create_whatsapp_connection,
    delete_whatsapp_connection,
    format_connection_test_message,
    get_whatsapp_connection_by_id,
    save_whatsapp_connection,
    send_user_whatsapp,
    send_whatsapp_connection,
    whatsapp_public_payload,
)

router = APIRouter()


class WhatsAppConnectionItem(BaseModel):
    id: str
    label: str = ""
    phone: str = ""
    api_key_hint: str | None = None
    last_error: str | None = None
    configured: bool = False


class WhatsAppConnectionUpdate(BaseModel):
    id: str | None = None
    phone: str | None = None
    api_key: str | None = None
    label: str | None = None


class WhatsAppPublicResponse(BaseModel):
    whatsapp_configured: bool = False
    whatsapp_phone: str = ""
    whatsapp_api_key_hint: str | None = None
    whatsapp_last_error: str | None = None
    whatsapp_setup_url: str = ""
    whatsapp_allow_message: str = ""
    whatsapp_connected_modules: list[str] = []
    whatsapp_connections: list[WhatsAppConnectionItem] = []
    whatsapp_max_connections: int = 5


class WhatsAppTestResponse(WhatsAppPublicResponse):
    ok: bool
    message: str


def _save_or_400(db: Session, user: User, body: WhatsAppConnectionUpdate):
    try:
        if body.id:
            return save_whatsapp_connection(
                db,
                user,
                connection_id=body.id,
                phone=body.phone,
                api_key=body.api_key,
                label=body.label,
            )
        if body.phone and body.api_key:
            # New number with both fields → add (or update primary if none yet).
            public = whatsapp_public_payload(db, user)
            if public.get("whatsapp_configured"):
                return create_whatsapp_connection(
                    db,
                    user,
                    phone=body.phone,
                    api_key=body.api_key,
                    label=body.label,
                )
        return save_whatsapp_connection(
            db,
            user,
            phone=body.phone,
            api_key=body.api_key,
            label=body.label,
        )
    except WhatsAppConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/whatsapp", response_model=WhatsAppPublicResponse)
async def get_whatsapp_settings(
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    return whatsapp_public_payload(db, user)


@router.put("/whatsapp", response_model=WhatsAppPublicResponse)
async def update_whatsapp_settings(
    body: WhatsAppConnectionUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    _save_or_400(db, user, body)
    db.commit()
    return whatsapp_public_payload(db, user)


@router.post("/whatsapp", response_model=WhatsAppPublicResponse)
async def add_whatsapp_settings(
    body: WhatsAppConnectionUpdate,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    if not body.phone or not (body.api_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail="Enter a WhatsApp number and CallMeBot API key to add another phone.",
        )
    try:
        create_whatsapp_connection(
            db,
            user,
            phone=body.phone,
            api_key=body.api_key or "",
            label=body.label,
        )
    except WhatsAppConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return whatsapp_public_payload(db, user)


@router.delete("/whatsapp/{connection_id}", response_model=WhatsAppPublicResponse)
async def remove_whatsapp_settings(
    connection_id: str,
    user: User = Depends(get_verified_user),
    db: Session = Depends(get_db),
):
    try:
        delete_whatsapp_connection(db, user, connection_id)
    except WhatsAppConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    connection_id = payload.id

    if payload.phone is not None or payload.api_key or payload.label is not None:
        row = _save_or_400(db, user, payload)
        db.commit()
        connection_id = row.id

    if connection_id:
        conn = get_whatsapp_connection_by_id(db, user, connection_id)
        if not conn:
            raise HTTPException(status_code=400, detail="That WhatsApp number was not found.")
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
        result = await send_whatsapp_connection(
            db, user, connection_id, format_connection_test_message()
        )
    else:
        result = await send_user_whatsapp(db, user, text=format_connection_test_message())

    public = whatsapp_public_payload(db, user)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.error or "WhatsApp test failed.")
    return WhatsAppTestResponse(
        ok=True,
        message="Test queued. Check WhatsApp in a few seconds — CallMeBot is often not instant.",
        **public,
    )
