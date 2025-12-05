"""add is_admin and admin audit logs

Revision ID: 0006_admin_rbac
Revises: 0005_soft_delete
Create Date: 2025-01-20 11:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006_admin_rbac"
down_revision = "0005_soft_delete"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("admin_notes", sa.Text(), nullable=True))
    op.create_index("ix_users_is_admin", "users", ["is_admin"])

    op.create_table(
        "admin_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("admin_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=255), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=True),
        sa.Column("target_id", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Remove server default after data backfill so future inserts must specify value
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("is_admin", server_default=None)


def downgrade():
    op.drop_table("admin_audit_logs")
    op.drop_index("ix_users_is_admin", table_name="users")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("admin_notes")
        batch_op.drop_column("is_admin")
