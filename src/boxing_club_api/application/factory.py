"""Assemble the API and manage the process-wide database engine lifecycle."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError
from sqlalchemy.orm import sessionmaker
from starlette.exceptions import HTTPException

from boxing_club_api.bookings.router import router as booking_router
from boxing_club_api.core.clock import utc_now
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.settings import Settings
from boxing_club_api.db.session import create_database_engine
from boxing_club_api.identity.router import identity_router
from boxing_club_api.identity.router import router as auth_router
from boxing_club_api.scheduling.router import router as room_router
from boxing_club_api.scheduling.session_router import router as session_router

from .correlation import correlate
from .errors import database_unavailable, http_failure, invalid_request, operation_failed
from .health import router as health_router

API_DESCRIPTION = """
A single-club API for accounts, trainer and room catalogs, dated classes,
reservations and cancellation.

### Authenticate in Swagger UI

1. Create the initial owner with the local bootstrap command, or initialize the
   fictional demo in an empty local database.
2. Execute `POST /api/v1/auth/login` with an account's email and password.
3. Copy the returned `access_token`, click **Authorize**, and paste the raw token.
   Swagger UI adds the `Bearer` prefix to protected requests.
4. Try `GET /api/v1/me`, then explore the routes available to that account's roles.

Owner, trainer assignment and member ownership rules are enforced by the API.
Logout revokes the current token. Swagger authorization is cleared on page reload.
Lists use zero-based pagination and timestamps require a UTC offset.
"""


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

    app = FastAPI(
        title="boxing-club-api",
        version="0.1.0",
        description=API_DESCRIPTION,
        docs_url="/docs",
        openapi_url="/openapi.json",
        swagger_ui_parameters={"persistAuthorization": False},
        openapi_tags=[
            {"name": "auth", "description": "Login and current-token revocation."},
            {
                "name": "identity",
                "description": "Current identity, owner-managed accounts and trainers.",
            },
            {
                "name": "rooms",
                "description": "Room catalog and owner-managed name/activity changes.",
            },
            {
                "name": "sessions",
                "description": "Dated classes, availability and owner cancellation.",
            },
            {
                "name": "bookings",
                "description": "Member reservations, own history and assigned-trainer rosters.",
            },
        ],
        lifespan=lifespan,
    )
    app.state.clock = utc_now
    app.state.app_env = settings.app_env
    app.state.db_sessions = None
    app.middleware("http")(correlate)
    app.add_exception_handler(HTTPException, http_failure)
    app.add_exception_handler(RequestValidationError, invalid_request)
    app.add_exception_handler(ApplicationError, operation_failed)
    for error_type in (OperationalError, InterfaceError, TimeoutError):
        app.add_exception_handler(error_type, database_unavailable)
    app.include_router(booking_router)
    app.include_router(session_router)
    app.include_router(room_router)
    app.include_router(identity_router)
    app.include_router(health_router)
    app.include_router(auth_router)
    return app
