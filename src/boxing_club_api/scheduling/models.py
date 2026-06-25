from uuid import UUID

from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from boxing_club_api.db.base import Base


class Room(Base):
    __tablename__ = "room"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    capacity: Mapped[int]
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
