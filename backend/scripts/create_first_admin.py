"""
Create an initial admin user without enabling dev login.

Usage:
    python -m scripts.create_first_admin <email> <password>
"""

import sys
from app.db import SessionLocal
from app.auth import hash_password, validate_password_policy, PasswordValidationError
from app.models import User
from sqlalchemy import select


def main(email: str, password: str) -> None:
    try:
        validate_password_policy(password)
    except PasswordValidationError as exc:
        print(f"Invalid password: {exc}")
        return
    db = SessionLocal()
    try:
        existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing:
            print(f"User {email} already exists.")
            return
        user = User(
            email=email,
            hashed_password=hash_password(password),
            is_active=True,
            is_admin=True,
            email_verified=True,
        )
        db.add(user)
        db.commit()
        print(f"Admin {email} created successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.create_first_admin <email> <password>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
