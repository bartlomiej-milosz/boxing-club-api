"""Manage the room catalog with owner authorization and immutable capacities."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from psycopg import errors
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal, require_owner
from boxing_club_api.identity.fields import normalize_name

from .models import Room


@dataclass(frozen=True)
class RoomDetails:
    """Detached catalog result whose capacity is fixed when the room is created."""

    id: UUID
    name: str
    capacity: int
    active: bool


def create_room(
    sessions: SessionFactory, principal: Principal, *, name: str, capacity: int, active: bool = True
) -> RoomDetails:
    """Create a room for an owner and translate duplicate trimmed names after rollback."""
    require_owner(principal)
    name = normalize_name(name)
    if not 1 <= capacity <= 2147483647:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "Room capacity must be a positive PostgreSQL integer."
        )
    result = RoomDetails(uuid4(), name, capacity, active)
    try:
        with sessions.begin() as session:
            session.add(Room(id=result.id, name=name, capacity=capacity, active=active))
    except IntegrityError as error:
        if (
            isinstance(error.orig, errors.UniqueViolation)
            and error.orig.diag.constraint_name == "uq_room_name"
        ):
            raise ApplicationError(
                409, "ROOM_NAME_ALREADY_EXISTS", "A room with this name already exists."
            ) from error
        raise
    return result


def list_rooms(
    sessions: SessionFactory,
    principal: Principal,
    *,
    page: int,
    size: int,
    include_inactive: bool = False,
) -> tuple[list[RoomDetails], int]:
    """Page rooms by name and ID; restrict inactive-room visibility to owners."""
    if include_inactive:
        require_owner(principal)
    statement = select(Room)
    if not include_inactive:
        statement = statement.where(Room.active.is_(True))
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rooms = session.scalars(
            statement.order_by(Room.name, Room.id).offset(page * size).limit(size)
        ).all()
        return [
            RoomDetails(room.id, room.name, room.capacity, room.active) for room in rooms
        ], total


def update_room(
    sessions: SessionFactory,
    principal: Principal,
    room_id: UUID,
    *,
    name: str | None = None,
    active: bool | None = None,
) -> RoomDetails:
    """Change a room's name or activity under its row lock, preserving capacity and history."""
    require_owner(principal)
    if name is not None:
        name = normalize_name(name)
    try:
        with sessions.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
            if room is None:
                raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Room not found.")
            if name is not None:
                room.name = name
            if active is not None:
                room.active = active
            result = RoomDetails(room.id, room.name, room.capacity, room.active)
    except IntegrityError as error:
        if (
            isinstance(error.orig, errors.UniqueViolation)
            and error.orig.diag.constraint_name == "uq_room_name"
        ):
            raise ApplicationError(
                409, "ROOM_NAME_ALREADY_EXISTS", "A room with this name already exists."
            ) from error
        raise
    return result
