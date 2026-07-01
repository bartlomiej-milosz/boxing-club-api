"""Create the initial owner with an explicitly invoked local command."""

import argparse
import sys
import warnings
from datetime import UTC, datetime
from getpass import GetPassWarning, getpass
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from boxing_club_api.core.settings import Settings
from boxing_club_api.db.session import SessionFactory, create_database_engine

from .fields import normalize_email, normalize_name
from .models import AppUser, UserRole
from .passwords import hash_password


class OwnerBootstrapConflict(Exception):
    """The first owner cannot be created with the supplied account details."""


def bootstrap_owner(
    sessions: SessionFactory,
    *,
    email: str,
    first_name: str,
    last_name: str,
    password: str,
) -> None:
    email = normalize_email(email)
    first_name = normalize_name(first_name)
    last_name = normalize_name(last_name)
    password_hash = hash_password(password)

    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        # Serialize the one-time check even when bootstraps use different emails.
        session.execute(text("LOCK TABLE public.user_role IN SHARE ROW EXCLUSIVE MODE"))
        if session.scalar(select(UserRole.user_id).where(UserRole.role == "OWNER").limit(1)):
            raise OwnerBootstrapConflict("An owner already exists.")
        if session.scalar(select(AppUser.id).where(AppUser.email == email)):
            raise OwnerBootstrapConflict("An account with this email already exists.")

        user_id = uuid4()
        session.add(
            AppUser(
                id=user_id,
                email=email,
                first_name=first_name,
                last_name=last_name,
                password_hash=password_hash,
                status="ACTIVE",
                created_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(UserRole(user_id=user_id, role="OWNER"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    args = parser.parse_args()
    database_url = Settings().database_url
    if database_url is None:
        parser.error("Set DATABASE_URL to the application database.")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("Owner password: ")
            confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise ValueError("Passwords do not match.")

        engine = create_database_engine(database_url.get_secret_value())
        try:
            bootstrap_owner(
                sessionmaker(engine),
                email=args.email,
                first_name=args.first_name,
                last_name=args.last_name,
                password=password,
            )
        finally:
            engine.dispose()
    except (ValueError, OwnerBootstrapConflict) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except GetPassWarning, EOFError, KeyboardInterrupt:
        print("Owner bootstrap requires a password entered in a terminal.", file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Owner bootstrap failed. Check the database configuration and migration status.",
            file=sys.stderr,
        )
        return 1

    print("Owner created.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
