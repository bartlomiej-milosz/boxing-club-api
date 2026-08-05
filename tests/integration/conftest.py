"""Configure opt-in test resources for this directory and its descendants."""

import os
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from tests.support import (
    APP,
    NOW,
    OWNER,
    AccountFactory,
    AccountResponse,
    SessionPayload,
    TestPostgres,
)

from boxing_club_api.application.factory import create_app
from boxing_club_api.db.session import SessionFactory, create_database_engine
from boxing_club_api.identity.bootstrap import bootstrap_owner

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DATABASE = "boxing_test_template"


def _wait_for_postgres(postgres: TestPostgres) -> None:
    """Wait up to 30 seconds for the application role to connect to the template database."""
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
    """Yield one migrated PostgreSQL container for the test run when explicitly enabled.

    Use generated credentials and a loopback-only ephemeral port.
    Remove the container and its volumes when setup fails or the session ends.
    """
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
    """Clone the migrated template for one test and drop the clone during teardown."""
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
    """Yield the test database session factory and dispose its connection pool afterward."""
    engine = create_database_engine(database_url)
    try:
        yield sessionmaker(engine)
    finally:
        engine.dispose()


@pytest.fixture
def client(database_url: URL, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """Serve the API against the current disposable database and close its engine afterward."""
    monkeypatch.setenv("DATABASE_URL", database_url.render_as_string(hide_password=False))
    with TestClient(create_app()) as api:
        yield api


@pytest.fixture
def owner_headers(sessions: SessionFactory, client: TestClient) -> dict[str, str]:
    """Create an owner and authenticate through HTTP for the current test database."""
    bootstrap_owner(
        sessions,
        email="owner@example.test",
        first_name="Sample",
        last_name="Owner",
        password="a sample passphrase",
    )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.test", "password": "a sample passphrase"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def account_factory(client: TestClient, owner_headers: dict[str, str]) -> AccountFactory:
    """Create and log in a non-owner through HTTP, returning its public data and auth header."""

    def create(email: str, roles: list[str]) -> tuple[AccountResponse, dict[str, str]]:
        response = client.post(
            "/api/v1/users",
            headers=owner_headers,
            json={
                "email": email,
                "first_name": "Sample",
                "last_name": email.partition("@")[0],
                "initial_password": "a sample passphrase",
                "roles": roles,
            },
        )
        assert response.status_code == 201, response.json()
        login = client.post(
            "/api/v1/auth/login", json={"email": email, "password": "a sample passphrase"}
        )
        assert login.status_code == 200
        account: AccountResponse = response.json()
        return account, {"Authorization": f"Bearer {login.json()['access_token']}"}

    return create


@pytest.fixture
def class_payload(
    client: TestClient, owner_headers: dict[str, str], account_factory: AccountFactory
) -> SessionPayload:
    """Create active catalog records and freeze the business clock independently of auth expiry."""
    assert isinstance(client.app, FastAPI)
    client.app.state.clock = lambda: NOW
    trainer, _ = account_factory("coach@example.test", ["TRAINER"])
    room = client.post(
        "/api/v1/rooms", headers=owner_headers, json={"name": "Main room", "capacity": 12}
    )
    assert room.status_code == 201
    return {
        "title": "Boxing fundamentals",
        "trainer_id": trainer["id"],
        "room_id": room.json()["id"],
        "starts_at": (NOW + timedelta(days=1)).isoformat(),
        "ends_at": (NOW + timedelta(days=1, hours=1)).isoformat(),
        "capacity": 12,
    }
