"""Cancel a class and its active reservations in a single class-locked transaction."""

from uuid import UUID

from sqlalchemy import select, text, update

from boxing_club_api.bookings.models import Booking
from boxing_club_api.core.clock import Clock, utc_now
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal, require_owner

from .models import TrainingSession
from .sessions import SessionDetails, session_details


def cancel_class(
    sessions: SessionFactory,
    principal: Principal,
    session_id: UUID,
    *,
    reason: str,
    clock: Clock = utc_now,
) -> SessionDetails:
    """Cancel before start, preserving prior member cancellations and the original replay audit."""
    require_owner(principal)
    reason = reason.strip()
    if not reason or len(reason) > 1000 or "\x00" in reason:
        raise ApplicationError(
            422, "VALIDATION_ERROR", "Supply a cancellation reason of 1–1000 characters."
        )
    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        record = session.scalar(
            select(TrainingSession).where(TrainingSession.id == session_id).with_for_update()
        )
        if record is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Class not found.")
        if record.status == "CANCELLED":
            return session_details(record)
        now = clock()
        if now >= record.starts_at:
            raise ApplicationError(
                409, "INVALID_STATE_TRANSITION", "Class cancellation must precede its start."
            )
        session.execute(
            update(Booking)
            .where(Booking.session_id == session_id, Booking.status == "RESERVED")
            .values(
                status="CANCELLED",
                cancelled_at=now,
                cancelled_by_user_id=principal.user_id,
                cancellation_reason=reason,
            )
        )
        record.status = "CANCELLED"
        record.cancelled_at = now
        record.cancelled_by_user_id = principal.user_id
        record.cancellation_reason = reason
        result = session_details(record)
    return result
