"""
ORBITIQ-X — Authentication API
================================
JWT-based authentication with refresh token rotation.

Endpoints
──────────
  POST /auth/login      — issue access + refresh tokens
  POST /auth/refresh    — rotate refresh token, issue new access token
  POST /auth/logout     — revoke refresh token session
  POST /auth/register   — create new user (admin only, or first-user bootstrap)
  GET  /auth/me         — current user profile
  GET  /auth/sessions   — list active sessions (admin only)
  POST /auth/change-password — change own password

Security design
────────────────
  • Access token:  JWT, signed HS256, 60-minute lifetime (configurable)
  • Refresh token: opaque 48-byte URL-safe random, stored as SHA-256 hash
  • Rotation:      each /refresh call revokes old session and creates new one
  • Lockout:       5 consecutive failed logins → 15-minute lockout
  • Audit:         all auth events written to audit_logs table

All endpoints are public except /auth/me, /auth/sessions, /auth/change-password,
and /auth/register (admin-only after first user exists).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.tokens import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from app.core.security.deps import (
    AdminOnly,
    AnyAuthUser,
    CurrentUser,
    log_auth_event,
    require_roles,
)
from app.db.models.audit_logs import AuditLog
from app.db.models.users import User, UserSession
from app.db.session import get_session

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Constants ─────────────────────────────────────────────────

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES   = 15


# ── Request / Response schemas ───────────────────────────────

class LoginRequest(BaseModel):
    username_or_email: str = Field(..., min_length=1)
    password:          str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token:  str
    refresh_token: str
    token_type:    str = "bearer"
    expires_in:    int   # seconds
    user: dict


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    email:    EmailStr
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name:    str | None = None
    organization: str | None = None
    role:         str        = Field(default="analyst",
                                     pattern=r"^(admin|operator|analyst|readonly)$")

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password:     str = Field(..., min_length=8, max_length=128)


# ── Helpers ───────────────────────────────────────────────────

def _user_dict(user: User) -> dict:
    return {
        "id":           user.id,
        "email":        user.email,
        "username":     user.username,
        "full_name":    user.full_name,
        "organization": user.organization,
        "role":         user.role,
        "is_active":    user.is_active,
        "last_login_at":user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at":   user.created_at.isoformat(),
    }


async def _create_session(
    session:       AsyncSession,
    user:          User,
    request:       Request,
) -> str:
    """
    Generate a refresh token, store hashed session, return raw token.
    """
    raw_token = generate_refresh_token()
    token_hash = hash_refresh_token(raw_token)
    expires    = refresh_token_expiry()

    db_session = UserSession(
        user_id    = user.id,
        token_hash = token_hash,
        user_agent = request.headers.get("user-agent", "")[:255],
        ip_address = request.client.host if request.client else None,
        expires_at = expires,
        revoked    = False,
    )
    session.add(db_session)
    await session.commit()
    return raw_token


# ── POST /auth/login ──────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and obtain JWT tokens",
    description=(
        "Exchange credentials for a short-lived access token and long-lived "
        "refresh token. The refresh token is stored hashed in the database. "
        "After 5 consecutive failures the account is locked for 15 minutes."
    ),
)
async def login(
    body:    LoginRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.core.config import get_settings
    settings = get_settings()

    # ── Find user by email or username ────────────────────────
    q = select(User).where(
        (User.email == body.username_or_email.lower()) |
        (User.username == body.username_or_email)
    )
    result = await session.execute(q)
    user   = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    # ── Generic failure handler (prevents user enumeration) ───
    async def _fail(audit_outcome: str = "failure", lock: bool = False) -> None:
        if user:
            # Increment failed count
            new_failed = (user.failed_login_count or 0) + 1
            locked_until = None
            if lock or new_failed >= MAX_FAILED_LOGINS:
                from datetime import timedelta
                locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
                new_failed   = 0   # Reset counter after lockout
            await session.execute(
                update(User)
                .where(User.id == user.id)
                .values(
                    failed_login_count=new_failed,
                    locked_until=locked_until,
                )
            )
            await session.commit()

        await log_auth_event(
            request, user, "login_failed", audit_outcome,
            detail=f"username_or_email={body.username_or_email[:64]}",
            session=session,
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user:
        await _fail()

    # ── Check lockout ─────────────────────────────────────────
    if user.locked_until and now < user.locked_until:
        remaining = int((user.locked_until - now).total_seconds() / 60)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account locked. Try again in {remaining} minutes.",
        )

    # ── Verify password ───────────────────────────────────────
    if not verify_password(body.password, user.hashed_password):
        await _fail()

    # ── Check account status ──────────────────────────────────
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled. Contact your administrator.",
        )

    # ── Issue tokens ──────────────────────────────────────────
    access_token  = create_access_token(
        user_id=user.id, email=user.email,
        username=user.username, role=user.role,
    )
    refresh_token = await _create_session(session, user, request)

    # ── Update user login stats ───────────────────────────────
    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(
            last_login_at      = now,
            login_count        = (user.login_count or 0) + 1,
            failed_login_count = 0,
            locked_until       = None,
        )
    )
    await session.commit()

    # ── Audit ─────────────────────────────────────────────────
    await log_auth_event(
        request, user, "login", "success",
        detail=f"role={user.role}",
        session=session,
    )

    logger.info("user_login user_id=%d role=%s", user.id, user.role)

    return ORJSONResponse(content={
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        "expires_in":    settings.BACKEND_JWT_EXPIRE_MINUTES * 60,
        "user":          _user_dict(user),
    })


# ── POST /auth/refresh ────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Rotate refresh token and issue new access token",
    description=(
        "Exchange a valid refresh token for a new access token and rotated "
        "refresh token. The old refresh token is immediately revoked. "
        "This prevents refresh token reuse attacks."
    ),
)
async def refresh_tokens(
    body:    RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    from app.core.config import get_settings
    settings = get_settings()

    token_hash = hash_refresh_token(body.refresh_token)
    now        = datetime.now(timezone.utc)

    # ── Find valid session ────────────────────────────────────
    q = (
        select(UserSession)
        .where(
            UserSession.token_hash == token_hash,
            UserSession.revoked    == False,   # noqa: E712
            UserSession.expires_at >  now,
        )
    )
    result     = await session.execute(q)
    db_session = result.scalar_one_or_none()

    if not db_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token is invalid, expired, or already used.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # ── Revoke old session ────────────────────────────────────
    await session.execute(
        update(UserSession)
        .where(UserSession.id == db_session.id)
        .values(revoked=True)
    )

    # ── Fetch user ────────────────────────────────────────────
    result = await session.execute(select(User).where(User.id == db_session.user_id))
    user   = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or disabled.",
        )

    # ── Issue new tokens ──────────────────────────────────────
    access_token  = create_access_token(
        user_id=user.id, email=user.email,
        username=user.username, role=user.role,
    )
    refresh_token = await _create_session(session, user, request)

    logger.info("token_refresh user_id=%d", user.id)

    return ORJSONResponse(content={
        "access_token":  access_token,
        "refresh_token": refresh_token,
        "token_type":    "bearer",
        "expires_in":    settings.BACKEND_JWT_EXPIRE_MINUTES * 60,
        "user":          _user_dict(user),
    })


# ── POST /auth/logout ─────────────────────────────────────────

@router.post(
    "/logout",
    summary="Revoke refresh token session",
    description="Revoke the supplied refresh token. The access token expires naturally.",
)
async def logout(
    body:    RefreshRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user:    AnyAuthUser  = None,  # optional — logout even with expired access token
) -> ORJSONResponse:
    token_hash = hash_refresh_token(body.refresh_token)

    await session.execute(
        update(UserSession)
        .where(UserSession.token_hash == token_hash)
        .values(revoked=True)
    )
    await session.commit()

    if user:
        await log_auth_event(
            request, user, "logout", "success", session=session,
        )

    return ORJSONResponse(content={"message": "Logged out successfully."})


# ── POST /auth/register ───────────────────────────────────────

@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description=(
        "Create a new platform user. "
        "If no users exist yet (bootstrap), the first user is created as admin "
        "without requiring authentication. "
        "After bootstrap, only admins may create new users."
    ),
)
async def register(
    body:    RegisterRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    # ── Bootstrap: allow first-user creation without auth ─────
    from sqlalchemy import func
    count_result = await session.execute(select(func.count()).select_from(User))
    first_user   = (count_result.scalar() or 0) == 0

    if not first_user:
        # Non-bootstrap: require admin token
        from app.core.security.deps import get_current_user
        from fastapi.security import HTTPBearer
        _bearer = HTTPBearer(auto_error=False)
        creds   = await _bearer(request)
        if not creds:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required to register new users.",
            )
        from app.core.security.tokens import decode_access_token
        try:
            payload = decode_access_token(creds.credentials)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token.",
            )
        if payload.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can register new users.",
            )

    # ── Check uniqueness ──────────────────────────────────────
    email_check = await session.execute(select(User).where(User.email == body.email.lower()))
    if email_check.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Email '{body.email}' already registered.")

    user_check = await session.execute(select(User).where(User.username == body.username))
    if user_check.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Username '{body.username}' already taken.")

    # ── Create user ───────────────────────────────────────────
    role = "admin" if first_user else body.role
    new_user = User(
        email           = body.email.lower(),
        username        = body.username,
        hashed_password = hash_password(body.password),
        full_name       = body.full_name,
        organization    = body.organization,
        role            = role,
        is_active       = True,
        is_verified     = False,
    )
    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    logger.info("user_registered id=%d role=%s bootstrap=%s", new_user.id, role, first_user)

    await log_auth_event(
        request, new_user, "user_registered", "success",
        detail=f"bootstrap={first_user} role={role}",
        session=session,
    )

    return ORJSONResponse(
        content={"message": "User created.", "user": _user_dict(new_user)},
        status_code=201,
    )


# ── GET /auth/me ──────────────────────────────────────────────

@router.get(
    "/me",
    summary="Get current user profile",
    description="Returns the profile of the currently authenticated user.",
)
async def get_me(user: AnyAuthUser) -> ORJSONResponse:
    return ORJSONResponse(content=_user_dict(user))


# ── POST /auth/change-password ────────────────────────────────

@router.post(
    "/change-password",
    summary="Change own password",
    description="Change the authenticated user's password. Current password is required.",
)
async def change_password(
    body:    ChangePasswordRequest,
    request: Request,
    user:    AnyAuthUser,
    session: AsyncSession = Depends(get_session),
) -> ORJSONResponse:
    if not verify_password(body.current_password, user.hashed_password):
        await log_auth_event(
            request, user, "password_change_failed", "failure",
            session=session,
        )
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    new_hash = hash_password(body.new_password)
    await session.execute(
        update(User)
        .where(User.id == user.id)
        .values(hashed_password=new_hash)
    )
    # Revoke all existing sessions (force re-login everywhere)
    await session.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id, UserSession.revoked == False)  # noqa
        .values(revoked=True)
    )
    await session.commit()

    await log_auth_event(
        request, user, "password_changed", "success", session=session,
    )

    return ORJSONResponse(content={"message": "Password changed. Please log in again."})


# ── GET /auth/sessions ────────────────────────────────────────

@router.get(
    "/sessions",
    summary="List active sessions (admin only)",
    description="Returns all active user sessions. Admin access required.",
)
async def list_sessions(
    _:       AdminOnly,
    session: AsyncSession = Depends(get_session),
    limit:   int          = 100,
) -> ORJSONResponse:
    now = datetime.now(timezone.utc)
    q   = (
        select(UserSession)
        .where(UserSession.revoked == False, UserSession.expires_at > now)  # noqa
        .order_by(UserSession.created_at.desc())
        .limit(limit)
    )
    result   = await session.execute(q)
    sessions = result.scalars().all()
    return ORJSONResponse(content={
        "count": len(sessions),
        "sessions": [
            {
                "id":         s.id,
                "user_id":    s.user_id,
                "ip_address": s.ip_address,
                "user_agent": s.user_agent,
                "expires_at": s.expires_at.isoformat(),
                "created_at": s.created_at.isoformat(),
            }
            for s in sessions
        ],
    })
