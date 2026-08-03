"""Map catalog records without creating or altering database tables."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column

from boxing_club_api.db.base import Base


class Room(Base):
    """Room catalog record with positive capacity enforced by SQL and immutable through the API."""

    __tablename__ = "room"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int]
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class TrainingSession(Base):
    """Dated class whose resources, times and capacity are fixed after creation."""

    __tablename__ = "training_session"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    trainer_id: Mapped[UUID] = mapped_column(ForeignKey("public.trainer_profile.user_id"))
    room_id: Mapped[UUID] = mapped_column(ForeignKey("public.room.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    booking_closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    capacity: Mapped[int]
    status: Mapped[str] = mapped_column(String(9))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("public.app_user.id"))
    cancellation_reason: Mapped[str | None] = mapped_column(String(1000))
