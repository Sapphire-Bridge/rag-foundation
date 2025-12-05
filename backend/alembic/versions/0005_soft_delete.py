"""add soft delete columns

Revision ID: 0005_soft_delete
Revises: 0004_add_unique_fs_name
Create Date: 2025-01-20 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0005_soft_delete"
down_revision = "0004_add_unique_fs_name"
branch_labels = None
depends_on = None


def upgrade():
    """Add deleted_at columns to stores and documents with supporting indexes."""
    with op.batch_alter_table("stores") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    with op.batch_alter_table("documents") as batch_op:
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index("ix_stores_deleted_at", "stores", ["deleted_at"])
    op.create_index("ix_documents_deleted_at", "documents", ["deleted_at"])


def downgrade():
    """Drop deleted_at columns and indexes."""
    op.drop_index("ix_documents_deleted_at", table_name="documents")
    op.drop_index("ix_stores_deleted_at", table_name="stores")

    with op.batch_alter_table("documents") as batch_op:
        batch_op.drop_column("deleted_at")

    with op.batch_alter_table("stores") as batch_op:
        batch_op.drop_column("deleted_at")
