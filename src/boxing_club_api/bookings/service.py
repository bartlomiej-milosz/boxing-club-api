"""Reserve seats under a class lock using member identity from authentication."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from psycopg import errors
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from boxing_club_api.core.clock import Clock, utc_now
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal
from boxing_club_api.identity.models import MemberProfile
from boxing_club_api.scheduling.models import TrainingSession

from .models import Booking
from .queries import reserved_count


@dataclass(frozen=True)
class BookingDetails:
    """Reservation state and immutable audit fields without private contact data."""

    id: UUID
    member_id: UUID
    session_id: UUID
    status: str
    created_at: datetime
    cancelled_at: datetime | None
    cancelled_by_user_id: UUID | None
    cancellation_reason: str | None


def booking_details(record: Booking) -> BookingDetails:
    """Copy a loaded reservation before transaction completion closes its session."""
    return BookingDetails(
        record.id,
        record.member_id,
        record.session_id,
        record.status,
        record.created_at,
        record.cancelled_at,
        record.cancelled_by_user_id,
        record.cancellation_reason,
    )


def require_member(principal: Principal) -> None:
    """Reject callers whose authenticated roles do not include MEMBER."""
    if "MEMBER" not in principal.roles:
        raise ApplicationError(403, "FORBIDDEN", "The MEMBER role is required.")


def reserve(
    sessions: SessionFactory, principal: Principal, session_id: UUID, *, clock: Clock = utc_now
) -> BookingDetails:
    """Reserve after locking the class and rechecking time, state, duplicate and seat count.

    Every writer affecting availability takes the same class lock first.
    The partial unique index remains the final guard against duplicate reservations.
    """
    require_member(principal)
    try:
        with sessions.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '2s'"))
            training = session.scalar(
                select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
            )
            if training is None:
                raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Class not found.")
            now = clock()
            if session.get(MemberProfile, principal.user_id) is None:
                raise ApplicationError(403, "FORBIDDEN", "A member profile is required.")
            if training.status != "SCHEDULED":
                raise ApplicationError(409, "SESSION_CANCELLED", "The class is cancelled.")
            if now >= training.booking_closes_at:
                raise ApplicationError(409, "BOOKING_CLOSED", "Booking has closed.")
            if (
                session.scalar(
                    select(Booking.id).where(
                        Booking.member_id == principal.user_id,
                        Booking.session_id == session_id,
                        Booking.status == "RESERVED",
                    )
                )
                is not None
            ):
                raise ApplicationError(
                    409, "BOOKING_ALREADY_EXISTS", "An active reservation already exists."
                )
            if reserved_count(session, session_id) >= training.capacity:
                raise ApplicationError(409, "SESSION_FULL", "No seats remain.")
            record = Booking(
                id=uuid4(),
                member_id=principal.user_id,
                session_id=session_id,
                status="RESERVED",
                created_at=now,
            )
            session.add(record)
            result = booking_details(record)
    except IntegrityError as error:
        if (
            isinstance(error.orig, errors.UniqueViolation)
            and error.orig.diag.constraint_name == "uq_booking_active_member_session"
        ):
            raise ApplicationError(
                409, "BOOKING_ALREADY_EXISTS", "An active reservation already exists."
            ) from error
        raise
    return result


def get_booking(sessions: SessionFactory, principal: Principal, booking_id: UUID) -> BookingDetails:
    """Return an accessible booking, concealing other members' private records with 404."""
    with sessions() as session:
        row = session.execute(
            select(Booking, TrainingSession.trainer_id)
            .join(TrainingSession, Booking.session_id == TrainingSession.id)
            .where(Booking.id == booking_id)
        ).one_or_none()
        if row is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Booking not found.")
        record, trainer_id = row
        permitted = (
            "OWNER" in principal.roles
            or ("MEMBER" in principal.roles and record.member_id == principal.user_id)
            or ("TRAINER" in principal.roles and trainer_id == principal.user_id)
        )
        if not permitted:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Booking not found.")
        return booking_details(record)


def own_bookings(
    sessions: SessionFactory,
    principal: Principal,
    *,
    page: int,
    size: int,
    status: str | None = None,
    starts_from: datetime | None = None,
    starts_to: datetime | None = None,
) -> tuple[list[BookingDetails], int]:
    """Page the caller's retained history by creation and ID, with optional class-date filters."""
    require_member(principal)
    if starts_from is not None and starts_to is not None and starts_from >= starts_to:
        raise ApplicationError(422, "VALIDATION_ERROR", "The date interval must be increasing.")
    query = (
        select(Booking)
        .join(TrainingSession, Booking.session_id == TrainingSession.id)
        .where(Booking.member_id == principal.user_id)
    )
    if status is not None:
        query = query.where(Booking.status == status)
    if starts_from is not None:
        query = query.where(TrainingSession.starts_at >= starts_from)
    if starts_to is not None:
        query = query.where(TrainingSession.starts_at < starts_to)
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.scalars(
            query.order_by(Booking.created_at.desc(), Booking.id.desc())
            .offset(page * size)
            .limit(size)
        ).all()
        return [booking_details(record) for record in rows], total


def cancel_booking(
    sessions: SessionFactory,
    principal: Principal,
    booking_id: UUID,
    *,
    reason: str | None = None,
    clock: Clock = utc_now,
) -> BookingDetails:
    """Cancel an owned reservation under its class lock, preserving audit fields on replay."""
    require_member(principal)
    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        session_id = session.scalar(
            select(Booking.session_id).where(
                Booking.id == booking_id, Booking.member_id == principal.user_id
            )
        )
        if session_id is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Booking not found.")
        training = session.scalar(
            select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
        )
        assert training is not None
        record = session.scalar(select(Booking).where(Booking.id == booking_id).with_for_update())
        assert record is not None
        if record.status == "CANCELLED":
            return booking_details(record)
        now = clock()
        if now >= training.starts_at:
            raise ApplicationError(
                409, "INVALID_STATE_TRANSITION", "Cancellation must precede the class start."
            )
        record.status = "CANCELLED"
        record.cancelled_at = now
        record.cancelled_by_user_id = principal.user_id
        record.cancellation_reason = reason
        result = booking_details(record)
    return result
