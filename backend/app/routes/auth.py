from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..config import settings
from ..db import get_db
from ..models import User
from ..schemas import TokenOut, DevLoginIn, RegisterIn, LoginIn
from ..auth import (
    PasswordValidationError,
    create_access_token,
    hash_password,
    verify_password,
    get_authorization,
    decode_token,
    revoke_jti,
    get_current_user,
    validate_password_policy,
)
from ..config import Settings
from ..rate_limit import check_rate_limit


def build_router(current_settings: Settings | None = None) -> APIRouter:
    cfg = current_settings or settings
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register")
    def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict[str, Any]:
        email = body.email.lower().strip()
        pw = body.password
        try:
            validate_password_policy(pw)
        except PasswordValidationError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        if db.query(User).filter(User.email == email).first():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
        user = User(
            email=email,
            hashed_password=hash_password(pw),
            is_active=True,
            email_verified=False,
            is_admin=False,
        )
        db.add(user)
        db.commit()
        return {"ok": True}

    @router.post("/login", response_model=TokenOut)
    def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
        email = body.email.lower().strip()
        # Throttle login attempts per email to mitigate brute force.
        check_rate_limit(f"login:{email}", cfg.LOGIN_RATE_LIMIT_PER_MINUTE)
        user = db.query(User).filter(User.email == email).one_or_none()
        if not user or not verify_password(body.password, user.hashed_password) or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token(user_id=user.id, email=user.email)
        return TokenOut(access_token=token)

    # Dev login endpoint - only available in non-production environments
    if cfg.ALLOW_DEV_LOGIN and cfg.ENVIRONMENT != "production":

        @router.post("/token", response_model=TokenOut, include_in_schema=(cfg.ENVIRONMENT != "production"))
        def dev_login(body: DevLoginIn, db: Session = Depends(get_db)) -> TokenOut:
            """
            Dev-only login endpoint. NOT AVAILABLE IN PRODUCTION.
            Creates or gets a user by email without password verification.
            """
            user = db.query(User).filter(User.email == body.email.lower()).one_or_none()
            if not user:
                # hashed_password defaults to '', enforced in DB with server_default
                user = User(
                    email=body.email.lower().strip(),
                    hashed_password="",
                    is_active=True,
                    email_verified=False,
                    is_admin=False,
                )
                db.add(user)
                db.commit()  # Explicit commit to ensure user exists before token creation
                db.refresh(user)  # Refresh to ensure all DB defaults are loaded

            token = create_access_token(user_id=user.id, email=user.email)
            return TokenOut(access_token=token)

    @router.post("/logout")
    def logout(token: str = Depends(get_authorization), user: User = Depends(get_current_user)) -> dict[str, Any]:
        """
        Logout endpoint. Revokes the current JWT token by adding its JTI to the revocation list.
        The token will be invalid until its natural expiration.
        """
        try:
            payload = decode_token(token)
            jti = payload.get("jti")
            exp = payload.get("exp", 0)
            if jti:
                revoke_jti(jti, exp)
        except Exception:
            # Even if revocation fails, return success (user intent is clear)
            pass
        return {"ok": True, "message": "Logged out successfully"}

    return router


# Export default router built from global settings
router = build_router()
