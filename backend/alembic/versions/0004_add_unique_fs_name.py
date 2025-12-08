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
    # Use batch mode so SQLite can recreate the table with the constraint applied
    with op.batch_alter_table("stores") as batch_op:
        batch_op.create_unique_constraint("uq_stores_fs_name", ["fs_name"])


def downgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.drop_constraint("uq_stores_fs_name", type_="unique")
