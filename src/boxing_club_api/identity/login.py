"""Verify credentials and issue expiring opaque tokens stored only as digests."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import uuid4

from sqlalchemy import select, text

from boxing_club_api.db.session import SessionFactory

from .models import AppUser, AuthSession
from .passwords import verify_password

SESSION_LIFETIME = timedelta(hours=8)
# An Argon2id hash of discarded random input for unknown-account verification.
DUMMY_PASSWORD_HASH = "$argon2id$v=19$m=65536,t=3,p=4$YT3zwOAVF/xGrsYNQe/+Jg$9bQAGbPy+DHDxz8ZbUecsD/ilIZ2+mdKT+asbzbsCGA"


@dataclass(frozen=True)
class LoginSession:
    """Raw token and expiry returned once after a successful login transaction."""

    access_token: str
    expires_at: datetime


def create_login_session(
    sessions: SessionFactory, email: str, password: str
) -> LoginSession | None:
    """Issue an eight-hour token for valid ACTIVE credentials, otherwise return None.

    Verify the password outside a database session, then recheck credentials
    under the user lock to prevent issuance from stale password data.
    Persist only the token digest and return the raw token after commit.
    """
    with sessions() as session:
        credentials = session.execute(
            select(AppUser.id, AppUser.password_hash, AppUser.status).where(AppUser.email == email)
        ).one_or_none()

    password_hash = credentials.password_hash if credentials else DUMMY_PASSWORD_HASH
    password_matches = verify_password(password, password_hash)
    if credentials is None or not password_matches or credentials.status != "ACTIVE":
        return None

    with sessions.begin() as session:
        session.execute(text("SET LOCAL lock_timeout = '2s'"))
        current = session.execute(
            select(AppUser.password_hash, AppUser.status)
            .where(AppUser.id == credentials.id)
            .with_for_update()
        ).one_or_none()
        if current is None or current.password_hash != password_hash or current.status != "ACTIVE":
            return None

        issued_at = datetime.now(UTC)
        expires_at = issued_at + SESSION_LIFETIME
        token = token_urlsafe(32)
        session.add(
            AuthSession(
                id=uuid4(),
                user_id=credentials.id,
                token_digest=sha256(token.encode("ascii")).hexdigest(),
                created_at=issued_at,
                expires_at=expires_at,
            )
        )

    return LoginSession(access_token=token, expires_at=expires_at)
