"""Exercise booking eligibility and seat snapshots over HTTP."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support import NOW, AccountFactory, SessionPayload

pytestmark = pytest.mark.integration


def test_reservation_seats_duplicate_full_and_actor_validation(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    member, headers = account_factory("member@example.test", ["MEMBER"])
    _, other = account_factory("other@example.test", ["MEMBER"])
    created = client.post(
        "/api/v1/sessions", headers=owner_headers, json={**class_payload, "capacity": 1}
    ).json()
    payload = {"session_id": created["id"]}
    assert client.post("/api/v1/bookings", json=payload).status_code == 401
    assert client.post("/api/v1/bookings", headers=owner_headers, json=payload).status_code == 403
    assert (
        client.post(
            "/api/v1/bookings", headers=headers, json={**payload, "member_id": member["id"]}
        ).status_code
        == 422
    )
    booked = client.post("/api/v1/bookings", headers=headers, json=payload)
    assert booked.status_code == 201 and booked.json()["member_id"] == member["id"]
    assert booked.headers["Location"] == f"/api/v1/bookings/{booked.json()['id']}"
    assert (
        client.post("/api/v1/bookings", headers=headers, json=payload).json()["code"]
        == "BOOKING_ALREADY_EXISTS"
    )
    assert (
        client.post("/api/v1/bookings", headers=other, json=payload).json()["code"]
        == "SESSION_FULL"
    )
    assert (
        client.get(f"/api/v1/sessions/{created['id']}", headers=headers).json()["available_seats"]
        == 0
    )


def test_booking_cutoff_is_exclusive(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    _, headers = account_factory("member@example.test", ["MEMBER"])
    created = client.post(
        "/api/v1/sessions",
        headers=owner_headers,
        json={**class_payload, "booking_closes_at": NOW.isoformat()},
    ).json()
    assert isinstance(client.app, FastAPI)
    client.app.state.clock = lambda: NOW
    response = client.post("/api/v1/bookings", headers=headers, json={"session_id": created["id"]})
    assert response.status_code == 409 and response.json()["code"] == "BOOKING_CLOSED"
