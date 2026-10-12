"""
Create (or reset the password of) the account Shopify App Store reviewers sign in with.

    cd backend
    .venv/bin/python create_review_account.py appreview@appmanager.store

The password is generated and printed once. Put the email in REVIEW_ACCOUNT_EMAILS in .env and
restart the API so this account signs in without the emailed login code.
"""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.models import User  # noqa: E402
from app.db.session import SessionLocal, init_db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("email")
    parser.add_argument("--name", default="Shopify App Review")
    args = parser.parse_args()

    email = args.email.strip().lower()
    password = secrets.token_urlsafe(12)

    init_db()
    db = SessionLocal()
    try:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, full_name=args.name, password_hash="")
            db.add(user)
        user.password_hash = hash_password(password)
        user.is_verified = True
        user.is_active = True
        db.commit()
    finally:
        db.close()

    print(f"\n  Review account ready\n  Email:    {email}\n  Password: {password}\n")
    if email not in settings.review_account_email_set:
        print(f"  Add REVIEW_ACCOUNT_EMAILS={email} to backend/.env and restart the API,")
        print("  otherwise sign-in still asks for the emailed code.\n")


if __name__ == "__main__":
    main()
