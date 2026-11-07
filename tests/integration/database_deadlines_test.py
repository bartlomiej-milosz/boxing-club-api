"""Exercise real PostgreSQL lock/statement deadlines and recovery through HTTP."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx2 import Response
from sqlalchemy import Connection, Engine, event, select, text
from sqlalchemy.pool import QueuePool

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.models import AuthSession
from boxing_club_api.scheduling.models import Room

pytestmark = pytest.mark.integration


def assert_unavailable(response: Response) -> None:
    """Require the common transient envelope and its matching correlation header."""
    assert response.status_code == 503
    body = response.json()
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "TEMPORARILY_UNAVAILABLE"
    assert body["request_id"] == response.headers["X-Request-ID"]


def application_engine(client: TestClient) -> Engine:
    """Select the API's engine rather than the independent blocking transaction's pool."""
    assert isinstance(client.app, FastAPI)
    sessions: SessionFactory = client.app.state.db_sessions
    engine = sessions.kw["bind"]
    assert isinstance(engine, Engine)
    return engine


def test_each_connection_has_deadlines_and_readiness_overrides_are_local(
    client: TestClient,
) -> None:
    engine = application_engine(client)
    assert client.get("/health/ready").status_code == 200
    with engine.connect() as first, engine.connect() as second:
        for connection in (first, second):
            assert tuple(
                connection.execute(
                    text(
                        "SELECT current_setting('lock_timeout'), current_setting('statement_timeout')"
                    )
                ).one()
            ) == ("2s", "5s")


@pytest.mark.concurrency
def test_unique_insert_times_out_before_blocker_commits_and_pool_recovers(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory
) -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        with sessions.begin() as blocker:
            blocker.add(Room(id=uuid4(), name="Locked room", capacity=2, active=True))
            blocker.flush()
            future = executor.submit(
                client.post,
                "/api/v1/rooms",
                headers=owner_headers,
                json={"name": "Locked room", "capacity": 2},
            )
            # The response must arrive while the conflicting insert is still uncommitted.
            assert_unavailable(future.result(timeout=7))
            assert client.get("/api/v1/rooms", headers=owner_headers).json()["items"] == []
    duplicate = client.post(
        "/api/v1/rooms", headers=owner_headers, json={"name": "Locked room", "capacity": 2}
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "ROOM_NAME_ALREADY_EXISTS"
    assert (
        client.post(
            "/api/v1/rooms", headers=owner_headers, json={"name": "Later room", "capacity": 2}
        ).status_code
        == 201
    )
    with sessions() as session:
        assert sorted(session.scalars(select(Room.name))) == ["Later room", "Locked room"]


@pytest.mark.concurrency
@pytest.mark.parametrize("operation", ["authentication_read", "logout"])
def test_read_and_logout_lock_waits_are_bounded_and_leave_token_usable(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory, operation: str
) -> None:
    with ThreadPoolExecutor(max_workers=1) as executor:
        with sessions.begin() as blocker:
            if operation == "authentication_read":
                blocker.execute(text("LOCK TABLE public.app_user IN ACCESS EXCLUSIVE MODE"))
                future = executor.submit(client.get, "/api/v1/me", headers=owner_headers)
            else:
                blocker.scalar(select(AuthSession).with_for_update())
                future = executor.submit(client.post, "/api/v1/auth/logout", headers=owner_headers)
            assert_unavailable(future.result(timeout=7))
            assert blocker.scalars(select(AuthSession.revoked_at)).all() == [None]
    assert client.get("/api/v1/me", headers=owner_headers).status_code == 200
    assert client.post("/api/v1/auth/logout", headers=owner_headers).status_code == 204
    assert client.get("/api/v1/me", headers=owner_headers).status_code == 401


def test_slow_authentication_statement_times_out_and_returns_its_pool_connection(
    client: TestClient, owner_headers: dict[str, str]
) -> None:
    engine = application_engine(client)

    def slow_query(
        _connection: Connection,
        _cursor: object,
        statement: str,
        parameters: object,
        _context: object,
        _executemany: bool,
    ) -> tuple[str, object]:
        if statement.startswith("SELECT") and "public.auth_session" in statement:
            return "SELECT pg_sleep(10)", ()
        return statement, parameters

    event.listen(engine, "before_cursor_execute", slow_query, retval=True)
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            response = executor.submit(client.get, "/api/v1/me", headers=owner_headers).result(
                timeout=7
            )
        assert_unavailable(response)
    finally:
        event.remove(engine, "before_cursor_execute", slow_query)
    assert isinstance(engine.pool, QueuePool)
    assert engine.pool.checkedout() == 0
    assert client.get("/api/v1/me", headers=owner_headers).status_code == 200
