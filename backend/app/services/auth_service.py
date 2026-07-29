import logging
import secrets
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.config import settings
from app.core.email import (
    generate_verification_code,
    send_login_code_email,
    send_verification_email,
)
from app.core.security import (
    create_access_token,
    hash_code,
    hash_password,
    verify_code,
    verify_password,
)
from app.db.models import User, VerificationCode, VerificationPurpose
from app.integrations.google_auth import GoogleAuthClient
from app.models.user import UserCreate, UserLogin

logger = logging.getLogger(__name__)


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

    def _normalize_email(self, email: str) -> str:
        return email.lower().strip()

    def _aware(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt

    def _invalidate_unused_codes(self, db: Session, user_id: str, purpose: str) -> None:
        db.execute(
            update(VerificationCode)
            .where(
                VerificationCode.user_id == user_id,
                VerificationCode.purpose == purpose,
                VerificationCode.used_at.is_(None),
            )
            .values(used_at=datetime.now(UTC))
        )

    async def _send_code(
        self,
        db: Session,
        user: User,
        purpose: str,
    ) -> None:
        self._invalidate_unused_codes(db, user.id, purpose)
        code = generate_verification_code()
        expires = datetime.now(UTC) + timedelta(minutes=settings.verification_code_expire_minutes)
        db.add(
            VerificationCode(
                user_id=user.id,
                code_hash=hash_code(code),
                purpose=purpose,
                expires_at=expires,
                attempt_count=0,
            )
        )
        db.commit()

        try:
            if purpose == VerificationPurpose.LOGIN_2FA.value:
                await send_login_code_email(user.email, code, user.full_name)
            else:
                await send_verification_email(user.email, code, user.full_name)
        except Exception as exc:
            logger.exception("Failed to send %s email to %s", purpose, user.email)
            if not settings.debug:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Could not send verification email. Check SMTP settings or try again later.",
                ) from exc

        if settings.debug:
            label = "LOGIN 2FA" if purpose == VerificationPurpose.LOGIN_2FA.value else "VERIFICATION"
            print(f"\n>>> {label} CODE for {user.email}: {code} <<<\n")

    def _consume_code(self, db: Session, user: User, purpose: str, code: str) -> None:
        row = db.scalar(
            select(VerificationCode)
            .where(
                VerificationCode.user_id == user.id,
                VerificationCode.purpose == purpose,
                VerificationCode.used_at.is_(None),
            )
            .order_by(VerificationCode.created_at.desc())
        )
        if not row:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No active verification code. Request a new one.",
            )

        if self._aware(row.expires_at) < datetime.now(UTC):
            row.used_at = datetime.now(UTC)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Code expired. Request a new one.",
            )

        if row.attempt_count >= settings.verification_code_max_attempts:
            row.used_at = datetime.now(UTC)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Too many incorrect attempts. Request a new code.",
            )

        cleaned = "".join(ch for ch in code.strip() if ch.isdigit())
        if len(cleaned) != settings.verification_code_length or not verify_code(
            cleaned, row.code_hash
        ):
            row.attempt_count = int(row.attempt_count or 0) + 1
            if row.attempt_count >= settings.verification_code_max_attempts:
                row.used_at = datetime.now(UTC)
                db.commit()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Too many incorrect attempts. Request a new code.",
                )
            db.commit()
            remaining = settings.verification_code_max_attempts - row.attempt_count
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid verification code. {remaining} attempt(s) remaining.",
            )

        row.used_at = datetime.now(UTC)
        db.commit()

    async def register(self, db: Session, data: UserCreate) -> dict:
        email = self._normalize_email(data.email)
        existing = db.scalar(select(User).where(User.email == email))
        if existing:
            if not existing.is_verified:
                # Require password ownership before re-sending codes for an unverified account
                if not verify_password(data.password, existing.password_hash):
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Email already registered",
                    )
                await self._send_code(db, existing, VerificationPurpose.EMAIL_VERIFY.value)
                return {
                    "message": "Account exists but is not verified. A new code was sent to your email.",
                    "requires_verification": True,
                    "email": existing.email,
                }
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

        user = User(
            email=email,
            password_hash=hash_password(data.password),
            full_name=data.full_name.strip(),
            is_verified=False,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        await self._send_code(db, user, VerificationPurpose.EMAIL_VERIFY.value)
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

    async def verify_email(self, db: Session, email: str, code: str) -> dict:
        user = db.scalar(select(User).where(User.email == self._normalize_email(email)))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )
        if user.is_verified:
            # Do NOT issue a token without proving a fresh code / password.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email is already verified. Sign in to continue.",
            )

        self._consume_code(db, user, VerificationPurpose.EMAIL_VERIFY.value, code)
        user.is_verified = True
        db.commit()
        db.refresh(user)
        return self._token_response(user)

    async def resend_verification(self, db: Session, email: str) -> dict:
        user = db.scalar(select(User).where(User.email == self._normalize_email(email)))
        # Anti-enumeration: same message whether or not the account exists
        generic = {"message": "If an account needs verification, a code was sent."}
        if not user or user.is_verified or not user.is_active:
            return generic
        await self._send_code(db, user, VerificationPurpose.EMAIL_VERIFY.value)
        return {"message": "If an account needs verification, a code was sent."}

    async def login(self, db: Session, data: UserLogin) -> dict:
        email = self._normalize_email(data.email)
        user = db.scalar(select(User).where(User.email == email))
        if not user or not verify_password(data.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled",
            )
        if not user.is_verified:
            await self._send_code(db, user, VerificationPurpose.EMAIL_VERIFY.value)
            return {
                "requires_verification": True,
                "requires_2fa": False,
                "email": user.email,
                "message": "Email not verified. A new code was sent to your email.",
            }

        await self._send_code(db, user, VerificationPurpose.LOGIN_2FA.value)
        payload = {
            "requires_2fa": True,
            "requires_verification": False,
            "email": user.email,
            "message": "Enter the 6-digit code we sent to your email to finish signing in.",
        }
        if settings.debug:
            payload["dev_hint"] = (
                "If you do not see an email, open the API server terminal — "
                "your login code is printed there while DEBUG=true."
            )
        return payload

    async def verify_login(self, db: Session, email: str, code: str) -> dict:
        user = db.scalar(select(User).where(User.email == self._normalize_email(email)))
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code",
            )
        if not user.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email not verified. Complete registration first.",
            )

        self._consume_code(db, user, VerificationPurpose.LOGIN_2FA.value, code)
        return self._token_response(user)

    async def resend_login_code(self, db: Session, email: str) -> dict:
        user = db.scalar(select(User).where(User.email == self._normalize_email(email)))
        generic = {"message": "If your account can sign in, a new code was sent."}
        if not user or not user.is_active or not user.is_verified:
            return generic
        await self._send_code(db, user, VerificationPurpose.LOGIN_2FA.value)
        return generic

    async def request_password_reset(self, db: Session, email: str) -> dict:
        # Phase 2: send reset code (keep anti-enumeration response)
        _ = db, email
        return {"message": "If an account exists, a reset link has been sent."}

    def get_user(self, user: User) -> dict:
        return self._user_response(user)

    def begin_google_auth(self) -> dict:
        if not settings.google_client_id or not settings.google_client_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google sign-in is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
            )
        try:
            state = GoogleAuthClient.create_state()
            return {"authorize_url": GoogleAuthClient.build_authorize_url(state)}
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    async def complete_google_auth(self, db: Session, code: str, state: str) -> dict:
        """Create or sign in a user via Google, then return a token response."""
        if not GoogleAuthClient.verify_state(state):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired Google sign-in session. Try again.",
            )

        try:
            token_data = await GoogleAuthClient.exchange_code_for_token(code)
        except Exception as exc:
            logger.exception("Google token exchange failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google sign-in failed. Please try again.",
            ) from exc

        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google did not return an access token.",
            )

        try:
            info = await GoogleAuthClient.fetch_userinfo(access_token)
        except Exception as exc:
            logger.exception("Google userinfo fetch failed")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not read your Google account. Please try again.",
            ) from exc

        raw_email = (info.get("email") or "").strip()
        if not raw_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google account has no email address.",
            )
        if info.get("verified_email") is False:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Google email is not verified. Use a verified Google account.",
            )

        email = self._normalize_email(raw_email)
        full_name = (info.get("name") or "").strip() or email.split("@")[0]

        user = db.scalar(select(User).where(User.email == email))
        if user:
            if not user.is_active:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Account is disabled",
                )
            if not user.is_verified:
                user.is_verified = True
            if full_name and (not user.full_name or user.full_name == user.email.split("@")[0]):
                user.full_name = full_name
            db.commit()
            db.refresh(user)
            return self._token_response(user)

        user = User(
            email=email,
            # Unusable random password — Google is the credential for this account
            password_hash=hash_password(secrets.token_urlsafe(48)),
            full_name=full_name,
            is_verified=True,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return self._token_response(user)

    def google_auth_frontend_redirect(self, token_payload: dict) -> str:
        token = quote(token_payload["access_token"], safe="")
        return f"{settings.frontend_url.rstrip('/')}/auth/google/callback?token={token}"

    def google_auth_error_redirect(self, message: str) -> str:
        return (
            f"{settings.frontend_url.rstrip('/')}/login"
            f"?error={quote(message, safe='')}"
        )
