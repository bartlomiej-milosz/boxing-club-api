from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_database_engine(database_url: str | URL) -> Engine:
    return create_engine(
        database_url,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
        pool_timeout=5,
        hide_parameters=True,
    )


type SessionFactory = sessionmaker[Session]
