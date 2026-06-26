"""user_sessions: add missing FK constraint user_id → users.id

Revision ID: 0010_add_fk_user_sessions
Revises: 0009_create_sync_metrics
Create Date: 2026-06-26 00:10:00
"""
from alembic import op

revision = "0010_add_fk_user_sessions"
down_revision = "0009_create_sync_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_user_sessions_user_id",
        "user_sessions", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_user_sessions_user_id", "user_sessions", type_="foreignkey")
