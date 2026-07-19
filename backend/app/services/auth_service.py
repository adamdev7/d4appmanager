import logging
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status

logger = logging.getLogger(__name__)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.core.email import generate_verification_code, send_verification_email
from app.core.security import (
    create_access_token,
    hash_code,
    hash_password,
    verify_code,
    verify_password,
)
from app.db.models import User, VerificationCode, VerificationPurpose
from app.models.user import UserCreate, UserLogin


class AuthService:
    def _user_response(self, user: User) -> dict:
        return {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "is_verified": user.is_verified,
        }

    def _token_response(self, user: User) -> dict:
        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": self._user_response(user),
        }

    async def register(self, db: Session, data: UserCreate) -> dict:
        existing = db.scalar(select(User).where(User.email == data.email.lower()))
        if existing:
            if not existing.is_verified:
                await self._send_verification(db, existing)
                return {
                    "message": "Account exists but is not verified. A new code was sent to your email.",
                    "requires_verification": True,
                    "email": existing.email,
                }
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = User(
            email=data.email.lower().strip(),
            password_hash=hash_password(data.password),
            full_name=data.full_name.strip(),
            is_verified=False,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        await self._send_verification(db, user)
        payload = {
            "message": "Verification code sent to your email.",
            "requires_verification": True,
            "email": user.email,
        }
        if settings.debug:
            payload["dev_hint"] = (
                "If you do not see an email, open the API server terminal — "
                "your 6-digit code is printed there while DEBUG=true."
            )
        return payload

    async def _send_verification(self, db: Session, user: User) -> None:
        code = generate_verification_code()
        expires = datetime.now(UTC) + timedelta(minutes=settings.verification_code_expire_minutes)
        db.add(
            VerificationCode(
                user_id=user.id,
                code_hash=hash_code(code),
                purpose=VerificationPurpose.EMAIL_VERIFY.value,
                expires_at=expires,
            )
        )
        db.commit()
        try:
            await send_verification_email(user.email, code, user.full_name)
        except Exception as exc:
            logger.exception("Failed to send verification email to %s", user.email)
            if not settings.debug:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not send verification email. Check SMTP settings or try again later.",
                ) from exc

        if settings.debug:
            print(f"\n>>> VERIFICATION CODE for {user.email}: {code} <<<\n")

    async def verify_email(self, db: Session, email: str, code: str) -> dict:
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

        if user.is_verified:
            return self._token_response(user)

        row = db.scalar(
            select(VerificationCode)
            .where(
                VerificationCode.user_id == user.id,
                VerificationCode.purpose == VerificationPurpose.EMAIL_VERIFY.value,
                VerificationCode.used_at.is_(None),
            )
            .order_by(VerificationCode.created_at.desc())
        )
        if not row:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No active verification code")

        expires = row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires < datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired. Request a new one.")

        if not verify_code(code.strip(), row.code_hash):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")

        row.used_at = datetime.now(UTC)
        user.is_verified = True
        db.commit()
        db.refresh(user)
        return self._token_response(user)

    async def resend_verification(self, db: Session, email: str) -> dict:
        user = db.scalar(select(User).where(User.email == email.lower().strip()))
        if not user:
            return {"message": "If an account exists, a verification code was sent."}
        if user.is_verified:
            return {"message": "Account is already verified. You can sign in."}
        await self._send_verification(db, user)
        return {"message": "Verification code sent."}

    async def login(self, db: Session, data: UserLogin) -> dict:
        user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_verified:
            await self._send_verification(db, user)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Email not verified. A new code was sent to your email.",
            )
        return self._token_response(user)

    async def request_password_reset(self, db: Session, email: str) -> dict:
        # Phase 2: send reset code
        return {"message": "If an account exists, a reset link has been sent."}

    def get_user(self, user: User) -> dict:
        return self._user_response(user)
