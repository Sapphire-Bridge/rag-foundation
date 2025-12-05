"""seed new app settings defaults

Revision ID: 0011_app_settings_defaults
Revises: 0010_app_settings
Create Date: 2025-02-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0011_app_settings_defaults"
down_revision = "0010_app_settings"
branch_labels = None
depends_on = None


NEW_DEFAULTS = {
    "welcome_message": "Hi! I'm your RAG assistant. Ask me anything about your documents.",
    "suggested_prompt_1": "Summarize the key findings from my uploads.",
    "suggested_prompt_2": "What are the main risks or open questions?",
    "suggested_prompt_3": "Create an outline using the latest documents.",
}


def upgrade():
    bind = op.get_bind()
    for key, value in NEW_DEFAULTS.items():
        bind.execute(
            sa.text(
                "INSERT INTO app_settings (key, value) "
                "SELECT :key, :value WHERE NOT EXISTS (SELECT 1 FROM app_settings WHERE key = :key)"
            ),
            {"key": key, "value": value},
        )


def downgrade():
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM app_settings WHERE key in (:k1, :k2, :k3, :k4)"),
        {
            "k1": "welcome_message",
            "k2": "suggested_prompt_1",
            "k3": "suggested_prompt_2",
            "k4": "suggested_prompt_3",
        },
    )
