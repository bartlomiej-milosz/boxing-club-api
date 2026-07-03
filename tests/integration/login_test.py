from base64 import urlsafe_b64decode
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import URL, select, update

from boxing_club_api.application.factory import create_app
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity import login
from boxing_club_api.identity.bootstrap import bootstrap_owner
from boxing_club_api.identity.models import AppUser, AuthSession
from boxing_club_api.identity.passwords import hash_password, verify_password

pytestmark = pytest.mark.integration
OWNER_EMAIL = "owner@example.test"
OWNER_PASSWORD = "a sample passphrase"


@pytest.fixture
def owner(sessions: SessionFactory) -> None:
    bootstrap_owner(
        sessions, email=OWNER_EMAIL, first_name="Sample", last_name="Owner", password=OWNER_PASSWORD
    )


def test_login_returns_token_and_stores_only_digest(
    owner: None,
    sessions: SessionFactory,
    database_url: URL,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "  OWNER@example.test ", "password": OWNER_PASSWORD},
        )
        next_response = client.post(
            "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        )

    assert response.status_code == next_response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    payload = response.json()
    assert set(payload) == {"access_token", "token_type", "expires_at"}
    assert payload["token_type"] == "bearer"
    token = payload["access_token"]
    assert token != next_response.json()["access_token"]
    assert len(urlsafe_b64decode(token + "=")) == 32
    digest = sha256(token.encode("ascii")).hexdigest()
    with sessions() as session:
        stored = session.scalars(
            select(AuthSession).where(AuthSession.token_digest == digest)
        ).one()
        assert stored.user_id == session.scalars(select(AppUser.id)).one()
        assert stored.revoked_at is None
        assert stored.expires_at - stored.created_at == timedelta(hours=8)
        assert datetime.fromisoformat(payload["expires_at"]) == stored.expires_at
        assert stored.expires_at > datetime.now(UTC)
    assert token not in caplog.text
    assert OWNER_PASSWORD not in caplog.text


def test_bad_unknown_and_blocked_credentials_get_same_failure(
    owner: None, sessions: SessionFactory, database_url: URL, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    with TestClient(create_app()) as client:
        wrong = client.post(
            "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": "wrong passphrase"}
        )
        unknown = client.post(
            "/api/v1/auth/login", json={"email": "missing@example.test", "password": OWNER_PASSWORD}
        )
        with sessions.begin() as session:
            session.execute(
                update(AppUser).where(AppUser.email == OWNER_EMAIL).values(status="BLOCKED")
            )
        blocked = client.post(
            "/api/v1/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}
        )

    for response in (wrong, unknown, blocked):
        assert response.status_code == 401
        body = response.json()
        assert body.pop("request_id")
        assert body == {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}
    with sessions() as session:
        assert session.scalars(select(AuthSession.id)).all() == []


def test_login_rechecks_credentials_after_password_verification(
    owner: None, sessions: SessionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement_hash = hash_password("a replacement passphrase")

    def verify_then_change(password: str, password_hash: str) -> bool:
        matches = verify_password(password, password_hash)
        with sessions.begin() as session:
            session.execute(
                update(AppUser)
                .where(AppUser.email == OWNER_EMAIL)
                .values(password_hash=replacement_hash)
            )
        return matches

    monkeypatch.setattr(login, "verify_password", verify_then_change)
    assert login.create_login_session(sessions, OWNER_EMAIL, OWNER_PASSWORD) is None
    with sessions() as session:
        assert session.scalars(select(AuthSession.id)).all() == []
