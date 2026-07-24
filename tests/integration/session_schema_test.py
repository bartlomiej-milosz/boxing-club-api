"""Exercise session exclusions, audit consistency and migration compatibility on PostgreSQL."""

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from psycopg import errors
from sqlalchemy import URL, text
from sqlalchemy.exc import IntegrityError

from boxing_club_api.db.session import SessionFactory
from boxing_club_api.identity.models import AppUser, TrainerProfile, UserRole
from boxing_club_api.scheduling.models import Room

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]
START = datetime(2030, 1, 1, 10, tzinfo=UTC)


@pytest.fixture
def catalog(sessions: SessionFactory) -> dict[str, UUID]:
    """Persist two trainers and rooms so exclusion tests can isolate each resource constraint."""
    ids = {key: uuid4() for key in ("trainer1", "trainer2", "room1", "room2")}
    with sessions.begin() as session:
        for key in ("trainer1", "trainer2"):
            session.add(
                AppUser(
                    id=ids[key],
                    email=f"{key}@example.test",
                    password_hash="unused-schema-test-hash",
                    first_name="Sample",
                    last_name="Trainer",
                    status="ACTIVE",
                    created_at=datetime.now(UTC),
                )
            )
        for key in ("room1", "room2"):
            session.add(Room(id=ids[key], name=key, capacity=12, active=True))
        session.flush()
        for key in ("trainer1", "trainer2"):
            session.add(UserRole(user_id=ids[key], role="TRAINER"))
            session.add(TrainerProfile(user_id=ids[key], active=True, bio=None))
    return ids


def insert_session(sessions: SessionFactory, catalog: dict[str, UUID], **changes) -> UUID:
    """Commit a SQL session row so schema checks are exercised independently of HTTP validation."""
    row = {
        "id": uuid4(),
        "title": "Boxing fundamentals",
        "trainer_id": catalog["trainer1"],
        "room_id": catalog["room1"],
        "starts_at": START,
        "ends_at": START + timedelta(hours=1),
        "booking_closes_at": START,
        "capacity": 12,
        "status": "SCHEDULED",
        "created_at": datetime.now(UTC),
        "cancelled_at": None,
        "cancelled_by_user_id": None,
        "cancellation_reason": None,
        **changes,
    }
    with sessions.begin() as session:
        session.execute(
            text("""INSERT INTO public.training_session
            (id,title,trainer_id,room_id,starts_at,ends_at,booking_closes_at,capacity,status,created_at,cancelled_at,cancelled_by_user_id,cancellation_reason)
            VALUES (:id,:title,:trainer_id,:room_id,:starts_at,:ends_at,:booking_closes_at,:capacity,:status,:created_at,:cancelled_at,:cancelled_by_user_id,:cancellation_reason)"""),
            row,
        )
    return row["id"]


def test_extension_and_named_exclusions_are_installed(sessions: SessionFactory) -> None:
    with sessions() as session:
        assert (
            session.scalar(text("SELECT extname FROM pg_extension WHERE extname='btree_gist'"))
            == "btree_gist"
        )
        constraints = dict(
            session.execute(
                text(
                    "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint WHERE conrelid='public.training_session'::regclass AND contype='x'"
                )
            ).all()
        )
        assert set(constraints) == {
            "ex_training_session_room_time",
            "ex_training_session_trainer_time",
        }
        assert all("'[)'::text" in value and "SCHEDULED" in value for value in constraints.values())


@pytest.mark.parametrize(
    "resource,constraint",
    [("room", "ex_training_session_room_time"), ("trainer", "ex_training_session_trainer_time")],
)
def test_overlapping_scheduled_resources_are_rejected(
    sessions: SessionFactory, catalog: dict[str, UUID], resource: str, constraint: str
) -> None:
    insert_session(sessions, catalog)
    changes = (
        {"trainer_id": catalog["trainer2"]} if resource == "room" else {"room_id": catalog["room2"]}
    )
    with pytest.raises(IntegrityError) as failure:
        insert_session(
            sessions,
            catalog,
            starts_at=START + timedelta(minutes=30),
            ends_at=START + timedelta(minutes=90),
            **changes,
        )
    assert isinstance(failure.value.orig, errors.ExclusionViolation)
    assert failure.value.orig.diag.constraint_name == constraint


def test_adjacent_ranges_and_distinct_resources_are_allowed(
    sessions: SessionFactory, catalog: dict[str, UUID]
) -> None:
    insert_session(sessions, catalog)
    insert_session(
        sessions,
        catalog,
        starts_at=START + timedelta(hours=1),
        ends_at=START + timedelta(hours=2),
        booking_closes_at=START + timedelta(hours=1),
    )
    insert_session(sessions, catalog, room_id=catalog["room2"], trainer_id=catalog["trainer2"])


def test_cancellation_releases_both_exclusions_without_deleting_history(
    sessions: SessionFactory, catalog: dict[str, UUID]
) -> None:
    original = insert_session(sessions, catalog)
    with sessions.begin() as session:
        session.execute(
            text(
                "UPDATE public.training_session SET status='CANCELLED',cancelled_at=:now,cancelled_by_user_id=:actor,cancellation_reason='Unavailable' WHERE id=:id"
            ),
            {"now": datetime.now(UTC), "actor": catalog["trainer1"], "id": original},
        )
    insert_session(sessions, catalog)
    with sessions() as session:
        assert session.scalar(text("SELECT count(*) FROM public.training_session")) == 2


@pytest.mark.parametrize(
    "changes,constraint",
    [
        ({"ends_at": START}, "ck_training_session_time_range"),
        ({"booking_closes_at": START + timedelta(seconds=1)}, "ck_training_session_booking_cutoff"),
        ({"capacity": 0}, "ck_training_session_capacity_positive"),
        ({"title": "  "}, "ck_training_session_title_trimmed"),
        ({"status": "CANCELLED"}, "ck_training_session_cancellation_audit"),
        ({"cancellation_reason": "Unexpected"}, "ck_training_session_cancellation_audit"),
    ],
)
def test_invalid_session_rows_fail_named_checks(
    sessions: SessionFactory, catalog: dict[str, UUID], changes: dict, constraint: str
) -> None:
    with pytest.raises(IntegrityError) as failure:
        insert_session(sessions, catalog, **changes)
    assert isinstance(failure.value.orig, errors.CheckViolation)
    assert failure.value.orig.diag.constraint_name == constraint


@pytest.mark.parametrize(
    "field,constraint",
    [("trainer_id", "fk_training_session_trainer"), ("room_id", "fk_training_session_room")],
)
def test_session_references_require_existing_catalog_records(
    sessions: SessionFactory, catalog: dict[str, UUID], field: str, constraint: str
) -> None:
    with pytest.raises(IntegrityError) as failure:
        insert_session(sessions, catalog, **{field: uuid4()})
    assert isinstance(failure.value.orig, errors.ForeignKeyViolation)
    assert failure.value.orig.diag.constraint_name == constraint


def test_migration_round_trip_preserves_populated_identity_and_room_tables(
    sessions: SessionFactory, catalog: dict[str, UUID], database_url: URL, postgres
) -> None:
    """Downgrade only this test clone, then reapply 0003 over populated 0002 tables."""
    env = {
        **os.environ,
        "MIGRATION_DATABASE_URL": postgres.owner_url(database_url.database).render_as_string(
            hide_password=False
        ),
    }
    for revision in ("0002", "head"):
        command = "downgrade" if revision == "0002" else "upgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", command, revision],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        with sessions() as session:
            assert session.scalar(text("SELECT count(*) FROM public.room")) == 2
            assert session.scalar(text("SELECT count(*) FROM public.app_user")) == 2
            assert session.scalar(text("SELECT version_num FROM public.alembic_version")) == (
                "0002" if revision == "0002" else "0003"
            )
    insert_session(sessions, catalog)


def test_invalid_session_status_is_rejected(
    sessions: SessionFactory, catalog: dict[str, UUID]
) -> None:
    # An unknown status violates both the status and cancellation-audit checks.
    with pytest.raises(IntegrityError) as failure:
        insert_session(sessions, catalog, status="UNKNOWN")
    assert isinstance(failure.value.orig, errors.CheckViolation)
