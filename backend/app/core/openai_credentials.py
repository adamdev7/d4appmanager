import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.crypto import decrypt_value, encrypt_value
from app.db.models import User, UserModuleOpenAIKey

OPENAI_MODULE_AI_EMAIL = "ai-email"
OPENAI_MODULE_AI_ADS = "ai-ads"
OPENAI_MODULE_ADS = "ads"

KNOWN_OPENAI_MODULES = (
    OPENAI_MODULE_AI_EMAIL,
    OPENAI_MODULE_AI_ADS,
    OPENAI_MODULE_ADS,
)

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


def _module_row(db: Session, user_id: str, module: str) -> UserModuleOpenAIKey | None:
    return db.scalar(
        select(UserModuleOpenAIKey).where(
            UserModuleOpenAIKey.user_id == user_id,
            UserModuleOpenAIKey.module_slug == module,
        )
    )


def _legacy_email_key(user: User) -> str | None:
    if not user.openai_api_key_encrypted:
        return None
    try:
        return decrypt_value(user.openai_api_key_encrypted)
    except ValueError:
        return None


def resolve_openai_api_key(db: Session, user: User, module: str) -> str | None:
    """Module-owned key first; email may fall back to legacy user columns; then server key."""
    row = _module_row(db, user.id, module)
    if row and row.api_key_encrypted:
        try:
            return decrypt_value(row.api_key_encrypted)
        except ValueError:
            pass
    if module == OPENAI_MODULE_AI_EMAIL:
        legacy = _legacy_email_key(user)
        if legacy:
            return legacy
    if settings.openai_api_key:
        return settings.openai_api_key
    return None


def is_openai_configured(db: Session, user: User, module: str) -> bool:
    return resolve_openai_api_key(db, user, module) is not None


def user_has_own_openai_key(db: Session, user: User, module: str) -> bool:
    row = _module_row(db, user.id, module)
    if row and row.api_key_encrypted:
        return True
    return module == OPENAI_MODULE_AI_EMAIL and bool(user.openai_api_key_encrypted)


def openai_key_status(db: Session, user: User, module: str) -> dict:
    configured = is_openai_configured(db, user, module)
    owned = user_has_own_openai_key(db, user, module)
    masked = None
    row = _module_row(db, user.id, module)
    if row and row.api_key_hint:
        masked = f"sk-••••{row.api_key_hint}"
    elif row and row.api_key_encrypted:
        try:
            masked = mask_openai_api_key(decrypt_value(row.api_key_encrypted))
        except ValueError:
            masked = "sk-••••••••"
    elif module == OPENAI_MODULE_AI_EMAIL and user.openai_api_key_hint:
        masked = f"sk-••••{user.openai_api_key_hint}"
    elif module == OPENAI_MODULE_AI_EMAIL and user.openai_api_key_encrypted:
        try:
            masked = mask_openai_api_key(decrypt_value(user.openai_api_key_encrypted))
        except ValueError:
            masked = "sk-••••••••"
    return {
        "openai_configured": configured,
        "openai_key_masked": masked,
        "openai_key_is_user_owned": owned,
        "openai_uses_server_fallback": configured and not owned,
    }


def set_module_openai_api_key(db: Session, user: User, module: str, api_key: str) -> None:
    if module not in KNOWN_OPENAI_MODULES:
        raise ValueError("Unknown OpenAI module")
    validate_openai_api_key_format(api_key)
    plain = api_key.strip()
    encrypted = encrypt_value(plain)
    hint = plain[-4:] if len(plain) >= 4 else None
    row = _module_row(db, user.id, module)
    if not row:
        row = UserModuleOpenAIKey(user_id=user.id, module_slug=module)
        db.add(row)
    row.api_key_encrypted = encrypted
    row.api_key_hint = hint
    if module == OPENAI_MODULE_AI_EMAIL:
        user.openai_api_key_encrypted = encrypted
        user.openai_api_key_hint = hint
    db.commit()
    db.refresh(user)


def clear_module_openai_api_key(db: Session, user: User, module: str) -> None:
    if module not in KNOWN_OPENAI_MODULES:
        raise ValueError("Unknown OpenAI module")
    row = _module_row(db, user.id, module)
    if row:
        db.delete(row)
    if module == OPENAI_MODULE_AI_EMAIL:
        user.openai_api_key_encrypted = None
        user.openai_api_key_hint = None
    db.commit()
    db.refresh(user)


def set_user_openai_api_key(db: Session, user: User, api_key: str) -> None:
    """Back-compat: email assistant key."""
    set_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL, api_key)


def clear_user_openai_api_key(db: Session, user: User) -> None:
    """Back-compat: email assistant key."""
    clear_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL)
