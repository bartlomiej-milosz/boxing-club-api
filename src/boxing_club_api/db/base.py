from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Common registry for mappings backed by Alembic migrations."""
