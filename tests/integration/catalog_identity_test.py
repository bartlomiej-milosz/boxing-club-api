"""Verify paginated identity reads, trainer visibility and owner-only catalog updates."""

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration


def test_owner_account_pages_filter_roles_and_exclude_credentials(
    client: TestClient, owner_headers: dict[str, str], account_factory
) -> None:
    account_factory("a@example.test", ["MEMBER"])
    trainer, _ = account_factory("b@example.test", ["TRAINER", "MEMBER"])
    first = client.get("/api/v1/users", params={"size": 1}, headers=owner_headers)
    second = client.get("/api/v1/users", params={"size": 1, "page": 1}, headers=owner_headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == {**first.json(), "page": 0, "size": 1, "total_items": 3}
    assert first.json()["items"][0]["email"] == "a@example.test"
    assert second.json()["items"][0]["email"] == "b@example.test"
    filtered = client.get("/api/v1/users", params={"role": "TRAINER"}, headers=owner_headers).json()
    assert filtered["total_items"] == 1
    assert filtered["items"] == [trainer]
    for user in first.json()["items"] + second.json()["items"]:
        assert set(user) == {"id", "email", "first_name", "last_name", "roles"}
    empty = client.get("/api/v1/users", params={"page": 99}, headers=owner_headers).json()
    assert empty["items"] == [] and empty["total_items"] == 3


@pytest.mark.parametrize("roles", [["MEMBER"], ["TRAINER"], ["MEMBER", "TRAINER"]])
def test_non_owner_cannot_read_accounts_or_change_trainers(
    client: TestClient, owner_headers: dict[str, str], account_factory, roles: list[str]
) -> None:
    _, headers = account_factory("caller@example.test", roles)
    trainer, _ = account_factory("trainer@example.test", ["TRAINER"])
    assert client.get("/api/v1/users", headers=headers).status_code == 403
    assert (
        client.patch(
            f"/api/v1/trainers/{trainer['id']}", headers=headers, json={"active": False}
        ).status_code
        == 403
    )
    assert client.get("/api/v1/trainers?include_inactive=true", headers=headers).status_code == 403


def test_trainer_visibility_updates_and_public_field_boundary(
    client: TestClient, owner_headers: dict[str, str], account_factory
) -> None:
    trainer, _ = account_factory("trainer@example.test", ["TRAINER"])
    _, member_headers = account_factory("member@example.test", ["MEMBER"])
    assert client.get("/api/v1/trainers").status_code == 401
    result = client.get("/api/v1/trainers", headers=member_headers).json()
    assert result["total_items"] == 1
    assert set(result["items"][0]) == {"id", "first_name", "last_name", "bio", "active"}
    patch = client.patch(
        f"/api/v1/trainers/{trainer['id']}",
        headers=owner_headers,
        json={"bio": "Boxing coach", "active": False},
    )
    assert patch.status_code == 200
    assert patch.json()["bio"] == "Boxing coach" and patch.json()["active"] is False
    assert client.get("/api/v1/trainers", headers=member_headers).json()["total_items"] == 0
    assert client.get("/api/v1/trainers?include_inactive=true", headers=owner_headers).json()[
        "items"
    ] == [patch.json()]
    cleared = client.patch(
        f"/api/v1/trainers/{trainer['id']}", headers=owner_headers, json={"bio": None}
    )
    assert cleared.status_code == 200 and cleared.json()["bio"] is None
    assert (
        client.patch(
            f"/api/v1/trainers/{uuid4()}", headers=owner_headers, json={"active": False}
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "payload", [{}, {"active": None}, {"email": "another@example.test"}, {"roles": ["OWNER"]}]
)
def test_trainer_patch_rejects_empty_null_active_and_unsupported_fields(
    client: TestClient, owner_headers: dict[str, str], payload: dict
) -> None:
    assert (
        client.patch(f"/api/v1/trainers/{uuid4()}", headers=owner_headers, json=payload).status_code
        == 422
    )


@pytest.mark.parametrize("query", ["size=0", "size=101", "page=-1"])
def test_identity_pages_reject_invalid_bounds(
    client: TestClient, owner_headers: dict[str, str], query: str
) -> None:
    for path in ("users", "trainers"):
        assert client.get(f"/api/v1/{path}?{query}", headers=owner_headers).status_code == 422
