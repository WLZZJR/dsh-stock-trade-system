"""Alembic environment: online migrations only, URL from the environment (never from files)."""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import URL, make_url

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _database_url() -> URL:
    # Tests inject a URL object; the CLI uses the same secret env var as the application.
    injected = config.attributes.get("sqlalchemy_url")
    if injected is not None:
        return make_url(injected)
    raw = os.environ.get("GEI_DATABASE_URL")
    if not raw:
        raise RuntimeError("GEI_DATABASE_URL is not set; cannot run migrations")
    url = make_url(raw)
    if url.drivername == "postgresql":
        url = url.set(drivername="postgresql+psycopg")  # psycopg 3 driver
    return url


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("offline migrations are not supported; run against a live PostgreSQL")
run_migrations_online()
