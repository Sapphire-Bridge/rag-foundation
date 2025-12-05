"""add status_updated_at column to documents

Revision ID: 0013_document_status_timestamp
Revises: 0012_add_deleted_by_tracking
Create Date: 2025-03-05 00:00:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import func


# revision identifiers, used by Alembic.
revision = "0013_document_status_timestamp"
down_revision = "0012_add_deleted_by_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    op.execute("UPDATE documents SET status_updated_at = COALESCE(status_updated_at, created_at)")


def downgrade() -> None:
    op.drop_column("documents", "status_updated_at")
