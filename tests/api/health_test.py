"""Check liveness and prevent disclosure of runtime configuration."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


def test_health_live() -> None:
    app: FastAPI = create_app()

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_live_keeps_environment_configuration_private(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("APP_DB_PASSWORD", "example-secret")
    app: FastAPI = create_app()

    with TestClient(app) as client:
        response = client.get("/health/live")

    assert app.state.app_env == "staging"
    assert response.status_code == 200


def test_unreachable_database_fails_readiness_without_failing_liveness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        port = unavailable.getsockname()[1]
        monkeypatch.setenv(
            "DATABASE_URL", f"postgresql+psycopg://unused:unused@127.0.0.1:{port}/unavailable"
        )
        with TestClient(create_app()) as client:
            assert client.get("/health/ready").status_code == 503
            assert client.get("/health/live").status_code == 200
