from fastapi import FastAPI
from fastapi.testclient import TestClient

from boxing_club_api.application.factory import create_app


def test_health_live() -> None:
    app: FastAPI = create_app()

    with TestClient(app) as client:
        response = client.get(url="/health/live")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
