"""Expose authenticated room catalog reads and owner-authorized catalog writes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

from boxing_club_api.application.errors import ErrorResponse
from boxing_club_api.core.pagination import Page
from boxing_club_api.identity.dependencies import CurrentPrincipal, DatabaseSessions

from .rooms import create_room, list_rooms, update_room
from .schemas import CreateRoomRequest, RoomResponse, UpdateRoomRequest

router = APIRouter(
    prefix="/api/v1/rooms",
    tags=["rooms"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


@router.post(
    "", response_model=RoomResponse, status_code=201, responses={409: {"model": ErrorResponse}}
)
def add_room(
    payload: CreateRoomRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    response: Response,
) -> RoomResponse:
    """Create an owner-managed room and return its resource location."""
    result = create_room(
        sessions, principal, name=payload.name, capacity=payload.capacity, active=payload.active
    )
    response.headers["Location"] = f"/api/v1/rooms/{result.id}"
    return RoomResponse.model_validate(result)


@router.get("", response_model=Page[RoomResponse])
def rooms(
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
    page: Annotated[int, Query(ge=0)] = 0,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    include_inactive: bool = False,
) -> Page[RoomResponse]:
    """Return a bounded catalog page, exposing inactive rooms only on an owner's request."""
    items, total = list_rooms(
        sessions, principal, page=page, size=size, include_inactive=include_inactive
    )
    return Page(
        items=[RoomResponse.model_validate(item) for item in items],
        page=page,
        size=size,
        total_items=total,
    )


@router.patch(
    "/{room_id}",
    response_model=RoomResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
)
def patch_room(
    room_id: UUID,
    payload: UpdateRoomRequest,
    principal: CurrentPrincipal,
    sessions: DatabaseSessions,
) -> RoomResponse:
    """Change a room's name or activity while keeping its original capacity."""
    return RoomResponse.model_validate(
        update_room(sessions, principal, room_id, name=payload.name, active=payload.active)
    )
