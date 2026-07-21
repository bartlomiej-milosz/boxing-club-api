"""Check room catalog authorization, visibility, immutable capacities and name conflicts."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.scheduling.models import Room

pytestmark = pytest.mark.integration


def test_owner_creates_lists_and_updates_rooms(
    client: TestClient, owner_headers: dict[str, str], sessions: SessionFactory
) -> None:
    response = client.post(
        "/api/v1/rooms", headers=owner_headers, json={"name": "  Main room  ", "capacity": 12}
    )
    assert response.status_code == 201
    room = response.json()
    assert response.headers["Location"] == f"/api/v1/rooms/{room['id']}"
    assert room["name"] == "Main room" and room["active"] is True
    patched = client.patch(
        f"/api/v1/rooms/{room['id']}",
        headers=owner_headers,
        json={"name": "Renamed room", "active": False},
    )
    assert patched.status_code == 200 and patched.json()["capacity"] == 12
    assert client.get("/api/v1/rooms", headers=owner_headers).json()["items"] == []
    assert client.get("/api/v1/rooms?include_inactive=true", headers=owner_headers).json()[
        "items"
    ] == [patched.json()]
    with sessions() as session:
        stored = session.scalars(select(Room)).one()
        assert stored.name == "Renamed room" and stored.capacity == 12 and not stored.active


@pytest.mark.parametrize("roles", [["MEMBER"], ["TRAINER"]])
def test_room_mutations_and_inactive_visibility_require_owner(
    client: TestClient, owner_headers: dict[str, str], account_factory, roles: list[str]
) -> None:
    _, headers = account_factory("caller@example.test", roles)
    room = client.post(
        "/api/v1/rooms", headers=owner_headers, json={"name": "Main", "capacity": 12}
    ).json()
    assert client.get("/api/v1/rooms", headers=headers).json()["items"] == [room]
    assert (
        client.post(
            "/api/v1/rooms", headers=headers, json={"name": "Other", "capacity": 12}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/v1/rooms/{room['id']}", headers=headers, json={"active": False}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/rooms?include_inactive=true", headers=headers).status_code == 403
    assert client.get("/api/v1/rooms").status_code == 401
    client.patch(f"/api/v1/rooms/{room['id']}", headers=owner_headers, json={"active": False})
    assert client.get("/api/v1/rooms", headers=headers).json()["items"] == []


def test_room_conflicts_rollback_failed_rename_and_pages_are_stable(
    client: TestClient, owner_headers: dict[str, str]
) -> None:
    for name in ("Beta", "Alpha"):
        assert (
            client.post(
                "/api/v1/rooms", headers=owner_headers, json={"name": name, "capacity": 10}
            ).status_code
            == 201
        )
    duplicate = client.post(
        "/api/v1/rooms", headers=owner_headers, json={"name": " Alpha ", "capacity": 10}
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "ROOM_NAME_ALREADY_EXISTS"
    page = client.get("/api/v1/rooms?size=1", headers=owner_headers).json()
    assert page["page"] == 0 and page["size"] == 1 and page["total_items"] == 2
    assert page["items"][0]["name"] == "Alpha"
    second = client.get("/api/v1/rooms?size=1&page=1", headers=owner_headers).json()["items"][0]
    failed = client.patch(
        f"/api/v1/rooms/{second['id']}",
        headers=owner_headers,
        json={"name": "Alpha", "active": False},
    )
    assert failed.status_code == 409
    assert client.get("/api/v1/rooms?size=1&page=1", headers=owner_headers).json()["items"] == [
        second
    ]
    assert (
        client.patch(
            f"/api/v1/rooms/{uuid4()}", headers=owner_headers, json={"active": False}
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"name": "", "capacity": 1},
        {"name": "  ", "capacity": 1},
        {"name": "A", "capacity": 0},
        {"name": "A", "capacity": -1},
        {"name": "A", "capacity": True},
        {"name": "A", "capacity": 2**31},
        {"name": "A", "capacity": 1, "extra": 1},
    ],
)
def test_invalid_room_creation_is_rejected(
    client: TestClient, owner_headers: dict[str, str], payload: dict
) -> None:
    assert client.post("/api/v1/rooms", headers=owner_headers, json=payload).status_code == 422


@pytest.mark.parametrize(
    "payload", [{}, {"capacity": 20}, {"name": None}, {"active": None}, {"name": "   "}]
)
def test_room_patch_rejects_capacity_changes_nulls_and_empty_input(
    client: TestClient, owner_headers: dict[str, str], payload: dict
) -> None:
    assert (
        client.patch(f"/api/v1/rooms/{uuid4()}", headers=owner_headers, json=payload).status_code
        == 422
    )


@pytest.mark.parametrize("query", ["page=-1", "size=0", "size=101"])
def test_room_pages_are_bounded(
    client: TestClient, owner_headers: dict[str, str], query: str
) -> None:
    assert client.get(f"/api/v1/rooms?{query}", headers=owner_headers).status_code == 422
