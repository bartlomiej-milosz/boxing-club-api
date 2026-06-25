from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.scheduling.models import Room

pytestmark = pytest.mark.integration


def test_room_round_trip_through_orm_and_sql(sessions: SessionFactory) -> None:
    room_id = uuid4()
    with sessions.begin() as session:
        session.add(Room(id=room_id, name="Training room", capacity=12))

    with sessions() as session:
        room = session.get_one(Room, room_id)
        assert (room.name, room.capacity, room.active) == ("Training room", 12, True)
        row = session.execute(
            text("SELECT name, capacity, active FROM public.room WHERE id = :id"), {"id": room_id}
        ).one()
        assert tuple(row) == (room.name, room.capacity, room.active)


@pytest.mark.parametrize(("name", "capacity"), [("Another room", 0), ("Existing room", 6)])
def test_room_constraint_rolls_back_entire_transaction(
    sessions: SessionFactory, name: str, capacity: int
) -> None:
    existing_id, first_id, invalid_id = uuid4(), uuid4(), uuid4()
    with sessions.begin() as session:
        session.add(Room(id=existing_id, name="Existing room", capacity=10))

    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(Room(id=first_id, name="Pending room", capacity=5))
        session.flush()
        session.add(Room(id=invalid_id, name=name, capacity=capacity))

    with sessions() as session:
        assert session.get(Room, existing_id) is not None
        assert session.get(Room, first_id) is None
        assert session.get(Room, invalid_id) is None
