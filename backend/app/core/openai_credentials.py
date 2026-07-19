import re

from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import User

_OPENAI_KEY_PATTERN = re.compile(r"^sk-[A-Za-z0-9_-]{20,}$")


def mask_openai_api_key(api_key: str) -> str:
    if len(api_key) <= 11:
        return "sk-••••••••"
    return f"{api_key[:7]}••••{api_key[-4:]}"


def validate_openai_api_key_format(api_key: str) -> None:
    key = api_key.strip()
    if not _OPENAI_KEY_PATTERN.match(key):
        raise ValueError(
            "Invalid OpenAI API key format. Keys start with sk- and come from platform.openai.com"
        )


def resolve_openai_api_key(user: User) -> str | None:
    """User key first; optional server OPENAI_API_KEY for local/dev only."""
    if user.openai_api_key_encrypted:
        return decrypt_value(user.openai_api_key_encrypted)
    if settings.openai_api_key:
        return settings.openai_api_key
    return None


def is_openai_configured(user: User) -> bool:
    return resolve_openai_api_key(user) is not None


def user_has_own_openai_key(user: User) -> bool:
    return bool(user.openai_api_key_encrypted)


def openai_key_status(user: User) -> dict:
    configured = is_openai_configured(user)
    masked = None
    if user.openai_api_key_hint:
        masked = f"sk-••••{user.openai_api_key_hint}"
    elif user.openai_api_key_encrypted:
        try:
            masked = mask_openai_api_key(decrypt_value(user.openai_api_key_encrypted))
        except ValueError:
            masked = "sk-••••••••"
    return {
        "openai_configured": configured,
        "openai_key_masked": masked,
        "openai_key_is_user_owned": user_has_own_openai_key(user),
        "openai_uses_server_fallback": configured and not user_has_own_openai_key(user),
    }


def set_user_openai_api_key(db: Session, user: User, api_key: str) -> None:
    validate_openai_api_key_format(api_key)
    plain = api_key.strip()
    user.openai_api_key_encrypted = encrypt_value(plain)
    user.openai_api_key_hint = plain[-4:] if len(plain) >= 4 else None
    db.commit()
    db.refresh(user)


def clear_user_openai_api_key(db: Session, user: User) -> None:
    user.openai_api_key_encrypted = None
    user.openai_api_key_hint = None
    db.commit()
    db.refresh(user)
