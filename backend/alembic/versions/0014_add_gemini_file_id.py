"""add gemini_file_id column to documents

Revision ID: 0014_add_gemini_file_id
Revises: 0013_document_status_timestamp
Create Date: 2025-03-06 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_add_gemini_file_id"
down_revision = "0013_document_status_timestamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("gemini_file_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "gemini_file_id")
