"""Initialize opt-in fictional demo data in an empty local database."""

import argparse
import json
import sys
import warnings
from dataclasses import asdict, dataclass
from datetime import timedelta
from getpass import GetPassWarning, getpass
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from boxing_club_api.core.clock import Clock, utc_now
from boxing_club_api.core.errors import ApplicationError
from boxing_club_api.core.settings import Settings
from boxing_club_api.db.session import SessionFactory, create_database_engine
from boxing_club_api.identity.models import AppUser, MemberProfile, TrainerProfile, UserRole
from boxing_club_api.identity.passwords import hash_password
from boxing_club_api.scheduling.models import Room, TrainingSession


@dataclass(frozen=True)
class DemoData:
    """Public fictional account names and catalog identifiers, excluding passwords and tokens."""

    owner_email: str
    trainer_email: str
    member_email: str
    room_id: UUID
    session_id: UUID


def seed_demo(sessions: SessionFactory, password: str, *, clock: Clock = utc_now) -> DemoData:
    """Insert fictional accounts and a future class atomically into an empty database.

    Hash the explicitly supplied password before opening a transaction. Refuse
    populated accounts or catalogs, preserving existing data on repeated invocation.
    """
    digest = hash_password(password)
    now = clock()
    ids = {name: uuid4() for name in ("owner", "trainer", "member", "other", "room", "class")}
    starts = (now + timedelta(days=2)).replace(minute=0, second=0, microsecond=0)
    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        session.execute(text("LOCK TABLE public.app_user IN SHARE ROW EXCLUSIVE MODE"))
        if (
            session.scalar(select(AppUser.id).limit(1)) is not None
            or session.scalar(select(Room.id).limit(1)) is not None
        ):
            raise ApplicationError(
                409,
                "DEMO_REQUIRES_EMPTY_DATABASE",
                "Demo initialization requires an empty database.",
            )
        for name in ("owner", "trainer", "member", "other"):
            session.add(
                AppUser(
                    id=ids[name],
                    email=f"{name}@example.test",
                    password_hash=digest,
                    first_name="Demo",
                    last_name=name.title(),
                    status="ACTIVE",
                    created_at=now,
                )
            )
        session.flush()
        for name, role in (
            ("owner", "OWNER"),
            ("trainer", "TRAINER"),
            ("member", "MEMBER"),
            ("other", "MEMBER"),
        ):
            session.add(UserRole(user_id=ids[name], role=role))
        for name in ("member", "other"):
            session.add(
                MemberProfile(
                    user_id=ids[name], joined_on=now.astimezone(ZoneInfo("Europe/Warsaw")).date()
                )
            )
        session.add(
            TrainerProfile(
                user_id=ids["trainer"], bio="Fictional demonstration coach.", active=True
            )
        )
        session.add(Room(id=ids["room"], name="Demo boxing room", capacity=2, active=True))
        session.flush()
        session.add(
            TrainingSession(
                id=ids["class"],
                title="Demo fundamentals",
                trainer_id=ids["trainer"],
                room_id=ids["room"],
                starts_at=starts,
                ends_at=starts + timedelta(hours=1),
                booking_closes_at=starts,
                capacity=2,
                status="SCHEDULED",
                created_at=now,
            )
        )
    return DemoData(
        "owner@example.test",
        "trainer@example.test",
        "member@example.test",
        ids["room"],
        ids["class"],
    )


def main() -> int:
    """Require local configuration and a hidden explicit password before initializing demo data."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-demo", action="store_true", required=True)
    parser.parse_args()
    settings = Settings()
    if settings.app_env != "local" or settings.database_url is None:
        parser.error("Use APP_ENV=local and an explicit DATABASE_URL for an empty demo database.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Demo account password: ")
            confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match.")
        engine = create_database_engine(settings.database_url.get_secret_value())
        try:
            result = seed_demo(sessionmaker(engine), password)
        finally:
            engine.dispose()
    except (ApplicationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except GetPassWarning, EOFError, KeyboardInterrupt:
        print("Enter the demo password in a terminal.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Demo initialization failed. Check database configuration and migrations.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(asdict(result), default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
