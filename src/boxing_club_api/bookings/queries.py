"""Count reservations using the caller's session without creating transaction boundaries."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Booking


def reserved_counts(session: Session, session_ids: list[UUID]) -> dict[UUID, int]:
    """Count RESERVED rows for class IDs without persisting a seat counter."""
    if not session_ids:
        return {}
    rows = session.execute(
        select(Booking.session_id, func.count())
        .where(Booking.session_id.in_(session_ids), Booking.status == "RESERVED")
        .group_by(Booking.session_id)
    ).all()
    return {session_id: count for session_id, count in rows}


def reserved_count(session: Session, session_id: UUID) -> int:
    """Read the current reserved count using the same transaction that locked the class."""
    return reserved_counts(session, [session_id]).get(session_id, 0)
