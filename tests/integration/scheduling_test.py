"""Verify class creation, schedule boundaries and immutable catalog snapshots."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tests.support import NOW, AccountFactory, SessionPayload

pytestmark = pytest.mark.integration


def test_owner_creates_class_with_concrete_cutoff(
    client: TestClient, owner_headers: dict[str, str], class_payload: SessionPayload
) -> None:
    response = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload)
    assert response.status_code == 201
    body = response.json()
    assert response.headers["Location"] == f"/api/v1/sessions/{body['id']}"
    assert body["booking_closes_at"] == body["starts_at"]
    assert body["available_seats"] == body["capacity"] == 12
    assert body["status"] == "SCHEDULED"


@pytest.mark.parametrize(
    "changes",
    [
        {"capacity": 13},
        {"capacity": 0},
        {"starts_at": "2030-01-02T10:00:00"},
        {"ends_at": "2030-01-01T10:00:00Z"},
        {"starts_at": NOW.isoformat()},
        {"booking_closes_at": (NOW + timedelta(days=2)).isoformat()},
        {"title": " "},
        {"unexpected": True},
    ],
)
def test_invalid_classes_fail(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    changes: dict[str, object],
) -> None:
    assert (
        client.post(
            "/api/v1/sessions", headers=owner_headers, json={**class_payload, **changes}
        ).status_code
        == 422
    )


@pytest.mark.parametrize("catalog", ["room", "trainer"])
def test_inactive_catalog_blocks_new_classes(
    client: TestClient, owner_headers: dict[str, str], class_payload: SessionPayload, catalog: str
) -> None:
    path = "rooms" if catalog == "room" else "trainers"
    resource_id = class_payload["room_id"] if catalog == "room" else class_payload["trainer_id"]
    assert (
        client.patch(
            f"/api/v1/{path}/{resource_id}", headers=owner_headers, json={"active": False}
        ).status_code
        == 200
    )
    assert (
        client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).status_code
        == 409
    )


def test_session_creation_permissions_and_unknown_catalog(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    _, member = account_factory("member@example.test", ["MEMBER"])
    assert client.post("/api/v1/sessions", json=class_payload).status_code == 401
    assert client.post("/api/v1/sessions", headers=member, json=class_payload).status_code == 403
    assert (
        client.post(
            "/api/v1/sessions",
            headers=owner_headers,
            json={**class_payload, "room_id": str(uuid4())},
        ).status_code
        == 404
    )
