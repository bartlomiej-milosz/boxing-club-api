"""Check identity constraints and transaction rollback on real PostgreSQL."""

from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from psycopg import errors
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.models import AppUser, MemberProfile, TrainerProfile, UserRole

pytestmark = pytest.mark.integration


def _user(user_id: UUID, email: str) -> AppUser:
    return AppUser(
        id=user_id,
        email=email,
        password_hash="unused-in-schema-tests",
        first_name="Sample",
        last_name="Member",
        status="ACTIVE",
        created_at=datetime.now(UTC),
    )


def test_role_and_profiles_commit_in_one_transaction(sessions: SessionFactory) -> None:
    user_id = uuid4()
    joined_on = date(2026, 1, 1)
    with sessions.begin() as session:
        session.add(_user(user_id, "member@example.test"))
        session.flush()
        session.add_all(
            [
                UserRole(user_id=user_id, role="MEMBER"),
                MemberProfile(user_id=user_id, joined_on=joined_on),
                UserRole(user_id=user_id, role="TRAINER"),
                TrainerProfile(user_id=user_id, active=True),
            ]
        )

    with sessions() as session:
        assert session.get_one(MemberProfile, user_id).joined_on == joined_on
        assert session.get_one(TrainerProfile, user_id).active
        assert session.get(UserRole, (user_id, "MEMBER")) is not None
        assert session.get(UserRole, (user_id, "TRAINER")) is not None


def test_profile_failure_rolls_back_user_and_role(sessions: SessionFactory) -> None:
    user_id = uuid4()
    with pytest.raises(IntegrityError) as failure, sessions.begin() as session:
        session.add(_user(user_id, "member@example.test"))
        session.flush()
        session.add(UserRole(user_id=user_id, role="MEMBER"))
        session.flush()
        session.execute(insert(MemberProfile).values(user_id=user_id, joined_on=None))

    assert isinstance(failure.value.orig, errors.NotNullViolation)
    with sessions() as session:
        assert session.get(AppUser, user_id) is None
        assert session.get(UserRole, (user_id, "MEMBER")) is None


def test_invalid_role_is_rejected(sessions: SessionFactory) -> None:
    with pytest.raises(IntegrityError) as failure, sessions.begin() as session:
        user_id = uuid4()
        session.add(_user(user_id, "member@example.test"))
        session.flush()
        session.add(UserRole(user_id=user_id, role="ADMIN"))

    assert isinstance(failure.value.orig, errors.CheckViolation)
    assert failure.value.orig.diag.constraint_name == "ck_user_role_role"


def test_email_must_be_normalized_and_unique(sessions: SessionFactory) -> None:
    with sessions.begin() as session:
        session.add(_user(uuid4(), "member@example.test"))

    with pytest.raises(IntegrityError) as duplicate, sessions.begin() as session:
        session.add(_user(uuid4(), "member@example.test"))
    assert isinstance(duplicate.value.orig, errors.UniqueViolation)
    assert duplicate.value.orig.diag.constraint_name == "uq_app_user_email"

    with pytest.raises(IntegrityError) as unnormalized, sessions.begin() as session:
        session.add(_user(uuid4(), "MEMBER@example.test"))
    assert isinstance(unnormalized.value.orig, errors.CheckViolation)
    assert unnormalized.value.orig.diag.constraint_name == "ck_app_user_email_normalized"
