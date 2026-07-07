"""Exercise login validation, token issuance and credential failure behavior."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "owner@example.test", "password": "short-pass"},
        {"email": "owner@example.test", "password": "x" * 129},
        {"email": "owner@example.test", "password": "valid passphrase", "extra": "secret extra"},
        {"email": "invalid email", "password": "valid passphrase"},
    ],
)
def test_invalid_login_does_not_echo_request_data(
    payload: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 422
    body = response.json()
    assert body["request_id"] == str(UUID(body["request_id"]))
    assert set(body) == {"code", "message", "request_id"}
    assert body["code"] == "VALIDATION_ERROR"
    for value in payload.values():
        assert value not in response.text


def test_login_without_database_is_unavailable_but_app_is_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "owner@example.test", "password": "sample passphrase"},
        )
        assert response.status_code == 503
        assert response.json()["code"] == "TEMPORARILY_UNAVAILABLE"
        assert client.get("/health/live").json() == {"status": "ok"}
