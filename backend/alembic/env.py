from logging.config import fileConfig
from alembic import context
import os
import sys

# Ensure app package on path
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from app.db import Base, engine
from app import models  # noqa

config = context.config
fileConfig(config.config_file_name) if config.config_file_name else None

target_metadata = Base.metadata


def run_migrations_offline():
    url = engine.url
    context.configure(url=str(url), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
