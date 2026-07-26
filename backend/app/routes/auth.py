from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
from app.config import settings
from app.core.rate_limit import enforce_auth_rate_limit
from app.db.models import User
from app.db.session import get_db
from app.models.user import UserCreate, UserLogin
from app.services.auth_service import AuthService

router = APIRouter()
_auth = AuthService()


class PasswordResetRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class VerifyLoginRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=4, max_length=12)


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendLoginCodeRequest(BaseModel):
    email: EmailStr


@router.post("/register")
async def register(data: UserCreate, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(
        request,
        action="register",
        email=data.email,
        limit=settings.auth_login_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    return await _auth.register(db, data)


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(
        request,
        action="verify-email",
        email=data.email,
        limit=settings.auth_otp_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    return await _auth.verify_email(db, data.email, data.code)


@router.post("/resend-verification")
async def resend_verification(
    data: ResendVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    enforce_auth_rate_limit(
        request,
        action="resend-verification",
        email=data.email,
        limit=5,
        window_seconds=settings.auth_rate_window_seconds * 2,
    )
    return await _auth.resend_verification(db, data.email)


@router.post("/login")
async def login(data: UserLogin, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(
        request,
        action="login",
        email=data.email,
        limit=settings.auth_login_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    return await _auth.login(db, data)


@router.post("/verify-login")
async def verify_login(data: VerifyLoginRequest, request: Request, db: Session = Depends(get_db)):
    enforce_auth_rate_limit(
        request,
        action="verify-login",
        email=data.email,
        limit=settings.auth_otp_rate_limit,
        window_seconds=settings.auth_rate_window_seconds,
    )
    return await _auth.verify_login(db, data.email, data.code)


@router.post("/resend-login-code")
async def resend_login_code(
    data: ResendLoginCodeRequest, request: Request, db: Session = Depends(get_db)
):
    enforce_auth_rate_limit(
        request,
        action="resend-login-code",
        email=data.email,
        limit=5,
        window_seconds=settings.auth_rate_window_seconds * 2,
    )
    return await _auth.resend_login_code(db, data.email)


@router.post("/forgot-password")
async def forgot_password(
    data: PasswordResetRequest, request: Request, db: Session = Depends(get_db)
):
    enforce_auth_rate_limit(
        request,
        action="forgot-password",
        email=data.email,
        limit=5,
        window_seconds=settings.auth_rate_window_seconds * 2,
    )
    return await _auth.request_password_reset(db, data.email)


@router.get("/me")
async def me(user: User = Depends(get_verified_user)):
    return _auth.get_user(user)
