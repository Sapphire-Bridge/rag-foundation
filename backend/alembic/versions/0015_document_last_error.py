"""add last_error to documents

Revision ID: 0015_document_last_error
Revises: 0014_add_gemini_file_id
Create Date: 2025-03-06 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0015_document_last_error"
down_revision = "0014_add_gemini_file_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "last_error")
