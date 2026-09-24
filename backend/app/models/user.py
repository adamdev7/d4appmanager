from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool = True
    is_verified: bool = False
    email_notifications: bool = True
    weekly_digest: bool = False


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserProfileUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email_notifications: bool | None = None
    weekly_digest: bool | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
