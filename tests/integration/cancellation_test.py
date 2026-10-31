"""Verify cancellation boundaries, ownership, audit replay and later rebooking."""

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.support import NOW, AccountFactory, SessionPayload

from boxing_club_api.db.session import SessionFactory

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


def test_owner_cancellation_preserves_member_audit_and_releases_slot(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
) -> None:
    _, member = account_factory("member@example.test", ["MEMBER"])
    _, other = account_factory("other@example.test", ["MEMBER"])
    training = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).json()
    first = client.post(
        "/api/v1/bookings", headers=member, json={"session_id": training["id"]}
    ).json()
    prior = client.post(
        f"/api/v1/bookings/{first['id']}/cancellation",
        headers=member,
        json={"reason": "Personal reason"},
    ).json()
    second = client.post(
        "/api/v1/bookings", headers=other, json={"session_id": training["id"]}
    ).json()
    path = f"/api/v1/sessions/{training['id']}/cancellation"
    assert client.post(path, headers=member, json={"reason": "Unauthorized"}).status_code == 403
    result = client.post(path, headers=owner_headers, json={"reason": "Trainer unavailable"})
    assert result.status_code == 200 and result.json()["status"] == "CANCELLED"
    assert (
        client.post(path, headers=owner_headers, json={"reason": "Changed reason"}).json()
        == result.json()
    )
    assert client.get(f"/api/v1/bookings/{first['id']}", headers=member).json() == prior
    updated = client.get(f"/api/v1/bookings/{second['id']}", headers=other).json()
    assert (
        updated["status"] == "CANCELLED" and updated["cancellation_reason"] == "Trainer unavailable"
    )
    assert (
        client.post("/api/v1/bookings", headers=member, json={"session_id": training["id"]}).json()[
            "code"
        ]
        == "SESSION_CANCELLED"
    )
    assert (
        client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).status_code
        == 201
    )


def test_class_cancellation_failure_rolls_back_reservation_updates(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
    sessions: SessionFactory,
) -> None:
    """Force a SQL failure after reservation updates and verify the whole class transaction rolls back."""
    from collections.abc import Sequence
    from uuid import UUID

    from sqlalchemy import event, update
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy.orm import Session, UOWTransaction

    from boxing_club_api.bookings.models import Booking
    from boxing_club_api.identity.authentication import resolve_principal
    from boxing_club_api.scheduling.cancellation import cancel_class
    from boxing_club_api.scheduling.models import TrainingSession

    _, member = account_factory("member@example.test", ["MEMBER"])
    training = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).json()
    booked = client.post(
        "/api/v1/bookings", headers=member, json={"session_id": training["id"]}
    ).json()
    owner = resolve_principal(sessions, owner_headers["Authorization"].split()[1])
    assert owner is not None

    def fail_class_write(
        session: Session, _context: UOWTransaction, _instances: Sequence[object] | None
    ) -> None:
        for item in session.dirty:
            if isinstance(item, TrainingSession) and item.status == "CANCELLED":
                session.execute(
                    update(TrainingSession).where(TrainingSession.id == item.id).values(capacity=0)
                )

    event.listen(sessions, "before_flush", fail_class_write)
    try:
        with pytest.raises(IntegrityError):
            cancel_class(
                sessions, owner, UUID(training["id"]), reason="Test rollback", clock=lambda: NOW
            )
    finally:
        event.remove(sessions, "before_flush", fail_class_write)
    with sessions() as session:
        assert session.get_one(TrainingSession, UUID(training["id"])).status == "SCHEDULED"
        assert session.get_one(Booking, UUID(booked["id"])).status == "RESERVED"
