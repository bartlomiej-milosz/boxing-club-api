"""Resolve immutable request principals and revoke opaque login sessions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select, update

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory

from .models import AppUser, AuthSession, UserRole


@dataclass(frozen=True)
class Principal:
    """Authenticated identifiers and roles detached from the short-lived read session."""

    user_id: UUID
    session_id: UUID
    roles: frozenset[str]


def resolve_principal(sessions: SessionFactory, token: str) -> Principal | None:
    """Resolve an unexpired, unrevoked token for an ACTIVE account, otherwise return None."""
    if not token or len(token) > 512 or not token.isascii():
        return None
    digest = sha256(token.encode("ascii")).hexdigest()
    with sessions() as session:
        record = session.execute(
            select(AuthSession.id, AuthSession.user_id)
            .join(AppUser, AppUser.id == AuthSession.user_id)
            .where(
                AuthSession.token_digest == digest,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > datetime.now(UTC),
                AppUser.status == "ACTIVE",
            )
        ).one_or_none()
        if record is None:
            return None
        roles = frozenset(
            session.scalars(select(UserRole.role).where(UserRole.user_id == record.user_id))
        )
        return Principal(user_id=record.user_id, session_id=record.id, roles=roles)


def require_owner(principal: Principal) -> None:
    """Reject an authenticated caller without the OWNER role."""
    if "OWNER" not in principal.roles:
        raise ApplicationError(403, "FORBIDDEN", "The OWNER role is required.")


def revoke_session(sessions: SessionFactory, principal: Principal) -> None:
    """Revoke only the caller's current login session in its own write transaction."""
    with sessions.begin() as session:
        session.execute(
            update(AuthSession)
            .where(
                AuthSession.id == principal.session_id,
                AuthSession.user_id == principal.user_id,
                AuthSession.revoked_at.is_(None),
            )
            .values(revoked_at=datetime.now(UTC))
        )
