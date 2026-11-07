"""Expose minimal roster data only to owners and the class's assigned trainer."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.pagination import page_offset
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal
from boxing_club_api.identity.models import AppUser
from boxing_club_api.scheduling.models import TrainingSession

from .models import Booking


@dataclass(frozen=True)
class RosterEntry:
    """Reservation and member display identity without email or credential fields."""

    id: UUID
    member_id: UUID
    first_name: str
    last_name: str
    status: str
    created_at: datetime


def roster(
    sessions: SessionFactory,
    principal: Principal,
    session_id: UUID,
    *,
    page: int,
    size: int,
    status: str | None = None,
) -> tuple[list[RosterEntry], int]:
    """Page a class roster by creation and ID after checking role and trainer assignment."""
    if not principal.roles & {"OWNER", "TRAINER"}:
        raise ApplicationError(403, "FORBIDDEN", "Owner or assigned trainer access is required.")
    offset = page_offset(page, size)
    with sessions() as session:
        training = session.get(TrainingSession, session_id)
        if training is None:
            raise ApplicationError(404, "RESOURCE_NOT_FOUND", "Class not found.")
        if "OWNER" not in principal.roles and training.trainer_id != principal.user_id:
            raise ApplicationError(
                403, "FORBIDDEN", "Only the assigned trainer can view this roster."
            )
        query = (
            select(
                Booking.id,
                Booking.member_id,
                AppUser.first_name,
                AppUser.last_name,
                Booking.status,
                Booking.created_at,
            )
            .join(AppUser, Booking.member_id == AppUser.id)
            .where(Booking.session_id == session_id)
        )
        if status is not None:
            query = query.where(Booking.status == status)
        total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
        rows = session.execute(
            query.order_by(Booking.created_at, Booking.id).offset(offset).limit(size)
        ).all()
        return [RosterEntry(*row) for row in rows], total
