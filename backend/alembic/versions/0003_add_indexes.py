from alembic import op

revision = "0003_add_indexes"
down_revision = "0002_add_auth_columns"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_stores_user_id", "stores", ["user_id"])
    op.create_index("ix_documents_store_id", "documents", ["store_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_query_logs_user_created", "query_logs", ["user_id", "created_at"])


def downgrade():
    op.drop_index("ix_query_logs_user_created", table_name="query_logs")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_store_id", table_name="documents")
    op.drop_index("ix_stores_user_id", table_name="stores")
