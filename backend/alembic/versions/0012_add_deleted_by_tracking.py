"""add deleted_by tracking

Revision ID: 0012_add_deleted_by_tracking
Revises: 0011_app_settings_defaults
Create Date: 2025-01-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0012_add_deleted_by_tracking"
down_revision = "0011_app_settings_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stores", sa.Column("deleted_by", sa.Integer(), nullable=True))
    op.create_index("ix_stores_deleted_by", "stores", ["deleted_by"])
    op.create_foreign_key("fk_stores_deleted_by", "stores", "users", ["deleted_by"], ["id"], ondelete="SET NULL")

    op.add_column("documents", sa.Column("deleted_by", sa.Integer(), nullable=True))
    op.create_index("ix_documents_deleted_by", "documents", ["deleted_by"])
    op.create_foreign_key("fk_documents_deleted_by", "documents", "users", ["deleted_by"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("fk_documents_deleted_by", "documents", type_="foreignkey")
    op.drop_index("ix_documents_deleted_by", table_name="documents")
    op.drop_column("documents", "deleted_by")

    op.drop_constraint("fk_stores_deleted_by", "stores", type_="foreignkey")
    op.drop_index("ix_stores_deleted_by", table_name="stores")
    op.drop_column("stores", "deleted_by")
