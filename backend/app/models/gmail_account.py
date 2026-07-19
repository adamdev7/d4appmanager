from enum import Enum

from pydantic import BaseModel, EmailStr


class GmailAccountStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    EXPIRED = "expired"


class GmailAccount(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    status: GmailAccountStatus = GmailAccountStatus.DISCONNECTED
    is_default_sender: bool = False
    store_ids: list[str] = []


class GmailEmailSettings(BaseModel):
    reply_to: EmailStr | None = None
    signature_html: str = ""
    track_opens: bool = False
    track_clicks: bool = False
    daily_send_limit: int = 500
