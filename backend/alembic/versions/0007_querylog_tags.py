"""add project_id and tags to query_logs

Revision ID: 0007_querylog_tags
Revises: 0006_admin_rbac
Create Date: 2024-11-15 00:00:00
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007_querylog_tags"
down_revision = "0006_admin_rbac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("query_logs", sa.Column("project_id", sa.Integer(), nullable=True))
    op.add_column("query_logs", sa.Column("tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("query_logs", "tags")
    op.drop_column("query_logs", "project_id")
