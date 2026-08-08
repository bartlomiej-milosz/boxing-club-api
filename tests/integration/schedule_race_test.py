"""Prove room and trainer overlap protection across independent transactions."""

from datetime import datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.support import NOW, AccountFactory, SessionPayload, run_race

from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import resolve_principal
from boxing_club_api.scheduling.models import TrainingSession
from boxing_club_api.scheduling.sessions import create_session

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


@pytest.mark.parametrize("resource", ["room", "trainer"])
def test_simultaneous_overlaps_have_one_winner(
    client: TestClient,
    owner_headers: dict[str, str],
    sessions: SessionFactory,
    class_payload: SessionPayload,
    account_factory: AccountFactory,
    resource: str,
) -> None:
    principal = resolve_principal(sessions, owner_headers["Authorization"].split()[1])
    assert principal is not None
    first = dict(class_payload)
    second = dict(class_payload)
    if resource == "room":
        trainer, _ = account_factory("othercoach@example.test", ["TRAINER"])
        second["trainer_id"] = trainer["id"]
    else:
        room = client.post(
            "/api/v1/rooms", headers=owner_headers, json={"name": "Second room", "capacity": 12}
        ).json()
        second["room_id"] = room["id"]

    def attempt(payload: dict[str, object]) -> int:
        try:
            create_session(
                sessions,
                principal,
                title=str(payload["title"]),
                trainer_id=UUID(str(payload["trainer_id"])),
                room_id=UUID(str(payload["room_id"])),
                starts_at=datetime.fromisoformat(str(payload["starts_at"])),
                ends_at=datetime.fromisoformat(str(payload["ends_at"])),
                capacity=12,
                clock=lambda: NOW,
            )
        except ApplicationError as error:
            assert error.code == "SCHEDULE_CONFLICT"
            return error.status_code
        return 201

    results = run_race([lambda: attempt(first), lambda: attempt(second)])
    assert sorted(results) == [201, 409]
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 1
    adjacent = {
        **class_payload,
        "starts_at": (NOW + timedelta(days=1, hours=1)).isoformat(),
        "ends_at": (NOW + timedelta(days=1, hours=2)).isoformat(),
    }
    assert client.post("/api/v1/sessions", headers=owner_headers, json=adjacent).status_code == 201
