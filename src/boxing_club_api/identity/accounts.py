"""Read explicit account results without leaking password hashes or ORM sessions."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from psycopg import errors
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.pagination import page_offset
from boxing_club_api.db.session import SessionFactory

from .authentication import Principal, require_owner
from .fields import normalize_email, normalize_name
from .models import AppUser, MemberProfile, TrainerProfile, UserRole
from .passwords import hash_password


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


def create_account(
    sessions: SessionFactory,
    principal: Principal,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
    roles: frozenset[str],
    trainer_bio: str | None = None,
) -> Account:
    """Create an owner-authorized account, roles and matching profiles atomically.

    Allow MEMBER, TRAINER or both. Normalize fields and hash the password
    before opening a transaction. Translate duplicate normalized emails to a
    conflict only after rollback; propagate unrelated integrity failures.
    """
    require_owner(principal)
    if not roles or not roles <= {"MEMBER", "TRAINER"}:
        raise ApplicationError(422, "VALIDATION_ERROR", "Choose MEMBER, TRAINER or both.")
    if trainer_bio is not None and "TRAINER" not in roles:
        raise ApplicationError(422, "VALIDATION_ERROR", "A trainer bio requires the TRAINER role.")
    email = normalize_email(email)
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    password_hash = hash_password(password)
    user_id = uuid4()
    created_at = datetime.now(UTC)
    result = Account(user_id, email, first_name, last_name, tuple(sorted(roles)))
    try:
        with sessions.begin() as session:
            session.add(
                AppUser(
                    id=user_id,
                    email=email,
                    first_name=first_name,
                    last_name=last_name,
                    password_hash=password_hash,
                    status="ACTIVE",
                    created_at=created_at,
                )
            )
            session.flush()
            session.add_all(UserRole(user_id=user_id, role=role) for role in sorted(roles))
            if "MEMBER" in roles:
                session.add(
                    MemberProfile(
                        user_id=user_id,
                        joined_on=created_at.astimezone(ZoneInfo("Europe/Warsaw")).date(),
                    )
                )
            if "TRAINER" in roles:
                session.add(TrainerProfile(user_id=user_id, bio=trainer_bio, active=True))
    except IntegrityError as error:
        if (
            isinstance(error.orig, errors.UniqueViolation)
            and error.orig.diag.constraint_name == "uq_app_user_email"
        ):
            raise ApplicationError(
                409, "EMAIL_ALREADY_EXISTS", "An account with this email already exists."
            ) from error
        raise
    return result


def list_accounts(
    sessions: SessionFactory, principal: Principal, *, page: int, size: int, role: str | None = None
) -> tuple[list[Account], int]:
    """Return an owner-only page ordered by email and ID, optionally filtered by role."""
    require_owner(principal)
    offset = page_offset(page, size)
    statement = select(AppUser)
    if role is not None:
        statement = statement.where(
            AppUser.id.in_(select(UserRole.user_id).where(UserRole.role == role))
        )
    with sessions() as session:
        total = session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        users = session.scalars(
            statement.order_by(AppUser.email, AppUser.id).offset(offset).limit(size)
        ).all()
        roles_by_user: dict[UUID, list[str]] = {user.id: [] for user in users}
        if users:
            for user_id, role_name in session.execute(
                select(UserRole.user_id, UserRole.role)
                .where(UserRole.user_id.in_(roles_by_user))
                .order_by(UserRole.role)
            ):
                roles_by_user[user_id].append(role_name)
        return [
            Account(
                user.id, user.email, user.first_name, user.last_name, tuple(roles_by_user[user.id])
            )
            for user in users
        ], total
