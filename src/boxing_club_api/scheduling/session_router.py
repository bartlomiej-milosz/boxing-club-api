"""Expose dated class creation with owner authorization and explicit public errors."""

from fastapi import APIRouter, Response

from boxing_club_api.application.dependencies import CurrentClock
from boxing_club_api.application.errors import ErrorResponse
from boxing_club_api.identity.dependencies import CurrentPrincipal, DatabaseSessions

from .schemas import CreateSessionRequest, SessionResponse
from .sessions import create_session

router = APIRouter(
    prefix="/api/v1/sessions",
    tags=["sessions"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post("", response_model=SessionResponse, status_code=201)
def add_session(
    payload: CreateSessionRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    clock: CurrentClock,
    response: Response,
) -> SessionResponse:
    """Create an owner-scheduled class and return its immutable concrete values."""
    result = create_session(sessions, principal, **payload.model_dump(), clock=clock)
    response.headers["Location"] = f"/api/v1/sessions/{result.id}"
    return SessionResponse.model_validate(result)
