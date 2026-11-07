"""Configure synchronous database connections and per-operation session factories."""

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str | URL) -> Engine:
    """Bound connection/pool waits to five seconds, locks to two and statements to five.

    Set PostgreSQL defaults on every physical connection, including authentication
    reads and implicit flushes. Readiness can tighten them with SET LOCAL; Alembic
    uses its own engine so application deadlines do not limit schema migrations.
    """
    return create_engine(
        database_url,
        connect_args={
            "connect_timeout": 5,
            "options": "-c lock_timeout=2s -c statement_timeout=5s",
        },
        pool_pre_ping=True,
        pool_timeout=5,
        hide_parameters=True,
    )


type SessionFactory = sessionmaker[Session]
