"""Expose member reservations with server-controlled ownership."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import AwareDatetime

from boxing_club_api.application.dependencies import CurrentClock
from boxing_club_api.application.errors import ErrorResponse
from boxing_club_api.core.pagination import Page
from boxing_club_api.identity.dependencies import CurrentPrincipal, DatabaseSessions

from .roster import roster
from .schemas import BookingResponse, CancelBookingRequest, ReserveRequest, RosterResponse
from .service import cancel_booking, get_booking, own_bookings, reserve

router = APIRouter(
    prefix="/api/v1",
    tags=["bookings"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 409, 422, 503)},
)


@router.post("/bookings", response_model=BookingResponse, status_code=201)
def add_booking(
    payload: ReserveRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    clock: CurrentClock,
    response: Response,
) -> BookingResponse:
    """Reserve for the authenticated member and return the reservation's location."""
    result = reserve(sessions, principal, payload.session_id, clock=clock)
    response.headers["Location"] = f"/api/v1/bookings/{result.id}"
    return BookingResponse.model_validate(result)


@router.get("/me/bookings", response_model=Page[BookingResponse])
def history(
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["RESERVED", "CANCELLED"] | None = None,
    starts_from: Annotated[AwareDatetime | None, Query(alias="from")] = None,
    starts_to: Annotated[AwareDatetime | None, Query(alias="to")] = None,
) -> Page[BookingResponse]:
    """Return only the authenticated member's history, including cancelled records."""
    items, total = own_bookings(
        sessions,
        principal,
        page=page,
        size=size,
        status=status,
        starts_from=starts_from,
        starts_to=starts_to,
    )
    return Page(
        items=[BookingResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )


@router.get("/bookings/{booking_id}", response_model=BookingResponse)
def detail(
    booking_id: UUID, principal: CurrentPrincipal, sessions: DatabaseSessions
) -> BookingResponse:
    """Read a booking as its member, the owner or its assigned trainer."""
    return BookingResponse.model_validate(get_booking(sessions, principal, booking_id))


@router.post("/bookings/{booking_id}/cancellation", response_model=BookingResponse)
def cancellation(
    booking_id: UUID,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    clock: CurrentClock,
    payload: CancelBookingRequest | None = None,
) -> BookingResponse:
    """Cancel an owned reservation before start, returning the original audit on replay."""
    result = cancel_booking(
        sessions, principal, booking_id, reason=payload.reason if payload else None, clock=clock
    )
    return BookingResponse.model_validate(result)


@router.get("/sessions/{session_id}/bookings", response_model=Page[RosterResponse])
def class_roster(
    session_id: UUID,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Literal["RESERVED", "CANCELLED"] | None = None,
) -> Page[RosterResponse]:
    """Show a bounded roster only to an owner or the selected class's assigned trainer."""
    items, total = roster(sessions, principal, session_id, page=page, size=size, status=status)
    return Page(
        items=[RosterResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )
