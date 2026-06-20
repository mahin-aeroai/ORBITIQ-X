"""users: create users and user_sessions tables

Revision ID: 0002_create_users
Revises: 0001_init_extensions
Create Date: 2026-06-20 00:02:00

Design notes:
  - hashed_password uses bcrypt (60-char output, but String(128) for future algo)
  - api_key_hash stores SHA-256 of the raw API key — never the key itself
  - locked_until enables account lockout after N failed logins
  - UserSession stores hashed refresh tokens (never raw JWT)
"""
from __future__ import annotations
import sqlalchemy as sa
from alembic import op

revision = "0002_create_users"
down_revision = "0001_init_extensions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id",                  sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email",               sa.String(255),  nullable=False),
        sa.Column("username",            sa.String(64),   nullable=False),
        sa.Column("hashed_password",     sa.String(128),  nullable=False),
        sa.Column("full_name",           sa.String(256)),
        sa.Column("organization",        sa.String(256)),
        sa.Column("role",                sa.String(32),   nullable=False, server_default="analyst",
                  comment="admin | operator | analyst | readonly"),
        sa.Column("is_active",           sa.Boolean(),    nullable=False, server_default="true"),
        sa.Column("is_verified",         sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("mfa_enabled",         sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("mfa_secret",          sa.String(64)),
        sa.Column("last_login_at",       sa.DateTime(timezone=True)),
        sa.Column("login_count",         sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("failed_login_count",  sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("locked_until",        sa.DateTime(timezone=True)),
        sa.Column("api_key_hash",        sa.String(128)),
        sa.Column("created_at",          sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",          sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_users_email",       "users", ["email"])
    op.create_unique_constraint("uq_users_username",    "users", ["username"])
    op.create_unique_constraint("uq_users_api_key",     "users", ["api_key_hash"])
    op.create_index("ix_users_email",        "users", ["email"])
    op.create_index("ix_users_role_active",  "users", ["role", "is_active"])

    # Trigger: auto-update updated_at on every row change
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ language 'plpgsql'
    """)
    op.execute("""
        CREATE TRIGGER trg_users_updated_at
        BEFORE UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)

    # ── user_sessions ────────────────────────────────────────
    op.create_table(
        "user_sessions",
        sa.Column("id",          sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id",     sa.BigInteger(), nullable=False),
        sa.Column("token_hash",  sa.String(128),  nullable=False),
        sa.Column("user_agent",  sa.Text()),
        sa.Column("ip_address",  sa.String(45)),
        sa.Column("expires_at",  sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked",     sa.Boolean(),    nullable=False, server_default="false"),
        sa.Column("created_at",  sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_sessions_token", "user_sessions", ["token_hash"])
    op.create_index("ix_sessions_user_expires", "user_sessions", ["user_id", "expires_at"])
    op.create_index("ix_sessions_token",         "user_sessions", ["token_hash"])
    op.create_foreign_key(
        "fk_sessions_user", "user_sessions", "users",
        ["user_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.execute("DROP TRIGGER IF EXISTS trg_users_updated_at ON users")
    op.drop_table("users")
    # Leave update_updated_at_column() function — shared by other tables
