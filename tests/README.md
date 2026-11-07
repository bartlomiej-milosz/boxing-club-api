# Tests

Run commands from the repository root after `make setup`.

## Test layers

| Location | Scope | PostgreSQL needed |
|---|---|---|
| `unit/` | Isolated functions such as password hashing and length boundaries | No |
| `api/` | HTTP validation, public errors, Swagger/OpenAPI, authentication configuration and health behavior without a working database | No |
| `integration/` | Real constraints, ORM persistence, service transactions, HTTP workflows and coordinated races | Yes |
| `support.py` | Shared fixture types, synthetic test constants and race coordination | Used by tests |
| `conftest.py` | Registers the explicit `--postgres` option | No container started here |
| `integration/conftest.py` | Owns disposable PostgreSQL, per-test databases and API/account fixtures | Yes |

Concurrency tests live in `integration/` and carry both `integration` and
`concurrency` markers. There is no separate concurrency directory.

The service layer already exists. Its central guarantees involve PostgreSQL locks,
transaction rollback, partial uniqueness and exclusion constraints, so most current
service behavior is exercised through integration tests. Independent input policies
and calculations are suitable for unit tests. Test counts reflect these different
scopes; tests in `api/` are HTTP tests even when they do not use PostgreSQL.

## Commands

```sh
make check
make test
make test-integration
```

`make check` runs Ruff, formatting and ty. `make test` runs the default suite with
PostgreSQL tests skipped. `make test-integration` opts into a disposable PostgreSQL
container and selects integration tests, including races.

```sh
# Select a layer.
uv run --locked pytest tests/unit
uv run --locked pytest tests/api

# Run one database test module or only coordinated races.
uv run --locked pytest --postgres tests/integration/booking_race_test.py
uv run --locked pytest --postgres -m concurrency

# Inspect collection without executing fixtures.
uv run --locked pytest --collect-only -q
```

Markers select tests; the `--postgres` flag authorizes database setup. Both are
required when selecting PostgreSQL-dependent cases by marker.

## Database lifecycle

The session-scoped `postgres` fixture starts one loopback-only PostgreSQL container
with a unique name, generated credentials and an ephemeral port. It initializes
roles, waits for the application role to connect, and applies Alembic migrations
once to a template database.

Each test receives a separately named clone through `database_url`. `sessions`
yields an application-role session factory. `client` starts FastAPI against that
clone. Teardown disposes connection pools, drops the clone, and finally removes
the container and its volumes. Tests set their own URLs rather than targeting the
normal development database configured in `.env`.

Constraints and race behavior are tested on PostgreSQL. Race helpers coordinate
independent sessions with barriers or events and bounded waits. Assertions inspect
both operation outcomes and the final persisted state.

## Adding tests

- Put request-independent behavior in `unit/`, database-free HTTP behavior in
  `api/`, and real database workflows or races in `integration/`.
- Add the `integration` marker to PostgreSQL tests, plus `concurrency` for races.
- Annotate fixture parameters and helper results. Reuse `AccountFactory` and other
  contracts from `tests.support`; use typed payloads or complete dictionary types.
- Obtain actor identity from authenticated fixtures. Exercise private-resource
  boundaries, failure rollback and state/time cutoffs where they affect behavior.
- Keep real credentials and tokens out of assertions, captured output and fixtures.
  Synthetic passphrases and generated disposable credentials are local test data.
