"""add chat history table and gcs uri

Revision ID: 0008_chat_history_and_gcs
Revises: 0007_querylog_tags
Create Date: 2025-02-25 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision = "0008_chat_history_and_gcs"
down_revision = "0007_querylog_tags"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("gcs_uri", sa.String(length=512), nullable=True))

    op.create_table(
        "chat_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=func.now()),
    )
    op.create_index(
        "ix_chat_history_user_session_created",
        "chat_history",
        ["user_id", "session_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_chat_history_user_session_created", table_name="chat_history")
    op.drop_table("chat_history")
    op.drop_column("documents", "gcs_uri")
