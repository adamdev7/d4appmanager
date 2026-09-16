from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.crypto import encrypt_value
from app.core.openai_credentials import (
    OPENAI_MODULE_ADS,
    OPENAI_MODULE_AI_ADS,
    OPENAI_MODULE_AI_EMAIL,
    clear_module_openai_api_key,
    is_openai_configured,
    resolve_openai_api_key,
    set_module_openai_api_key,
)
from app.db.models import User
from app.db.session import Base


EMAIL_KEY = "sk-" + "e" * 24
ADS_KEY = "sk-" + "a" * 24
AI_ADS_KEY = "sk-" + "i" * 24


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _user(db) -> User:
    user = User(
        email="owner@example.com",
        password_hash="x",
        full_name="Owner",
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def test_email_and_ai_ads_keys_are_independent():
    db = _session()
    user = _user(db)
    with patch("app.core.openai_credentials.settings") as settings:
        settings.openai_api_key = ""
        set_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL, EMAIL_KEY)
        set_module_openai_api_key(db, user, OPENAI_MODULE_AI_ADS, AI_ADS_KEY)

        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL) == EMAIL_KEY
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) == AI_ADS_KEY

        clear_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL)
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL) is None
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) == AI_ADS_KEY

        set_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL, EMAIL_KEY)
        clear_module_openai_api_key(db, user, OPENAI_MODULE_AI_ADS)
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL) == EMAIL_KEY
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) is None
        assert not is_openai_configured(db, user, OPENAI_MODULE_AI_ADS)


def test_ads_reports_key_is_independent_of_email():
    db = _session()
    user = _user(db)
    with patch("app.core.openai_credentials.settings") as settings:
        settings.openai_api_key = ""
        set_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL, EMAIL_KEY)
        set_module_openai_api_key(db, user, OPENAI_MODULE_ADS, ADS_KEY)
        clear_module_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL)
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_ADS) == ADS_KEY
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL) is None


def test_legacy_user_column_only_feeds_email_module():
    db = _session()
    user = _user(db)
    user.openai_api_key_encrypted = encrypt_value(EMAIL_KEY)
    user.openai_api_key_hint = EMAIL_KEY[-4:]
    db.commit()
    db.refresh(user)
    with patch("app.core.openai_credentials.settings") as settings:
        settings.openai_api_key = ""
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_EMAIL) == EMAIL_KEY
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_AI_ADS) is None
        assert resolve_openai_api_key(db, user, OPENAI_MODULE_ADS) is None
