import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings

_fernet: Fernet | None = None


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is not None:
        return _fernet
    key = settings.encryption_key
    if not key:
        # Derive a dev-only key from JWT secret (set ENCRYPTION_KEY in production)
        digest = hashlib.sha256(settings.jwt_secret_key.encode()).digest()
        key = base64.urlsafe_b64encode(digest)
    else:
        key = key.encode() if isinstance(key, str) else key
    _fernet = Fernet(key)
    return _fernet


def encrypt_value(plain: str) -> str:
    return _get_fernet().encrypt(plain.encode()).decode()


def decrypt_value(token: str) -> str:
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Failed to decrypt stored credential") from e
