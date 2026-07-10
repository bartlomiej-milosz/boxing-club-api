"""Read explicit account results without leaking password hashes or ORM sessions."""

from dataclasses import dataclass
from uuid import UUID

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory

from .authentication import Principal
from .models import AppUser


@dataclass(frozen=True)
class Account:
    """Public account identity and role names safe to return from an API operation."""

    id: UUID
    email: str
    first_name: str
    last_name: str
    roles: tuple[str, ...]


def get_me(sessions: SessionFactory, principal: Principal) -> Account:
    """Read the current ACTIVE account and return its identity after closing the session."""
    with sessions() as session:
        user = session.get(AppUser, principal.user_id)
        if user is None or user.status != "ACTIVE":
            raise ApplicationError(
                401, "AUTHENTICATION_REQUIRED", "A valid bearer token is required."
            )
        return Account(
            user.id, user.email, user.first_name, user.last_name, tuple(sorted(principal.roles))
        )
