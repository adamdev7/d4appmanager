from pydantic import BaseModel, EmailStr, Field


class User(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    is_active: bool = True
    is_verified: bool = False


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
