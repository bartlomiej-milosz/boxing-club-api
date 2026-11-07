"""Expose dated class creation with owner authorization and explicit public errors."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import AwareDatetime

from boxing_club_api.application.dependencies import CurrentClock
from boxing_club_api.application.errors import ErrorResponse
from boxing_club_api.core.pagination import Page
from boxing_club_api.identity.dependencies import CurrentPrincipal, DatabaseSessions

from .cancellation import cancel_class
from .schemas import CancelSessionRequest, CreateSessionRequest, SessionResponse
from .sessions import create_session, get_session, list_sessions

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


@router.get("", response_model=Page[SessionResponse])
def schedule(
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    clock: CurrentClock,
    starts_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    starts_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
    trainer_id: UUID | None = None,
    status: Literal["SCHEDULED", "CANCELLED"] | None = None,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[SessionResponse]:
    """List classes in a bounded interval, defaulting to the next fourteen days."""
    lower = starts_from if starts_from is not None else clock()
    items, total = list_sessions(
        sessions,
        starts_from=lower,
        starts_to=starts_to,
        trainer_id=trainer_id,
        status=status,
        page=page,
        size=size,
    )
    return Page(
        items=[SessionResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )


@router.get("/{session_id}", response_model=SessionResponse)
def session_by_id(
    session_id: UUID, principal: CurrentPrincipal, sessions: DatabaseSessions
) -> SessionResponse:
    """Read class facts and availability without exposing the roster."""
    return SessionResponse.model_validate(get_session(sessions, session_id))


@router.post("/{session_id}/cancellation", response_model=SessionResponse)
def cancellation(
    session_id: UUID,
    payload: CancelSessionRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    clock: CurrentClock,
) -> SessionResponse:
    """Cancel an owner-managed class and release every active reservation atomically."""
    return SessionResponse.model_validate(
        cancel_class(sessions, principal, session_id, reason=payload.reason, clock=clock)
    )
