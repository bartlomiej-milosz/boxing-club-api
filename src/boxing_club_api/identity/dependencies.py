"""Connect FastAPI bearer authentication to short-lived identity queries."""

from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory

from .authentication import Principal, resolve_principal

bearer = HTTPBearer(auto_error=False)


def database_sessions(request: Request) -> SessionFactory:
    """Obtain the application's session factory or report unavailable database configuration."""
    sessions: SessionFactory | None = request.app.state.db_sessions
    if sessions is None:
        raise ApplicationError(
            503, "TEMPORARILY_UNAVAILABLE", "The database is temporarily unavailable."
        )
    return sessions


DatabaseSessions = Annotated[SessionFactory, Depends(database_sessions)]


def current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
    request: Request,
) -> Principal:
    """Require a valid bearer token and return identifiers without retaining an ORM session."""
    if credentials is None:
        raise ApplicationError(401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required.")
    principal = resolve_principal(database_sessions(request), credentials.credentials)
    if principal is None:
        raise ApplicationError(401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required.")
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]
