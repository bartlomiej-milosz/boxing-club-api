"""Check readiness against the migrated database and stale schema metadata."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from boxing_club_api.db.session import SessionFactory

pytestmark = pytest.mark.integration


def test_readiness_requires_current_schema_but_liveness_does_not(
    client: TestClient, sessions: SessionFactory
) -> None:
    assert client.get("/health/ready").status_code == 200
    with sessions.begin() as session:
        session.execute(text("UPDATE public.alembic_version SET version_num='stale'"))
    response = client.get("/health/ready")
    assert response.status_code == 503 and response.json() == {"status": "unavailable"}
    assert client.get("/health/live").status_code == 200
