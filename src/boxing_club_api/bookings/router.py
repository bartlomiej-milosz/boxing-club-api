"""Expose member reservations with server-controlled ownership."""

from fastapi import APIRouter, Response

from boxing_club_api.application.dependencies import CurrentClock
from boxing_club_api.application.errors import ErrorResponse
from boxing_club_api.identity.dependencies import CurrentPrincipal, DatabaseSessions

from .schemas import BookingResponse, ReserveRequest
from .service import reserve

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
