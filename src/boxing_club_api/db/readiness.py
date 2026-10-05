"""Check database connectivity and the exact schema revision with bounded SQL waits."""

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .session import SessionFactory

EXPECTED_REVISION = "0004"


def database_ready(sessions: SessionFactory) -> bool:
    """Require the expected revision and readable core tables without modifying application data."""
    try:
        with sessions.begin() as session:
            session.execute(text("SET LOCAL statement_timeout = '1s'"))
            session.execute(text("SET LOCAL lock_timeout = '500ms'"))
            if session.execute(
                text("SELECT version_num FROM public.alembic_version")
            ).scalars().all() != [EXPECTED_REVISION]:
                return False
            session.execute(
                text(
                    "SELECT u.id, t.id, b.id FROM public.app_user u, public.training_session t, public.booking b LIMIT 0"
                )
            )
            return True
    except SQLAlchemyError:
        return False
