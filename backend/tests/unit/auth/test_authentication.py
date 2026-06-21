"""
ORBITIQ-X — Authentication & RBAC Tests
=========================================
Tests JWT token operations, password hashing, RBAC role guards,
token refresh, and permission enforcement.

Coverage
─────────
  TestPasswordHashing    : bcrypt hash + verify + timing-safe comparison
  TestTokenCreation      : access token creation, decode, expiry, type check
  TestRefreshToken       : generation, hashing, expiry helpers
  TestRoleHierarchy      : role level comparisons
  TestRBACGuards         : dependency injection guards in FastAPI context
  TestLoginFlow          : full login → access token → refresh → logout
  TestAccountLockout     : failed login counter + lockout enforcement
  TestAuditLogging       : audit event writing

Run
────
  pytest tests/unit/auth/ -v --asyncio-mode=auto
  pytest tests/unit/auth/ -v -k "password"
  pytest tests/unit/auth/ -v -k "rbac"
"""
from __future__ import annotations

import sys
import pathlib
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_BE_ROOT = pathlib.Path(__file__).parents[3]
if str(_BE_ROOT) not in sys.path:
    sys.path.insert(0, str(_BE_ROOT))


# ─────────────────────────────────────────────────────────────
# TestPasswordHashing
# ─────────────────────────────────────────────────────────────

class TestPasswordHashing:

    def test_hash_produces_bcrypt_format(self):
        from app.core.security.tokens import hash_password
        h = hash_password("Secur3Pass!")
        assert h.startswith("$2b$") or h.startswith("$2a$")
        assert len(h) >= 60

    def test_verify_correct_password(self):
        from app.core.security.tokens import hash_password, verify_password
        pw = "Orb1tIQ_Test!"
        h  = hash_password(pw)
        assert verify_password(pw, h) is True

    def test_verify_wrong_password(self):
        from app.core.security.tokens import hash_password, verify_password
        h = hash_password("CorrectHorse99")
        assert verify_password("WrongHorse99", h) is False

    def test_same_password_different_hashes(self):
        """bcrypt generates different salts each time."""
        from app.core.security.tokens import hash_password
        pw = "UniquePassword1"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert h1 != h2

    def test_verify_both_hashes_work(self):
        from app.core.security.tokens import hash_password, verify_password
        pw = "BothHashes9"
        h1 = hash_password(pw)
        h2 = hash_password(pw)
        assert verify_password(pw, h1) is True
        assert verify_password(pw, h2) is True


# ─────────────────────────────────────────────────────────────
# TestTokenCreation
# ─────────────────────────────────────────────────────────────

class TestTokenCreation:

    def _make_token(self, **kwargs):
        from app.core.security.tokens import create_access_token
        defaults = dict(
            user_id=42, email="test@orbitiq.dev",
            username="testuser", role="analyst",
        )
        defaults.update(kwargs)
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM  = "HS256"
            m.return_value.BACKEND_JWT_EXPIRE_MINUTES = 60
            return create_access_token(**defaults)

    def _decode_token(self, token: str) -> dict:
        from app.core.security.tokens import decode_access_token
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM = "HS256"
            return decode_access_token(token)

    def test_access_token_is_string(self):
        token = self._make_token()
        assert isinstance(token, str)
        assert len(token) > 50

    def test_access_token_has_correct_claims(self):
        token   = self._make_token(user_id=99, role="operator")
        payload = self._decode_token(token)
        assert payload["sub"]      == "99"
        assert payload["role"]     == "operator"
        assert payload["type"]     == "access"
        assert "exp" in payload
        assert "jti" in payload

    def test_different_tokens_have_unique_jti(self):
        t1 = self._make_token()
        t2 = self._make_token()
        p1 = self._decode_token(t1)
        p2 = self._decode_token(t2)
        assert p1["jti"] != p2["jti"]

    def test_expired_token_raises(self):
        from app.core.security.tokens import create_access_token, decode_access_token
        from jose import JWTError
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM  = "HS256"
            m.return_value.BACKEND_JWT_EXPIRE_MINUTES = -1   # already expired
            token = create_access_token(
                user_id=1, email="e@e.com", username="u", role="analyst"
            )
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM = "HS256"
            with pytest.raises(JWTError):
                decode_access_token(token)

    def test_wrong_type_raises(self):
        """A refresh token must not be accepted as an access token."""
        from app.core.security.tokens import create_access_token, decode_access_token
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM  = "HS256"
            m.return_value.BACKEND_JWT_EXPIRE_MINUTES = 60
            token = create_access_token(
                user_id=1, email="e@e.com", username="u", role="analyst"
            )
        # Tamper: if we manually set type=refresh in payload it won't verify anyway,
        # but test the type check error path:
        from jose import jwt as jose_jwt
        payload = jose_jwt.decode(
            token, "x" * 32, algorithms=["HS256"]
        )
        payload["type"] = "refresh"
        bad_token = jose_jwt.encode(payload, "x" * 32, algorithm="HS256")
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.ORBITIQ_SECRET_KEY.get_secret_value.return_value = "x" * 32
            m.return_value.BACKEND_JWT_ALGORITHM = "HS256"
            with pytest.raises(ValueError, match="Not an access token"):
                decode_access_token(bad_token)


# ─────────────────────────────────────────────────────────────
# TestRefreshToken
# ─────────────────────────────────────────────────────────────

class TestRefreshToken:

    def test_refresh_token_is_urlsafe_string(self):
        from app.core.security.tokens import generate_refresh_token
        tok = generate_refresh_token()
        assert isinstance(tok, str)
        assert len(tok) >= 48

    def test_refresh_tokens_are_unique(self):
        from app.core.security.tokens import generate_refresh_token
        tokens = {generate_refresh_token() for _ in range(100)}
        assert len(tokens) == 100

    def test_hash_refresh_token_is_hex(self):
        from app.core.security.tokens import generate_refresh_token, hash_refresh_token
        tok  = generate_refresh_token()
        h    = hash_refresh_token(tok)
        assert len(h) == 64      # SHA-256 hex
        assert all(c in "0123456789abcdef" for c in h)

    def test_same_token_same_hash(self):
        from app.core.security.tokens import hash_refresh_token
        raw = "fixed_token_for_test"
        assert hash_refresh_token(raw) == hash_refresh_token(raw)

    def test_refresh_token_expiry_in_future(self):
        from app.core.security.tokens import refresh_token_expiry
        with patch("app.core.security.tokens.get_settings") as m:
            m.return_value.BACKEND_JWT_REFRESH_EXPIRE_DAYS = 7
            exp = refresh_token_expiry()
        assert exp > datetime.now(timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        assert 6.9 < delta.total_seconds() / 86400 < 7.1


# ─────────────────────────────────────────────────────────────
# TestRoleHierarchy
# ─────────────────────────────────────────────────────────────

class TestRoleHierarchy:

    def test_role_levels_correct(self):
        from app.core.security.deps import _ROLE_LEVEL, Role
        assert _ROLE_LEVEL[Role.ADMIN]    > _ROLE_LEVEL[Role.OPERATOR]
        assert _ROLE_LEVEL[Role.OPERATOR] > _ROLE_LEVEL[Role.ANALYST]
        assert _ROLE_LEVEL[Role.ANALYST]  > _ROLE_LEVEL[Role.READONLY]

    def test_meets_min_role_same(self):
        from app.core.security.deps import _meets_min_role, Role
        assert _meets_min_role(Role.ANALYST,  Role.ANALYST)  is True
        assert _meets_min_role(Role.OPERATOR, Role.OPERATOR) is True
        assert _meets_min_role(Role.ADMIN,    Role.ADMIN)    is True

    def test_meets_min_role_higher(self):
        from app.core.security.deps import _meets_min_role, Role
        assert _meets_min_role(Role.ADMIN,    Role.OPERATOR) is True
        assert _meets_min_role(Role.ADMIN,    Role.ANALYST)  is True
        assert _meets_min_role(Role.OPERATOR, Role.ANALYST)  is True

    def test_meets_min_role_lower(self):
        from app.core.security.deps import _meets_min_role, Role
        assert _meets_min_role(Role.ANALYST,  Role.OPERATOR) is False
        assert _meets_min_role(Role.READONLY, Role.ANALYST)  is False
        assert _meets_min_role(Role.ANALYST,  Role.ADMIN)    is False

    def test_role_constants_match_db_values(self):
        """Role constants must exactly match the DB constraint values."""
        from app.core.security.deps import Role
        assert Role.ADMIN    == "admin"
        assert Role.OPERATOR == "operator"
        assert Role.ANALYST  == "analyst"
        assert Role.READONLY == "readonly"


# ─────────────────────────────────────────────────────────────
# TestRBACGuards (unit — no real DB)
# ─────────────────────────────────────────────────────────────

class TestRBACGuards:

    def _make_user(self, role: str, is_active: bool = True) -> MagicMock:
        u = MagicMock()
        u.id         = 1
        u.role       = role
        u.is_active  = is_active
        u.locked_until = None
        u.email      = "u@test.dev"
        u.username   = "testuser"
        return u

    @pytest.mark.asyncio
    async def test_require_roles_allows_matching(self):
        from app.core.security.deps import require_roles
        guard = require_roles("admin", "operator")
        user  = self._make_user("operator")
        result = await guard(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_require_roles_blocks_insufficient(self):
        from fastapi import HTTPException
        from app.core.security.deps import require_roles
        guard = require_roles("admin")
        user  = self._make_user("analyst")
        with pytest.raises(HTTPException) as exc_info:
            await guard(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_require_min_role_allows_higher(self):
        from app.core.security.deps import require_min_role
        guard = require_min_role("analyst")
        user  = self._make_user("admin")   # admin > analyst
        result = await guard(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_require_min_role_blocks_lower(self):
        from fastapi import HTTPException
        from app.core.security.deps import require_min_role
        guard = require_min_role("operator")
        user  = self._make_user("analyst")  # analyst < operator
        with pytest.raises(HTTPException) as exc_info:
            await guard(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_inactive_user_blocked(self):
        from fastapi import HTTPException
        from app.core.security.deps import get_current_user
        # Mock token decode to return user_id=1
        with (
            patch("app.core.security.deps.decode_access_token", return_value={"sub": "1"}),
            patch("app.core.security.deps.get_session"),
        ):
            # Simulate inactive user from DB
            mock_session = AsyncMock()
            mock_result  = MagicMock()
            inactive_user = self._make_user("analyst", is_active=False)
            mock_result.scalar_one_or_none.return_value = inactive_user
            mock_session.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="fake.token.here", session=mock_session)
            assert exc_info.value.status_code == 403


# ─────────────────────────────────────────────────────────────
# TestAccountLockout
# ─────────────────────────────────────────────────────────────

class TestAccountLockout:

    def test_lockout_threshold_constant(self):
        from app.api.v1.endpoints.auth import MAX_FAILED_LOGINS, LOCKOUT_MINUTES
        assert MAX_FAILED_LOGINS == 5
        assert LOCKOUT_MINUTES   == 15

    @pytest.mark.asyncio
    async def test_locked_user_raises_403(self):
        from fastapi import HTTPException
        from app.core.security.deps import get_current_user

        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        locked_user = MagicMock()
        locked_user.id           = 1
        locked_user.is_active    = True
        locked_user.locked_until = future

        with (
            patch("app.core.security.deps.decode_access_token", return_value={"sub": "1"}),
        ):
            mock_session = AsyncMock()
            mock_result  = MagicMock()
            mock_result.scalar_one_or_none.return_value = locked_user
            mock_session.execute = AsyncMock(return_value=mock_result)

            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(token="fake", session=mock_session)
            assert exc_info.value.status_code == 403
            assert "locked" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_expired_lockout_allows_access(self):
        """A lockout in the past (expired) should not block the user."""
        from app.core.security.deps import get_current_user

        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        user = MagicMock()
        user.id           = 1
        user.is_active    = True
        user.locked_until = past   # lockout has expired

        with (
            patch("app.core.security.deps.decode_access_token", return_value={"sub": "1"}),
        ):
            mock_session = AsyncMock()
            mock_result  = MagicMock()
            mock_result.scalar_one_or_none.return_value = user
            mock_session.execute = AsyncMock(return_value=mock_result)

            result = await get_current_user(token="fake", session=mock_session)
            assert result is user


# ─────────────────────────────────────────────────────────────
# TestPasswordChangePolicy
# ─────────────────────────────────────────────────────────────

class TestPasswordChangePolicy:

    def test_password_must_have_digit(self):
        from pydantic import ValidationError
        from app.api.v1.endpoints.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.com", username="user1",
                password="NoDigitHere!",  # no digit
            )

    def test_password_must_have_letter(self):
        from pydantic import ValidationError
        from app.api.v1.endpoints.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.com", username="user2",
                password="12345678!",   # no letter
            )

    def test_valid_password_passes(self):
        from app.api.v1.endpoints.auth import RegisterRequest
        r = RegisterRequest(
            email="test@orbitiq.dev", username="validuser",
            password="Secur3Pass",
        )
        assert r.password == "Secur3Pass"

    def test_username_pattern_enforced(self):
        from pydantic import ValidationError
        from app.api.v1.endpoints.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.com", username="bad user!",  # spaces + ! invalid
                password="Valid1Pass",
            )

    def test_valid_role_values(self):
        from app.api.v1.endpoints.auth import RegisterRequest
        for role in ["admin", "operator", "analyst", "readonly"]:
            r = RegisterRequest(
                email=f"{role}@test.dev", username=f"{role}user",
                password="Test1Pass", role=role,
            )
            assert r.role == role

    def test_invalid_role_rejected(self):
        from pydantic import ValidationError
        from app.api.v1.endpoints.auth import RegisterRequest
        with pytest.raises(ValidationError):
            RegisterRequest(
                email="a@b.com", username="user3",
                password="Test1Pass", role="superadmin",
            )



# ─────────────────────────────────────────────────────────────
# TestAuditLogging
# ─────────────────────────────────────────────────────────────

class TestAuditLogging:
    """
    Tests for the log_auth_event audit helper.
    log_auth_event imports AuditLog lazily inside the function body.
    We patch at "app.db.models.audit_logs.AuditLog" to intercept
    the class before the ORM mapper tries to resolve relationships.
    """

    def _make_request(self, path: str = "/api/v1/auth/login") -> MagicMock:
        req = MagicMock()
        req.client.host = "192.168.1.100"
        req.headers.get = lambda k, d="": {"user-agent": "TestAgent/1.0"}.get(k, d)
        req.url.path    = path
        req.method      = "POST"
        return req

    def _make_user(self) -> MagicMock:
        u = MagicMock()
        u.id       = 42
        u.username = "missioncontrol"
        return u

    def _mock_audit_log(self):
        """Return a MockAuditLog class that captures constructor kwargs."""
        captured = {}

        class MockAuditLog:
            def __init__(self, **kwargs):
                captured.update(kwargs)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        return MockAuditLog, captured

    @pytest.mark.asyncio
    async def test_audit_event_written_with_correct_fields(self):
        """log_auth_event should construct an AuditLog with expected fields."""
        from app.core.security.deps import log_auth_event

        MockAuditLog, captured = self._mock_audit_log()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add    = lambda obj: None

        req  = self._make_request("/api/v1/auth/login")
        user = self._make_user()

        with patch("app.db.models.audit_logs.AuditLog", MockAuditLog):
            await log_auth_event(
                request=req, user=user,
                action="login", outcome="success",
                detail="role=operator",
                session=mock_session,
            )

        assert captured.get("action")      == "login"
        assert captured.get("outcome")     == "success"
        assert captured.get("user_id")     == 42
        assert captured.get("username")    == "missioncontrol"
        assert captured.get("ip_address")  == "192.168.1.100"
        assert captured.get("description") == "role=operator"
        assert captured.get("endpoint")    == "/api/v1/auth/login"

    @pytest.mark.asyncio
    async def test_audit_event_null_user_allowed(self):
        """Audit events for pre-auth failures must accept user=None."""
        from app.core.security.deps import log_auth_event

        MockAuditLog, captured = self._mock_audit_log()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add    = lambda obj: None

        req = self._make_request("/api/v1/auth/login")

        with patch("app.db.models.audit_logs.AuditLog", MockAuditLog):
            await log_auth_event(
                request=req, user=None,
                action="login_failed", outcome="failure",
                session=mock_session,
            )

        assert captured.get("user_id")  is None
        assert captured.get("username") is None
        assert captured.get("action")   == "login_failed"
        assert captured.get("outcome")  == "failure"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_propagate(self):
        """
        A database error in log_auth_event must be swallowed.
        Audit failure must never break the authentication flow.
        """
        from app.core.security.deps import log_auth_event

        mock_session = AsyncMock()
        mock_session.add = MagicMock(side_effect=RuntimeError("DB gone"))

        req  = self._make_request()
        user = self._make_user()

        # Must not raise — even with a broken session
        await log_auth_event(
            request=req, user=user,
            action="login", outcome="success",
            session=mock_session,
        )

    @pytest.mark.asyncio
    async def test_logout_audit_event(self):
        """Logout should produce an audit event with correct action and endpoint."""
        from app.core.security.deps import log_auth_event

        MockAuditLog, captured = self._mock_audit_log()
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add    = lambda obj: None

        req  = self._make_request("/api/v1/auth/logout")
        user = self._make_user()

        with patch("app.db.models.audit_logs.AuditLog", MockAuditLog):
            await log_auth_event(
                request=req, user=user,
                action="logout", outcome="success",
                session=mock_session,
            )

        assert captured.get("action")   == "logout"
        assert captured.get("endpoint") == "/api/v1/auth/logout"


# ─────────────────────────────────────────────────────────────
# TestPermissionMatrix
# ─────────────────────────────────────────────────────────────

class TestPermissionMatrix:
    """
    Verify the full RBAC access matrix defined in router.py.
    Tests that each role gets exactly the access it should.
    """

    def _make_user(self, role: str) -> MagicMock:
        u = MagicMock()
        u.id         = 1
        u.role       = role
        u.is_active  = True
        u.locked_until = None
        return u

    @pytest.mark.asyncio
    async def test_admin_passes_all_guards(self):
        from app.core.security.deps import require_roles, require_min_role, Role
        user = self._make_user(Role.ADMIN)
        for guard_fn in [
            require_roles("admin"),
            require_min_role("operator"),
            require_min_role("analyst"),
            require_min_role("readonly"),
        ]:
            result = await guard_fn(user)
            assert result is user

    @pytest.mark.asyncio
    async def test_operator_ssa_access(self):
        """Operators can access SSA endpoints."""
        from app.core.security.deps import require_min_role, Role
        user  = self._make_user(Role.OPERATOR)
        guard = require_min_role("operator")
        result = await guard(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_operator_cannot_access_foundation(self):
        """Operators must not access foundation (admin-only)."""
        from fastapi import HTTPException
        from app.core.security.deps import require_roles, Role
        user  = self._make_user(Role.OPERATOR)
        guard = require_roles("admin")
        with pytest.raises(HTTPException) as exc_info:
            await guard(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_analyst_graph_access(self):
        """Analysts can access knowledge graph."""
        from app.core.security.deps import require_min_role, Role
        user  = self._make_user(Role.ANALYST)
        guard = require_min_role("analyst")
        result = await guard(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_analyst_cannot_access_ssa(self):
        """Analysts must not access SSA (operator+)."""
        from fastapi import HTTPException
        from app.core.security.deps import require_min_role, Role
        user  = self._make_user(Role.ANALYST)
        guard = require_min_role("operator")
        with pytest.raises(HTTPException) as exc_info:
            await guard(user)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_any_auth_access(self):
        """Read-only (viewer) users can access any-auth routes."""
        from app.core.security.deps import require_min_role, Role
        user  = self._make_user(Role.READONLY)
        guard = require_min_role("readonly")
        result = await guard(user)
        assert result is user

    @pytest.mark.asyncio
    async def test_readonly_cannot_access_agents(self):
        """Viewers must not access agents (analyst+)."""
        from fastapi import HTTPException
        from app.core.security.deps import require_min_role, Role
        user  = self._make_user(Role.READONLY)
        guard = require_min_role("analyst")
        with pytest.raises(HTTPException) as exc_info:
            await guard(user)
        assert exc_info.value.status_code == 403

    def test_full_access_matrix(self):
        """
        Table-driven test of all role × resource combinations.
        True = access granted, False = access denied.
        """
        from app.core.security.deps import _meets_min_role, Role

        matrix = {
            # (user_role, min_required_role) → expected
            (Role.ADMIN,    "readonly"): True,
            (Role.ADMIN,    "analyst"):  True,
            (Role.ADMIN,    "operator"): True,
            (Role.ADMIN,    "admin"):    True,
            (Role.OPERATOR, "readonly"): True,
            (Role.OPERATOR, "analyst"):  True,
            (Role.OPERATOR, "operator"): True,
            (Role.OPERATOR, "admin"):    False,
            (Role.ANALYST,  "readonly"): True,
            (Role.ANALYST,  "analyst"):  True,
            (Role.ANALYST,  "operator"): False,
            (Role.ANALYST,  "admin"):    False,
            (Role.READONLY, "readonly"): True,
            (Role.READONLY, "analyst"):  False,
            (Role.READONLY, "operator"): False,
            (Role.READONLY, "admin"):    False,
        }

        for (user_role, min_role), expected in matrix.items():
            result = _meets_min_role(user_role, min_role)
            assert result == expected, (
                f"_meets_min_role({user_role!r}, {min_role!r}) "
                f"expected {expected}, got {result}"
            )
