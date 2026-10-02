"""Check consistent public failures and response correlation without a database."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


def test_error_envelopes_and_success_headers_share_request_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as client:
        responses = [
            client.get("/missing"),
            client.post("/health/live"),
            client.get("/api/v1/me"),
            client.post(
                "/api/v1/auth/login", json={"email": "invalid", "password": "very-secret-input"}
            ),
        ]
        assert [response.status_code for response in responses] == [404, 405, 401, 422]
        for response in responses:
            body = response.json()
            assert set(body) == {"code", "message", "request_id"}
            assert body["request_id"] == response.headers["X-Request-ID"]
            assert str(UUID(body["request_id"])) == body["request_id"]
            assert "very-secret-input" not in response.text
        live = client.get("/health/live")
        assert live.status_code == 200 and UUID(live.headers["X-Request-ID"])
        assert len({response.headers["X-Request-ID"] for response in responses}) == len(responses)
