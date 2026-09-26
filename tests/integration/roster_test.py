"""Verify assignment-based roster access and the private-contact boundary."""

import pytest
from fastapi.testclient import TestClient
from tests.support import AccountFactory, SessionPayload

pytestmark = pytest.mark.integration


def test_roster_checks_assignment_roles_and_cancelled_filter(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    _, member = account_factory("member@example.test", ["MEMBER"])
    _, other = account_factory("unassigned@example.test", ["TRAINER"])
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "coach@example.test", "password": "a sample passphrase"},
    )
    trainer = {"Authorization": f"Bearer {login.json()['access_token']}"}
    training = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).json()
    booking = client.post(
        "/api/v1/bookings", headers=member, json={"session_id": training["id"]}
    ).json()
    path = f"/api/v1/sessions/{training['id']}/bookings"
    assert client.get(path, headers=member).status_code == 403
    assert client.get(path, headers=other).status_code == 403
    assert client.get(path).status_code == 401
    owner_result = client.get(path, headers=owner_headers)
    assigned = client.get(path, headers=trainer)
    assert owner_result.status_code == assigned.status_code == 200
    assert owner_result.json() == assigned.json()
    assert set(assigned.json()["items"][0]) == {
        "id",
        "member_id",
        "first_name",
        "last_name",
        "status",
        "created_at",
    }
    assert client.get(f"/api/v1/bookings/{booking['id']}", headers=trainer).status_code == 200
    assert client.get(f"/api/v1/bookings/{booking['id']}", headers=other).status_code == 404
    client.post(f"/api/v1/bookings/{booking['id']}/cancellation", headers=member)
    assert client.get(path + "?status=CANCELLED", headers=trainer).json()["total_items"] == 1
    assert client.get(path + "?status=RESERVED", headers=trainer).json()["items"] == []
