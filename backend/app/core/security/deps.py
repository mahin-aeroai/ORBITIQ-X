"""
ORBITIQ-X — RBAC & Auth Dependencies
=======================================
FastAPI dependency-injection functions for JWT authentication
and role-based access control.

Role hierarchy (DB values → display names)
────────────────────────────────────────────
  admin     → ADMIN    — full platform access
  operator  → OPERATOR — SSA, Digital Twin, Conjunctions (read+write)
  analyst   → ANALYST  — analytics, graph, RAG, agents (read-only)
  readonly  → VIEWER   — dashboard metrics only (read-only)

Access matrix
──────────────
  /ssa/*                admin | operator
  /digital-twin/*       admin | operator
  /conjunctions/*       admin | operator
  /ssa-conjunctions/*   admin | operator
  /agents/*             admin | analyst
  /knowledge-graph/*    admin | analyst
  /rag/*                admin | analyst
  /foundation/*         admin
  /catalog/*            admin | operator
  /mission/*            admin | analyst | operator
  /space-weather/*      all authenticated
  /satellites/*         all authenticated
  /auth/*               public

Usage
──────
  from app.core.security.deps import CurrentUser, require_roles

  @router.get("/ssa/conjunctions")
  async def list_conjunctions(
      user: CurrentUser,                          # any authenticated user
      _:    Annotated[User, require_roles("admin", "operator")],
  ) -> ...:
      ...

  # Or use the pre-built guards:
  @router.get("/foundation/models")
  async def list_models(user: AdminOnly) -> ...:
      ...
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.tokens import decode_access_token
from app.db.models.users import User
from app.db.session import get_session

logger = logging.getLogger(__name__)

# ── Role constants (match DB values exactly) ──────────────────

class Role:
    ADMIN    = "admin"
    OPERATOR = "operator"
    ANALYST  = "analyst"
    READONLY = "readonly"   # DB name for VIEWER

    ALL = {ADMIN, OPERATOR, ANALYST, READONLY}


# Role hierarchy: each role has all permissions of roles below it
_ROLE_LEVEL: dict[str, int] = {
    Role.ADMIN:    4,
    Role.OPERATOR: 3,
    Role.ANALYST:  2,
    Role.READONLY: 1,
}


def _meets_min_role(user_role: str, min_role: str) -> bool:
    """True if user_role >= min_role in the hierarchy."""
    return _ROLE_LEVEL.get(user_role, 0) >= _ROLE_LEVEL.get(min_role, 99)


# ── Bearer token extractor ────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


async def _get_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> str:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


# ── Core auth dependency ──────────────────────────────────────

async def get_current_user(
    token:   Annotated[str, Depends(_get_token)],
    session: AsyncSession = Depends(get_session),
) -> User:
    """
    Validate Bearer token → return the active User row.

    Raises 401 for: missing token, invalid signature, expired, unknown user.
    Raises 403 for: inactive / locked account.
    """
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token is invalid or has expired. Please log in again.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
        user_id = int(payload["sub"])
    except (JWTError, ValueError, KeyError):
        raise credentials_error

    # Fetch live user record (checks active status + lockout)
    from sqlalchemy import select
    result = await session.execute(select(User).where(User.id == user_id))
    user   = result.scalar_one_or_none()

    if user is None:
        raise credentials_error

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled. Contact your administrator.",
        )

    # Check account lockout
    if user.locked_until is not None:
        from datetime import datetime, timezone
        if datetime.now(timezone.utc) < user.locked_until:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account temporarily locked due to too many failed login attempts.",
            )

    return user


# ── Type alias for annotated dependency ───────────────────────

CurrentUser = Annotated[User, Depends(get_current_user)]


# ── Role guard factory ────────────────────────────────────────

def require_roles(*allowed_roles: str):
    """
    Return a FastAPI dependency that enforces role membership.

    Usage::

        @router.get("/ssa/conjunctions")
        async def endpoint(
            user: Annotated[User, Depends(require_roles("admin", "operator"))],
        ) -> ...: ...
    """
    allowed = set(allowed_roles)

    async def _check(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. "
                    f"Required: one of {sorted(allowed)}. "
                    f"Your role: {user.role}."
                ),
            )
        return user

    return _check


def require_min_role(min_role: str):
    """
    Return a dependency that enforces role hierarchy (>= min_role).

    Usage::

        @router.delete("/catalog/sync")
        async def endpoint(
            user: Annotated[User, Depends(require_min_role("operator"))],
        ) -> ...: ...
    """
    async def _check(user: CurrentUser) -> User:
        if not _meets_min_role(user.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Insufficient permissions. "
                    f"Minimum required role: {min_role}. "
                    f"Your role: {user.role}."
                ),
            )
        return user

    return _check


# ── Pre-built role guards (convenience) ──────────────────────

AdminOnly     = Annotated[User, Depends(require_roles("admin"))]
OperatorPlus  = Annotated[User, Depends(require_min_role("operator"))]
AnalystPlus   = Annotated[User, Depends(require_min_role("analyst"))]
AnyAuthUser   = CurrentUser   # alias for readability


# ── Audit logger dependency ───────────────────────────────────

async def log_auth_event(
    request:  Request,
    user:     User | None,
    action:   str,
    outcome:  str = "success",
    detail:   str | None = None,
    session:  AsyncSession = None,  # type: ignore[assignment]
) -> None:
    """
    Write an audit record for security-relevant events.
    Swallows all errors — audit failure must never break the request path.
    """
    try:
        from app.db.models.audit_logs import AuditLog
        log = AuditLog(
            user_id         = user.id if user else None,
            username        = user.username if user else None,
            ip_address      = request.client.host if request.client else None,
            user_agent      = request.headers.get("user-agent", "")[:255],
            action          = action,
            outcome         = outcome,
            description     = detail,
            endpoint        = str(request.url.path),
            http_method     = request.method,
            request_id      = request.headers.get("x-request-id"),
        )
        if session:
            session.add(log)
            await session.commit()
    except Exception as exc:
        logger.warning("audit_log_failed action=%s error=%s", action, exc)
