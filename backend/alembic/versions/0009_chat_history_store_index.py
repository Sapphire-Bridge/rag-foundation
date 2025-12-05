"""add store_id index for chat_history

Revision ID: 0009_chat_history_store_index
Revises: 0008_chat_history_and_gcs
Create Date: 2025-03-01 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0009_chat_history_store_index"
down_revision = "0008_chat_history_and_gcs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes("chat_history")}

    if "ix_chat_history_store_id" not in existing:
        op.create_index(
            "ix_chat_history_store_id",
            "chat_history",
            ["store_id"],
        )

    if "ix_chat_history_user_session_created" not in existing:
        op.create_index(
            "ix_chat_history_user_session_created",
            "chat_history",
            ["user_id", "session_id", "created_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {idx["name"] for idx in inspector.get_indexes("chat_history")}

    if "ix_chat_history_user_session_created" in existing:
        op.drop_index("ix_chat_history_user_session_created", table_name="chat_history")
    if "ix_chat_history_store_id" in existing:
        op.drop_index("ix_chat_history_store_id", table_name="chat_history")
