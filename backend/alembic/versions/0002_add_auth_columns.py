from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "0002_add_auth_columns"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("hashed_password", sa.String(length=255), nullable=False, server_default=""))
        b.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")))
        b.add_column(sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("email_verified")
        b.drop_column("is_active")
        b.drop_column("hashed_password")
