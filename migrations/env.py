"""Connect Alembic to an explicit migration target and run versioned SQL revisions."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Hand-written migrations own the schema; ORM metadata is not used for autogeneration.
target_metadata = None


def migration_url() -> str:
    """Require an explicit migration target rather than an implicit database."""
    url: str | None = os.environ.get("MIGRATION_DATABASE_URL")
    if not url:
        raise RuntimeError("Set MIGRATION_DATABASE_URL, for example with uv run --env-file .env")
    return url


def run_migrations_offline() -> None:
    """Render SQL without connecting to a database."""
    context.configure(
        url=migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect as the migration owner for the duration of the command."""
    engine = create_engine(migration_url(), poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
