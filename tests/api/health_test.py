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
