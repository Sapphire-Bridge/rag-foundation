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
    # Use batch mode so SQLite can apply constraint changes by recreating tables
    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
        batch_op.create_index("ix_stores_deleted_by", ["deleted_by"])
        batch_op.create_foreign_key(
            "fk_stores_deleted_by",
            "users",
            ["deleted_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.add_column(sa.Column("deleted_by", sa.Integer(), nullable=True))
        batch_op.create_index("ix_documents_deleted_by", ["deleted_by"])
        batch_op.create_foreign_key(
            "fk_documents_deleted_by",
            "users",
            ["deleted_by"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents", schema=None) as batch_op:
        batch_op.drop_constraint("fk_documents_deleted_by", type_="foreignkey")
        batch_op.drop_index("ix_documents_deleted_by")
        batch_op.drop_column("deleted_by")

    with op.batch_alter_table("stores", schema=None) as batch_op:
        batch_op.drop_constraint("fk_stores_deleted_by", type_="foreignkey")
        batch_op.drop_index("ix_stores_deleted_by")
        batch_op.drop_column("deleted_by")
