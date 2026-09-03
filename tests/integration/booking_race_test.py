"""Prove last-seat and duplicate safety across competing database transactions."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.support import NOW, AccountFactory, SessionPayload, run_race

from boxing_club_api.bookings.models import Booking
from boxing_club_api.bookings.service import reserve
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.authentication import Principal, resolve_principal

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


@pytest.mark.parametrize("duplicate", [False, True])
def test_competing_reservations_leave_one_active_row(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
    sessions: SessionFactory,
    duplicate: bool,
) -> None:
    _, first = account_factory("one@example.test", ["MEMBER"])
    _, second = account_factory("two@example.test", ["MEMBER"])
    principals = [
        resolve_principal(sessions, headers["Authorization"].split()[1])
        for headers in (first, first if duplicate else second)
    ]
    assert all(principal is not None for principal in principals)
    training = client.post(
        "/api/v1/sessions",
        headers=owner_headers,
        json={**class_payload, "capacity": 12 if duplicate else 1},
    ).json()

    def attempt(principal: Principal | None) -> int:
        assert principal is not None
        try:
            reserve(sessions, principal, UUID(training["id"]), clock=lambda: NOW)
        except ApplicationError as error:
            assert error.code == ("BOOKING_ALREADY_EXISTS" if duplicate else "SESSION_FULL")
            return error.status_code
        return 201

    outcomes = run_race([lambda: attempt(principals[0]), lambda: attempt(principals[1])])
    assert sorted(outcomes) == [201, 409]
    with sessions() as session:
        assert (
            session.scalar(
                select(func.count()).select_from(Booking).where(Booking.status == "RESERVED")
            )
            == 1
        )
