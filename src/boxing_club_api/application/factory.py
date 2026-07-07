"""Assemble the API and manage the process-wide database engine lifecycle."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import sessionmaker

from boxing_club_api.core.settings import Settings
from boxing_club_api.db.session import create_database_engine
from boxing_club_api.identity.router import router as auth_router

from .errors import invalid_request
from .health import router as health_router


def create_app() -> FastAPI:
    """Compose routers and settings, opening database resources during application lifespan."""
    settings = Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        """Provide a session factory while the app runs and dispose its engine on shutdown."""
        database_url = settings.database_url
        if database_url is None:
            yield
            return

        engine = create_database_engine(database_url.get_secret_value())
        try:
            app.state.db_sessions = sessionmaker(engine)
            yield
        finally:
            app.state.db_sessions = None
            await run_in_threadpool(engine.dispose)

    app = FastAPI(title="boxing-club-api", version="0.1.0", lifespan=lifespan)
    app.state.app_env = settings.app_env
    app.state.db_sessions = None
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.include_router(health_router)
    app.include_router(auth_router)
    return app
