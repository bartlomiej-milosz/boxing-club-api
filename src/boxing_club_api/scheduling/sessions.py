"""Create immutable dated classes while serializing catalog activity changes."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from psycopg import errors
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from boxing_club_api.core.clock import Clock, utc_now
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal, require_owner
from boxing_club_api.identity.models import AppUser, TrainerProfile

from .models import Room, TrainingSession


@dataclass(frozen=True)
class SessionDetails:
    """Public class facts and seat availability at the time the result was read."""

    id: UUID
    title: str
    trainer_id: UUID
    room_id: UUID
    starts_at: datetime
    ends_at: datetime
    booking_closes_at: datetime
    capacity: int
    status: str
    available_seats: int
    cancelled_at: datetime | None = None
    cancelled_by_user_id: UUID | None = None
    cancellation_reason: str | None = None


def session_details(record: TrainingSession, reserved: int = 0) -> SessionDetails:
    """Copy loaded class fields before its ORM session is closed."""
    return SessionDetails(
        record.id,
        record.title,
        record.trainer_id,
        record.room_id,
        record.starts_at,
        record.ends_at,
        record.booking_closes_at,
        record.capacity,
        record.status,
        max(0, record.capacity - reserved) if record.status == "SCHEDULED" else 0,
        record.cancelled_at,
        record.cancelled_by_user_id,
        record.cancellation_reason,
    )


def create_session(
    sessions: SessionFactory,
    principal: Principal,
    *,
    title: str,
    trainer_id: UUID,
    room_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    capacity: int,
    booking_closes_at: datetime | None = None,
    clock: Clock = utc_now,
) -> SessionDetails:
    """Create a future class under room -> trainer locks and database overlap constraints.

    Validate active catalog records after locking. Read the clock after waiting.
    Translate exclusion failures only after rolling back the write transaction.
    """
    require_owner(principal)
    title = title.strip()
    cutoff = booking_closes_at if booking_closes_at is not None else starts_at
    if not title or len(title) > 120 or "\x00" in title or not 1 <= capacity <= 2147483647:
        raise ApplicationError(422, "VALIDATION_ERROR", "Invalid class title or capacity.")
    if any(value.utcoffset() is None for value in (starts_at, ends_at, cutoff)):
        raise ApplicationError(
            422, "VALIDATION_ERROR", "Class timestamps must include a UTC offset."
        )
    starts_at, ends_at, cutoff = (value.astimezone(UTC) for value in (starts_at, ends_at, cutoff))
    if ends_at <= starts_at or cutoff > starts_at:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "Class times or booking cutoff are invalid."
        )
    try:
        with sessions.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            room = session.scalar(select(Room).where(Room.id == room_id).with_for_update())
            if room is None:
                raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Room not found.")
            trainer = session.scalar(
                select(TrainerProfile).where(TrainerProfile.user_id == trainer_id).with_for_update()
            )
            if trainer is None:
                raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Trainer not found.")
            account = session.get_one(AppUser, trainer_id)
            if not room.active or not trainer.active or account.status != "ACTIVE":
                raise ApplicationError(
                    409, "INVALID_STATE_TRANSITION", "The room and trainer must be active."
                )
            now = clock()
            if starts_at <= now or capacity > room.capacity:
                raise ApplicationError(
                    422,
                    "VALIDATION_ERROR",
                    "Use a future start and capacity within the room limit.",
                )
            record = TrainingSession(
                id=uuid4(),
                title=title,
                trainer_id=trainer_id,
                room_id=room_id,
                starts_at=starts_at,
                ends_at=ends_at,
                booking_closes_at=cutoff,
                capacity=capacity,
                status="SCHEDULED",
                created_at=now,
            )
            session.add(record)
            result = session_details(record)
    except IntegrityError as error:
        if isinstance(error.orig, errors.ExclusionViolation):
            raise ApplicationError(
                409,
                "SCHEDULE_CONFLICT",
                "The room or trainer is already scheduled in this interval.",
            ) from error
        raise
    return result


def list_sessions(
    sessions: SessionFactory,
    *,
    starts_from: datetime,
    starts_to: datetime,
    page: int,
    size: int,
    trainer_id: UUID | None = None,
    status: str | None = None,
) -> tuple[list[SessionDetails], int]:
    """Page a half-open schedule window by start and ID, excluding all participant data."""
    if (
        starts_from.utcoffset() is None
        or starts_to.utcoffset() is None
        or not timedelta(0) < starts_to - starts_from <= timedelta(days=90)
    ):
        raise ApplicationError(
            422,
            "VALIDATION_ERROR",
            "Use an aware interval greater than zero and no longer than 90 days.",
        )
    query = select(TrainingSession).where(
        TrainingSession.starts_at >= starts_from, TrainingSession.starts_at < starts_to
    )
    if trainer_id is not None:
        query = query.where(TrainingSession.trainer_id == trainer_id)
    if status is not None:
        query = query.where(TrainingSession.status == status)
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(TrainingSession.starts_at, TrainingSession.id)
            .offset(page * size)
            .limit(size)
        ).all()
        return [session_details(row) for row in rows], total


def get_session(sessions: SessionFactory, session_id: UUID) -> SessionDetails:
    """Read public facts for one class or return a stable not-found failure."""
    with sessions() as session:
        record = session.get(TrainingSession, session_id)
        if record is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Class not found.")
        return session_details(record)
