"""Check the served Swagger page and its generated HTTP bearer API description."""

import pytest
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


def test_swagger_ui_loads_the_openapi_schema_without_persisting_authorization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/docs")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "SwaggerUIBundle" in response.text
    assert "/openapi.json" in response.text
    assert '"persistAuthorization": false' in response.text


def test_openapi_endpoint_explains_bearer_login_and_groups_business_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    document = response.json()
    assert "Authorize" in document["info"]["description"]
    assert "POST /api/v1/auth/login" in document["info"]["description"]
    assert {tag["name"] for tag in document["tags"]} == {
        "auth",
        "identity",
        "rooms",
        "sessions",
        "bookings",
    }
    assert document["components"]["securitySchemes"]["HTTPBearer"] == {
        "type": "http",
        "scheme": "bearer",
    }
    assert document["paths"]["/api/v1/me"]["get"]["security"] == [{"HTTPBearer": []}]
