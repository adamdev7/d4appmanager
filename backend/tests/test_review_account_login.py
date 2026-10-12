import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.core.security import hash_password
from app.db.models import User
from app.db.session import Base
from app.models.user import UserLogin
from app.services import auth_service
from app.services.auth_service import AuthService

PASSWORD = "review-pass-123"


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    for email in ("appreview@appmanager.store", "owner@example.com"):
        session.add(User(email=email, full_name="Test", password_hash=hash_password(PASSWORD), is_verified=True))
    session.commit()

    sent: list[str] = []

    async def fake_send(email, code, name):
        sent.append(email)

    monkeypatch.setattr(auth_service, "send_login_code_email", fake_send)
    monkeypatch.setattr(settings, "review_account_emails", " AppReview@appmanager.store ")
    session.sent = sent
    yield session
    session.close()


def test_review_account_signs_in_without_email_code(db):
    result = asyncio.run(AuthService().login(db, UserLogin(email="appreview@appmanager.store", password=PASSWORD)))
    assert result["access_token"]
    assert result["user"]["email"] == "appreview@appmanager.store"
    assert db.sent == []


def test_other_accounts_still_need_email_code(db):
    result = asyncio.run(AuthService().login(db, UserLogin(email="owner@example.com", password=PASSWORD)))
    assert result["requires_2fa"] is True
    assert "access_token" not in result
    assert db.sent == ["owner@example.com"]


def test_review_account_still_needs_correct_password(db):
    with pytest.raises(HTTPException) as exc:
        asyncio.run(AuthService().login(db, UserLogin(email="appreview@appmanager.store", password="wrong-password")))
    assert exc.value.status_code == 401
