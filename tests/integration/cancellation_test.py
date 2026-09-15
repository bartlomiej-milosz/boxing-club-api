"""Verify cancellation boundaries, ownership, audit replay and later rebooking."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support import NOW, AccountFactory, SessionPayload

pytestmark = pytest.mark.integration


def test_member_cancellation_replay_rebooking_and_exact_start(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    _, member = account_factory("member@example.test", ["MEMBER"])
    _, other = account_factory("other@example.test", ["MEMBER"])
    training = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).json()
    payload = {"session_id": training["id"]}
    booked = client.post("/api/v1/bookings", headers=member, json=payload).json()
    path = f"/api/v1/bookings/{booked['id']}/cancellation"
    assert client.post(path, headers=other).status_code == 404
    cancelled = client.post(path, headers=member, json={"reason": "Changed plans"})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert isinstance(client.app, FastAPI)
    client.app.state.clock = lambda: NOW + timedelta(minutes=1)
    assert (
        client.post(path, headers=member, json={"reason": "Different reason"}).json()
        == cancelled.json()
    )
    rebooked = client.post("/api/v1/bookings", headers=member, json=payload)
    assert rebooked.status_code == 201 and rebooked.json()["id"] != booked["id"]
    client.app.state.clock = lambda: datetime.fromisoformat(class_payload["starts_at"])
    assert (
        client.post(
            f"/api/v1/bookings/{rebooked.json()['id']}/cancellation", headers=member
        ).status_code
        == 409
    )
    assert client.post(path, headers=member).json() == cancelled.json()
    history = client.get("/api/v1/me/bookings?status=CANCELLED", headers=member).json()
    assert history["total_items"] == 1 and history["items"] == [cancelled.json()]
