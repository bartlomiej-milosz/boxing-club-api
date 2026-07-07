"""Map accounts, roles, profiles and login sessions to the identity schema."""

from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CHAR, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from boxing_club_api.db.base import Base


class AppUser(Base):
    """Account identity and password hash shared by all roles; never serialize this model directly."""

    __tablename__ = "app_user"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(Text)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(7))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserRole(Base):
    """One role assignment identified by the user and role composite key."""

    __tablename__ = "user_role"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[UUID] = mapped_column(ForeignKey("public.app_user.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(7), primary_key=True)


class MemberProfile(Base):
    """Member-specific data created atomically with the MEMBER role."""

    __tablename__ = "member_profile"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[UUID] = mapped_column(ForeignKey("public.app_user.id"), primary_key=True)
    joined_on: Mapped[date]


class TrainerProfile(Base):
    """Trainer catalog data whose active flag controls eligibility for new sessions."""

    __tablename__ = "trainer_profile"
    __table_args__ = {"schema": "public"}

    user_id: Mapped[UUID] = mapped_column(ForeignKey("public.app_user.id"), primary_key=True)
    bio: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool]


class AuthSession(Base):
    """Opaque login session represented by a digest, expiry and optional revocation time."""

    __tablename__ = "auth_session"
    __table_args__ = {"schema": "public"}

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("public.app_user.id"))
    token_digest: Mapped[str] = mapped_column(CHAR(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
