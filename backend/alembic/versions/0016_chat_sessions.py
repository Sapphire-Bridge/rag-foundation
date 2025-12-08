"""add chat_sessions and fk session_id

Revision ID: 0016_chat_sessions
Revises: 0015_document_last_error
Create Date: 2025-12-04 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func
import uuid
import datetime

# revision identifiers, used by Alembic.
revision = "0016_chat_sessions"
down_revision = "0015_document_last_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("store_id", sa.Integer(), sa.ForeignKey("stores.id"), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=func.now(), nullable=False),
    )
    op.create_index("ix_chat_sessions_user_updated", "chat_sessions", ["user_id", "updated_at"])
    op.create_index("ix_chat_sessions_user_store_updated", "chat_sessions", ["user_id", "store_id", "updated_at"])

    # Backfill existing chat history into chat_sessions (one session per user/store/session_id)
    conn = op.get_bind()
    rows = list(
        conn.execute(
            sa.text(
                """
                select distinct user_id, store_id, session_id
                from chat_history
                """
            )
        )
    )
    for row in rows:
        now_value = datetime.datetime.now(datetime.timezone.utc)
        new_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                insert into chat_sessions (id, user_id, store_id, updated_at)
                values (:id, :user_id, :store_id, :now)
                """
            ),
            {"id": new_id, "user_id": row.user_id, "store_id": row.store_id, "now": now_value},
        )
        conn.execute(
            sa.text(
                """
                update chat_history
                set session_id = :new_id
                where user_id = :user_id
                  and store_id is not distinct from :store_id
                  and session_id is not distinct from :old_id
                """
            ),
            {"new_id": new_id, "user_id": row.user_id, "store_id": row.store_id, "old_id": row.session_id},
        )

    with op.batch_alter_table("chat_history", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_chat_history_session",
            "chat_sessions",
            ["session_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.create_index("ix_chat_history_session", "chat_history", ["session_id"])


def downgrade() -> None:
    op.drop_constraint("fk_chat_history_session", "chat_history", type_="foreignkey")
    op.drop_index("ix_chat_history_session", table_name="chat_history")
    op.drop_index("ix_chat_sessions_user_store_updated", table_name="chat_sessions")
    op.drop_index("ix_chat_sessions_user_updated", table_name="chat_sessions")
    op.drop_table("chat_sessions")
