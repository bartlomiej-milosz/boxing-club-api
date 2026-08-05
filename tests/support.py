"""Share typed fixture contracts and disposable PostgreSQL connection details."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import NotRequired, TypedDict

from sqlalchemy.engine import URL

OWNER = "boxing_owner"
APP = "boxing_app"


class AccountResponse(TypedDict):
    """Public JSON account fields returned by the account-creation fixture."""

    id: str
    email: str
    first_name: str
    last_name: str
    roles: list[str]


type AccountFactory = Callable[[str, list[str]], tuple[AccountResponse, dict[str, str]]]


@dataclass(frozen=True)
class TestPostgres:
    """Disposable container connection details with passwords excluded from repr output."""

    port: int
    owner_password: str = field(repr=False)
    app_password: str = field(repr=False)

    def owner_url(self, database: str) -> URL:
        """Build a migration-owner URL for the requested test database."""
        return self._url(database, OWNER, self.owner_password)

    def app_url(self, database: str) -> URL:
        """Build an application-role URL for the requested test database."""
        return self._url(database, APP, self.app_password)

    def _url(self, database: str, username: str, password: str) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=username,
            password=password,
            host="127.0.0.1",
            port=self.port,
            database=database,
        )


NOW = datetime(2030, 1, 1, 10, tzinfo=UTC)


class SessionPayload(TypedDict):
    """JSON class input shared by HTTP scheduling and booking tests."""

    title: str
    trainer_id: str
    room_id: str
    starts_at: str
    ends_at: str
    capacity: int
    booking_closes_at: NotRequired[str]
