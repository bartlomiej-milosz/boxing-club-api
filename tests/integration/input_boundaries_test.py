"""Protect biography, timestamp and shared pagination boundaries at the HTTP layer."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import select
from tests.support import AccountFactory, SessionPayload

from boxing_club_api.core.pagination import MAX_OFFSET
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.models import AppUser, MemberProfile, TrainerProfile, UserRole

pytestmark = pytest.mark.integration


def assert_invalid(response: Response) -> None:
    """Require a correlated validation envelope without submitted data or SQL details."""
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "VALIDATION_ERROR"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_nul_biography_rejects_account_before_any_identity_rows_are_created(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory
) -> None:
    response = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "invalid-bio@example.test",
            "initial_password": "a sample passphrase",
            "first_name": "Sample",
            "last_name": "Trainer",
            "roles": ["MEMBER", "TRAINER"],
            "trainer_bio": "hello\x00world",
        },
    )
    assert_invalid(response)
    assert "hello" not in response.text
    with sessions() as session:
        assert session.scalars(select(AppUser.email)).all() == ["owner@example.test"]
        assert session.scalars(select(UserRole.role)).all() == ["OWNER"]
        assert session.scalars(select(MemberProfile.user_id)).all() == []
        assert session.scalars(select(TrainerProfile.user_id)).all() == []


def test_biography_accepts_unicode_rejects_nul_without_mutation_and_can_be_cleared(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory
) -> None:
    bio = "Zażółć gęślą jaźń 🥊\nТренер"
    created = client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "coach@example.test",
            "initial_password": "a sample passphrase",
            "first_name": "Sample",
            "last_name": "Trainer",
            "roles": ["TRAINER"],
            "trainer_bio": bio,
        },
    )
    assert created.status_code == 201
    trainer_id = created.json()["id"]
    path = f"/api/v1/trainers/{trainer_id}"
    assert_invalid(client.patch(path, headers=owner_headers, json={"bio": "hello\x00world"}))
    with sessions() as session:
        assert session.get_one(TrainerProfile, UUID(trainer_id)).bio == bio
    patched = client.patch(path, headers=owner_headers, json={"bio": bio + "\nCoach"})
    assert patched.status_code == 200 and patched.json()["bio"] == bio + "\nCoach"
    cleared = client.patch(path, headers=owner_headers, json={"bio": None})
    assert cleared.status_code == 200 and cleared.json()["bio"] is None


@pytest.mark.parametrize(
    "query",
    [
        {"from": "9999-12-31T00:00:00Z"},
        {"from": "0001-01-01T00:00:00+01:00", "to": "0001-01-02T00:00:00Z"},
        {"from": "9999-12-30T00:00:00Z", "to": "9999-12-31T23:59:59-01:00"},
    ],
)
def test_schedule_rejects_default_end_or_utc_conversion_overflow(
    client: TestClient, owner_headers: dict[str, str], query: dict[str, str]
) -> None:
    assert_invalid(client.get("/api/v1/sessions", headers=owner_headers, params=query))


@pytest.mark.parametrize(
    "query",
    [
        {"from": "9999-12-15T00:00:00Z"},
        {"from": "9999-12-30T00:00:00Z", "to": "9999-12-31T23:59:59Z"},
        {"from": "0001-01-01T00:00:00Z", "to": "0001-01-02T00:00:00Z"},
        {"from": "2030-01-01T00:00:00Z", "to": "2030-04-01T00:00:00Z"},
    ],
)
def test_schedule_preserves_representable_boundary_dates_and_ninety_day_limit(
    client: TestClient, owner_headers: dict[str, str], query: dict[str, str]
) -> None:
    response = client.get("/api/v1/sessions", headers=owner_headers, params=query)
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("starts_at", "9999-12-31T23:59:59-01:00"),
        ("ends_at", "9999-12-31T23:59:59-01:00"),
        ("booking_closes_at", "0001-01-01T00:00:00+01:00"),
    ],
)
def test_class_creation_rejects_utc_overflow(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    field: str,
    value: str,
) -> None:
    assert_invalid(
        client.post("/api/v1/sessions", headers=owner_headers, json={**class_payload, field: value})
    )


@pytest.mark.parametrize("field", ["from", "to"])
def test_history_rejects_unrepresentable_utc_filter(
    client: TestClient, account_factory: AccountFactory, field: str
) -> None:
    _, headers = account_factory("member@example.test", ["MEMBER"])
    assert_invalid(
        client.get(
            "/api/v1/me/bookings",
            headers=headers,
            params={field: "9999-12-31T23:59:59-01:00"},
        )
    )


@pytest.mark.parametrize("family", ["users", "trainers", "rooms", "sessions", "history", "roster"])
def test_all_list_families_reject_offset_overflow_and_accept_representable_empty_pages(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
    family: str,
) -> None:
    headers = owner_headers
    path = f"/api/v1/{family}"
    if family == "history":
        _, headers = account_factory("member@example.test", ["MEMBER"])
        path = "/api/v1/me/bookings"
    elif family == "roster":
        training = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload)
        assert training.status_code == 201
        path = f"/api/v1/sessions/{training.json()['id']}/bookings"
    for size in (20, 100):
        assert_invalid(client.get(path, headers=headers, params={"page": MAX_OFFSET, "size": size}))
        # The first overflowing page must fail; the adjacent representable one is valid.
        assert_invalid(
            client.get(path, headers=headers, params={"page": MAX_OFFSET // size + 1, "size": size})
        )
        page = MAX_OFFSET // size
        response = client.get(path, headers=headers, params={"page": page, "size": size})
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["page"] == page
    assert client.get(path, headers=headers, params={"page": 0, "size": 1}).status_code == 200
