"""Check protected-route documentation and errors independently of database availability."""

import pytest
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


def test_openapi_declares_bearer_security_and_public_error_schemas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    document = create_app().openapi()
    assert document["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    for path, method, status in [
        ("/api/v1/me", "get", "401"),
        ("/api/v1/auth/logout", "post", "401"),
        ("/api/v1/users", "post", "409"),
        ("/api/v1/users", "get", "403"),
        ("/api/v1/trainers/{trainer_id}", "patch", "404"),
        ("/api/v1/rooms", "post", "409"),
    ]:
        operation = document["paths"][path][method]
        assert operation["security"] == [{"HTTPBearer": []}]
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/ErrorResponse"
        }
    assert "security" not in document["paths"]["/api/v1/auth/login"]["post"]


def test_protected_route_distinguishes_missing_auth_from_unconfigured_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        assert client.get("/api/v1/me").status_code == 401
        response = client.get(
            "/api/v1/me", headers={"Authorization": "Bearer synthetic-test-token"}
        )
        assert response.status_code == 503
        assert response.json()["code"] == "TEMPORARILY_UNAVAILABLE"
