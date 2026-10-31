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


@pytest.mark.parametrize("change", ["deactivate", "time"])
def test_creation_rechecks_catalog_and_clock_after_waiting(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    sessions: SessionFactory,
    change: str,
) -> None:
    """Coordinate a blocked creator with a committed catalog or clock change without sleeps."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from sqlalchemy import Connection, Engine, event

    from boxing_club_api.scheduling.models import Room

    principal = resolve_principal(sessions, owner_headers["Authorization"].split()[1])
    assert principal is not None
    engine = sessions.kw["bind"]
    assert isinstance(engine, Engine)
    waiting = Event()
    clock_state = {"now": NOW}

    def before_execute(
        _connection: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        if "public.room" in statement and "FOR UPDATE" in statement:
            waiting.set()

    def attempt() -> int:
        try:
            create_session(
                sessions,
                principal,
                title=class_payload["title"],
                trainer_id=UUID(class_payload["trainer_id"]),
                room_id=UUID(class_payload["room_id"]),
                starts_at=datetime.fromisoformat(class_payload["starts_at"]),
                ends_at=datetime.fromisoformat(class_payload["ends_at"]),
                capacity=class_payload["capacity"],
                clock=lambda: clock_state["now"],
            )
        except ApplicationError as error:
            return error.status_code
        return 201

    with ThreadPoolExecutor(max_workers=1) as executor:
        try:
            with sessions.begin() as locker:
                room = locker.get_one(Room, UUID(class_payload["room_id"]), with_for_update=True)
                event.listen(engine, "before_cursor_execute", before_execute)
                future = executor.submit(attempt)
                assert waiting.wait(timeout=10)
                if change == "deactivate":
                    room.active = False
                else:
                    clock_state["now"] = datetime.fromisoformat(class_payload["starts_at"])
            assert future.result(timeout=10) == (409 if change == "deactivate" else 422)
        finally:
            event.remove(engine, "before_cursor_execute", before_execute)
    with sessions() as session:
        assert session.scalar(select(func.count()).select_from(TrainingSession)) == 0
