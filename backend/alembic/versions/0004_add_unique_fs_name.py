"""Add unique constraint to stores.fs_name

Revision ID: 0004_add_unique_fs_name
Revises: 0003_add_indexes
Create Date: 2025-11-17

"""

from alembic import op

revision = "0004_add_unique_fs_name"
down_revision = "0003_add_indexes"
branch_labels = None
depends_on = None


def upgrade():
    # Add unique constraint to stores.fs_name column
    op.create_unique_constraint("uq_stores_fs_name", "stores", ["fs_name"])


def downgrade():
    # Remove unique constraint
    op.drop_constraint("uq_stores_fs_name", "stores", type_="unique")
