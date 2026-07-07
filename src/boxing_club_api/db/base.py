"""Share the ORM registry for tables whose schema is managed by Alembic."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common registry for mappings backed by Alembic migrations."""
