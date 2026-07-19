from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import get_verified_user
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


class ResendVerificationRequest(BaseModel):
    email: EmailStr


@router.post("/register")
async def register(data: UserCreate, db: Session = Depends(get_db)):
    return await _auth.register(db, data)


@router.post("/verify-email")
async def verify_email(data: VerifyEmailRequest, db: Session = Depends(get_db)):
    return await _auth.verify_email(db, data.email, data.code)


@router.post("/resend-verification")
async def resend_verification(data: ResendVerificationRequest, db: Session = Depends(get_db)):
    return await _auth.resend_verification(db, data.email)


@router.post("/login")
async def login(data: UserLogin, db: Session = Depends(get_db)):
    return await _auth.login(db, data)


@router.post("/forgot-password")
async def forgot_password(data: PasswordResetRequest, db: Session = Depends(get_db)):
    return await _auth.request_password_reset(db, data.email)


@router.get("/me")
async def me(user: User = Depends(get_verified_user)):
    return _auth.get_user(user)
