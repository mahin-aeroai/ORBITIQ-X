"""
ORBITIQ-X — Security Core
==========================
JWT token generation/verification and password hashing.

Uses existing dependencies (verified in requirements/base.txt):
  python-jose[cryptography]==3.3.0
  passlib[bcrypt]==1.7.4

Uses existing config fields (verified in config.py):
  ORBITIQ_SECRET_KEY
  BACKEND_JWT_ALGORITHM        (default: HS256)
  BACKEND_JWT_EXPIRE_MINUTES   (default: 60)
  BACKEND_JWT_REFRESH_EXPIRE_DAYS (default: 7)

Token scheme
─────────────
  Access token:   short-lived (default 60 min), carries role + user_id
  Refresh token:  long-lived (default 7 days), opaque UUID stored hashed in DB
  Rotation:       each /auth/refresh call issues a new refresh token and
                  revokes the old one (prevents refresh token reuse)

Password security
──────────────────
  bcrypt with work factor 12.
  Timing-safe comparison via passlib.
  Account lockout after 5 consecutive failures (checked at login time).
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

# ── Password context ──────────────────────────────────────────

_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


def hash_password(plain: str) -> str:
    """Hash a plain-text password with bcrypt (work factor 12)."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Timing-safe bcrypt verification."""
    return _pwd_context.verify(plain, hashed)


# ── Token claims ──────────────────────────────────────────────

class TokenType:
    ACCESS  = "access"
    REFRESH = "refresh"


# ── Access token ──────────────────────────────────────────────

def create_access_token(
    user_id:  int,
    email:    str,
    username: str,
    role:     str,
    *,
    expire_minutes: int | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Claims
    ──────
    sub      — user_id (string per JWT spec)
    email    — user email
    username — username
    role     — RBAC role (admin | operator | analyst | readonly)
    type     — "access"
    iat, exp — issued/expiry times
    jti      — unique token ID for revocation (future)
    """
    settings = get_settings()
    minutes  = expire_minutes or settings.BACKEND_JWT_EXPIRE_MINUTES
    now      = datetime.now(timezone.utc)
    exp      = now + timedelta(minutes=minutes)

    payload: dict[str, Any] = {
        "sub":      str(user_id),
        "email":    email,
        "username": username,
        "role":     role,
        "type":     TokenType.ACCESS,
        "iat":      int(now.timestamp()),
        "exp":      int(exp.timestamp()),
        "jti":      str(uuid.uuid4()),
    }
    return jwt.encode(
        payload,
        settings.ORBITIQ_SECRET_KEY.get_secret_value(),
        algorithm=settings.BACKEND_JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT access token.

    Raises
    ──────
    JWTError  — invalid signature, expired, or malformed
    ValueError — wrong token type
    """
    settings = get_settings()
    payload  = jwt.decode(
        token,
        settings.ORBITIQ_SECRET_KEY.get_secret_value(),
        algorithms=[settings.BACKEND_JWT_ALGORITHM],
    )
    if payload.get("type") != TokenType.ACCESS:
        raise ValueError("Not an access token")
    return payload


# ── Refresh token ─────────────────────────────────────────────

def generate_refresh_token() -> str:
    """
    Generate a cryptographically secure opaque refresh token.
    The raw token is returned to the client; only its hash is stored in DB.
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """SHA-256 hash of the raw refresh token for DB storage."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def refresh_token_expiry(days: int | None = None) -> datetime:
    """Return UTC expiry datetime for a refresh token."""
    settings = get_settings()
    d        = days or settings.BACKEND_JWT_REFRESH_EXPIRE_DAYS
    return datetime.now(timezone.utc) + timedelta(days=d)


# ── Utility ───────────────────────────────────────────────────

def extract_user_id(token: str) -> int | None:
    """Extract user_id from token without raising on expiry (for refresh flow)."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.ORBITIQ_SECRET_KEY.get_secret_value(),
            algorithms=[settings.BACKEND_JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        return int(payload["sub"])
    except Exception:
        return None
