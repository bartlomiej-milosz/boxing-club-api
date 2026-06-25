import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from boxing_club_api.db.session import SessionFactory, create_database_engine

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DATABASE = "boxing_test_template"
OWNER = "boxing_owner"
APP = "boxing_app"


@dataclass(frozen=True)
class TestPostgres:
    port: int
    owner_password: str = field(repr=False)
    app_password: str = field(repr=False)

    def owner_url(self, database: str) -> URL:
        return self._url(database, OWNER, self.owner_password)

    def app_url(self, database: str) -> URL:
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


def _wait_for_postgres(postgres: TestPostgres) -> None:
    deadline = time.monotonic() + 30
    while True:
        try:
            with psycopg.connect(
                host="127.0.0.1",
                port=postgres.port,
                user=APP,
                password=postgres.app_password,
                dbname=TEMPLATE_DATABASE,
                connect_timeout=1,
            ) as connection:
                assert connection.execute("SELECT current_database(), current_user").fetchone() == (
                    TEMPLATE_DATABASE,
                    APP,
                )
            return
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                pytest.fail("The disposable PostgreSQL container did not become ready.")
            time.sleep(0.2)


@pytest.fixture(scope="session")
def postgres(request: pytest.FixtureRequest) -> Iterator[TestPostgres]:
    if not request.config.getoption("--postgres"):
        pytest.skip("Run make test-integration to start disposable PostgreSQL.")

    if shutil.which("docker") is None:
        pytest.fail("Docker is required for PostgreSQL integration tests.")

    name = f"boxing-test-{uuid4().hex}"
    owner_password = secrets.token_urlsafe(24)
    app_password = secrets.token_urlsafe(24)
    try:
        subprocess.run(
            [
                "docker",
                "run",
                "--detach",
                "--name",
                name,
                "--publish",
                "127.0.0.1::5432",
                "--env",
                f"POSTGRES_DB={TEMPLATE_DATABASE}",
                "--env",
                f"POSTGRES_USER={OWNER}",
                "--env",
                "POSTGRES_PASSWORD",
                "--env",
                f"APP_DB_USER={APP}",
                "--env",
                "APP_DB_PASSWORD",
                "--mount",
                f"type=bind,source={ROOT / 'infra/postgres/init-app-role.sql'},"
                "target=/docker-entrypoint-initdb.d/10-app-role.sql,readonly",
                "postgres:18-alpine",
            ],
            env={
                **os.environ,
                "POSTGRES_PASSWORD": owner_password,
                "APP_DB_PASSWORD": app_password,
            },
            capture_output=True,
            check=True,
            timeout=120,
        )
        published = subprocess.check_output(
            ["docker", "port", name, "5432/tcp"], text=True, timeout=10
        )
        host, port = published.strip().rsplit(":", 1)
        assert host == "127.0.0.1"
        database = TestPostgres(int(port), owner_password, app_password)
        _wait_for_postgres(database)
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=ROOT,
            env={
                **os.environ,
                "MIGRATION_DATABASE_URL": database.owner_url(TEMPLATE_DATABASE).render_as_string(
                    hide_password=False
                ),
            },
            check=True,
            timeout=30,
        )
        yield database
    finally:
        subprocess.run(
            ["docker", "rm", "--force", "--volumes", name],
            capture_output=True,
            timeout=30,
            check=False,
        )


@pytest.fixture
def database_url(postgres: TestPostgres) -> Iterator[URL]:
    database = f"boxing_test_{uuid4().hex}"
    with psycopg.connect(
        host="127.0.0.1",
        port=postgres.port,
        user=OWNER,
        password=postgres.owner_password,
        dbname="postgres",
        autocommit=True,
    ) as connection:
        connection.execute(
            sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                sql.Identifier(database), sql.Identifier(TEMPLATE_DATABASE)
            )
        )
        try:
            yield postgres.app_url(database)
        finally:
            connection.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database))
            )


@pytest.fixture
def sessions(database_url: URL) -> Iterator[SessionFactory]:
    engine = create_database_engine(database_url)
    try:
        yield sessionmaker(engine)
    finally:
        engine.dispose()
