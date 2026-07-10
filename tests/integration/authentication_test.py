"""Check bearer lifecycle, account status and authentication session boundaries."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.models import AppUser, AuthSession

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer unknown", "Bearer"])
def test_me_requires_a_valid_bearer(client: TestClient, authorization: str | None) -> None:
    headers = {"Authorization": authorization} if authorization is not None else {}
    response = client.get("/api/v1/me", headers=headers)
    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_me_and_logout_revoke_only_current_session(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory
) -> None:
    another = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.test", "password": "a sample passphrase"},
    ).json()["access_token"]
    response = client.get("/api/v1/me", headers=owner_headers)
    assert response.status_code == 200
    assert set(response.json()) == {"id", "email", "first_name", "last_name", "roles"}
    assert response.json()["roles"] == ["OWNER"]
    assert client.post("/api/v1/auth/logout", headers=owner_headers).status_code == 204
    assert client.get("/api/v1/me", headers=owner_headers).status_code == 401
    assert client.post("/api/v1/auth/logout", headers=owner_headers).status_code == 401
    assert (
        client.get("/api/v1/me", headers={"Authorization": f"Bearer {another}"}).status_code == 200
    )
    with sessions() as session:
        records = session.scalars(select(AuthSession)).all()
        assert sum(item.revoked_at is not None for item in records) == 1


@pytest.mark.parametrize("state", ["expired", "revoked", "blocked"])
def test_previously_valid_token_fails_after_state_change(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory, state: str
) -> None:
    with sessions.begin() as session:
        if state == "blocked":
            session.execute(update(AppUser).values(status="BLOCKED"))
        elif state == "revoked":
            session.execute(update(AuthSession).values(revoked_at=datetime.now(UTC)))
        else:
            now = datetime.now(UTC)
            session.execute(
                update(AuthSession).values(
                    created_at=now - timedelta(hours=10), expires_at=now - timedelta(hours=1)
                )
            )
    assert client.get("/api/v1/me", headers=owner_headers).status_code == 401


def test_authentication_returns_connection_before_logout_write(
    client: TestClient, owner_headers: dict[str, str], database_url: URL
) -> None:
    engine = create_engine(database_url, pool_size=1, max_overflow=0, pool_timeout=0.2)
    assert isinstance(client.app, FastAPI)
    assert isinstance(engine.pool, QueuePool)
    original = client.app.state.db_sessions
    try:
        client.app.state.db_sessions = sessionmaker(engine)
        assert client.post("/api/v1/auth/logout", headers=owner_headers).status_code == 204
        assert engine.pool.checkedout() == 0
    finally:
        client.app.state.db_sessions = original
        engine.dispose()
