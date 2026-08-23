"""Check the final SQL duplicate guard and retained cancelled reservation history."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg import errors
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from tests.support import AccountFactory, SessionPayload

from boxing_club_api.bookings.models import Booking
from boxing_club_api.db.session import SessionFactory

pytestmark = pytest.mark.integration


def test_active_duplicate_fails_but_cancelled_history_allows_rebooking(
    client: TestClient,
    owner_headers: dict[str, str],
    class_payload: SessionPayload,
    account_factory: AccountFactory,
    sessions: SessionFactory,
) -> None:
    member, _ = account_factory("member@example.test", ["MEMBER"])
    created = client.post("/api/v1/sessions", headers=owner_headers, json=class_payload).json()
    user_id = UUID(member["id"])
    session_id = UUID(created["id"])
    booking_id = uuid4()
    with sessions.begin() as session:
        session.add(
            Booking(
                id=booking_id,
                member_id=user_id,
                session_id=session_id,
                status="RESERVED",
                created_at=datetime.now(UTC),
            )
        )
    with pytest.raises(IntegrityError) as failure, sessions.begin() as session:
        session.add(
            Booking(
                id=uuid4(),
                member_id=user_id,
                session_id=session_id,
                status="RESERVED",
                created_at=datetime.now(UTC),
            )
        )
    assert isinstance(failure.value.orig, errors.UniqueViolation)
    assert failure.value.orig.diag.constraint_name == "uq_booking_active_member_session"
    with sessions.begin() as session:
        original = session.get_one(Booking, booking_id)
        original.status = "CANCELLED"
        original.cancelled_at = datetime.now(UTC)
        original.cancelled_by_user_id = user_id
        session.flush()
        session.add(
            Booking(
                id=uuid4(),
                member_id=user_id,
                session_id=session_id,
                status="RESERVED",
                created_at=datetime.now(UTC),
            )
        )
    with sessions() as session:
        assert sorted(session.scalars(select(Booking.status)).all()) == ["CANCELLED", "RESERVED"]
