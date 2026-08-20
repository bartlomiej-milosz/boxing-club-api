"""Map reservation history while keeping migration DDL authoritative."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from boxing_club_api.db.base import Base


class Booking(Base):
    """A reservation or retained cancellation linked to its member and immutable class."""

    __tablename__ = "booking"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    member_id: Mapped[UUID] = mapped_column(ForeignKey("public.member_profile.user_id"))
    session_id: Mapped[UUID] = mapped_column(ForeignKey("public.training_session.id"))
    status: Mapped[str] = mapped_column(String(9))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.app_user.id"))
    cancellation_reason: Mapped[str | None] = mapped_column(String(1000))
