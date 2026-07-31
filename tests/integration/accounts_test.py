"""Verify controlled account creation, profile atomicity and credential-safe responses."""

from collections.abc import Sequence
from typing import NotRequired, TypedDict
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from psycopg import errors
from sqlalchemy import event, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, UOWTransaction

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.accounts import create_account
from boxing_club_api.identity.authentication import resolve_principal
from boxing_club_api.identity.models import AppUser, MemberProfile, TrainerProfile, UserRole
from boxing_club_api.identity.passwords import verify_password


class AccountPayload(TypedDict):
    """Valid account fields whose individual values can be varied by validation tests."""

    email: str
    initial_password: str
    first_name: str
    last_name: str
    roles: list[str]
    trainer_bio: NotRequired[str]


pytestmark = pytest.mark.integration


def account_payload(
    email: str = "member@example.test", roles: list[str] | None = None
) -> AccountPayload:
    """Supply valid account input so individual tests can vary one contract boundary."""
    return {
        "email": email,
        "initial_password": "a member passphrase",
        "first_name": "Sample",
        "last_name": "Member",
        "roles": roles if roles is not None else ["MEMBER"],
    }


@pytest.mark.parametrize("roles", [["MEMBER"], ["TRAINER"], ["MEMBER", "TRAINER"]])
def test_owner_creates_roles_and_profiles_atomically(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory, roles: list[str]
) -> None:
    payload = account_payload("  MEMBER@example.test ", roles)
    if "TRAINER" in roles:
        payload["trainer_bio"] = "Boxing coach"
    response = client.post("/api/v1/users", json=payload, headers=owner_headers)
    assert response.status_code == 201
    body = response.json()
    user_id = UUID(body["id"])
    assert response.headers["Location"] == f"/api/v1/users/{user_id}"
    assert set(body) == {"id", "email", "first_name", "last_name", "roles"}
    assert body["email"] == "member@example.test"
    assert body["roles"] == sorted(roles)
    with sessions() as session:
        user = session.get_one(AppUser, user_id)
        assert verify_password("a member passphrase", user.password_hash)
        assert set(
            session.scalars(select(UserRole.role).where(UserRole.user_id == user_id))
        ) == set(roles)
        assert (session.get(MemberProfile, user_id) is not None) == ("MEMBER" in roles)
        trainer = session.get(TrainerProfile, user_id)
        assert (trainer is not None) == ("TRAINER" in roles)
        if trainer is not None:
            assert trainer.active and trainer.bio == "Boxing coach"
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "member@example.test", "password": "a member passphrase"},
        ).status_code
        == 200
    )


def test_account_creation_requires_owner_and_rejects_normalized_duplicate(
    client: TestClient, owner_headers: dict[str, str]
) -> None:
    payload = account_payload()
    assert client.post("/api/v1/users", json=payload).status_code == 401
    assert client.post("/api/v1/users", json=payload, headers=owner_headers).status_code == 201
    duplicate = client.post(
        "/api/v1/users", json={**payload, "email": " MEMBER@example.test "}, headers=owner_headers
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "EMAIL_ALREADY_EXISTS"
    token = client.post(
        "/api/v1/auth/login",
        json={"email": payload["email"], "password": payload["initial_password"]},
    ).json()["access_token"]
    assert (
        client.post(
            "/api/v1/users",
            json=account_payload("other@example.test"),
            headers={"Authorization": f"Bearer {token}"},
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"roles": ["OWNER"]},
        {"roles": ["MEMBER", "OWNER"]},
        {"roles": []},
        {"first_name": "   "},
        {"initial_password": "short"},
        {"trainer_bio": "Unexpected biography"},
        {"actor_id": "unexpected"},
    ],
)
def test_account_validation_rejects_unsupported_inputs_without_echoing_password(
    client: TestClient, owner_headers: dict[str, str], changes: dict[str, object]
) -> None:
    payload: dict[str, object] = {**account_payload(), **changes}
    response = client.post("/api/v1/users", json=payload, headers=owner_headers)
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
    password = payload["initial_password"]
    assert isinstance(password, str)
    assert password not in response.text


def test_failed_profile_write_rolls_back_account_roles_and_profiles(
    sessions: SessionFactory, owner_headers: dict[str, str]
) -> None:
    principal = resolve_principal(sessions, owner_headers["Authorization"].split()[1])
    assert principal is not None

    def invalidate_profile(
        session: Session, _context: UOWTransaction, _instances: Sequence[object] | None
    ) -> None:
        for item in session.new:
            if isinstance(item, TrainerProfile):
                # Bypass the ORM attribute type to exercise a real SQL NOT NULL failure.
                session.execute(insert(TrainerProfile).values(user_id=item.user_id, active=None))

    event.listen(sessions, "before_flush", invalidate_profile)
    try:
        with pytest.raises(IntegrityError) as failure:
            create_account(
                sessions,
                principal,
                email="rollback@example.test",
                first_name="Sample",
                last_name="Trainer",
                password="a sample passphrase",
                roles=frozenset({"MEMBER", "TRAINER"}),
            )
    finally:
        event.remove(sessions, "before_flush", invalidate_profile)
    assert isinstance(failure.value.orig, errors.NotNullViolation)
    assert failure.value.orig.diag.column_name == "active"
    with sessions() as session:
        assert (
            session.scalar(select(AppUser.id).where(AppUser.email == "rollback@example.test"))
            is None
        )
        assert session.scalars(select(UserRole.role)).all() == ["OWNER"]
        assert session.scalars(select(MemberProfile.user_id)).all() == []
        assert session.scalars(select(TrainerProfile.user_id)).all() == []
