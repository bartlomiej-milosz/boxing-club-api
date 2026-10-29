# Boxing Club API

A single-club training booking API built as a Python learning and portfolio project.
Stage 1 implements accounts, opaque bearer authentication, rooms, dated classes,
reservations, cancellation and trainer rosters. It is a synchronous modular monolith
using FastAPI, SQLAlchemy, psycopg and PostgreSQL.

Paid memberships, payments, attendance and hosted deployment remain planned for
later stages. There is no frontend. This project does not represent commercial use.

## Run locally

Requirements: Docker with Compose, uv, and Python 3.15. Curl, jq and Bash are used
by the walkthrough. Runtime and development versions are pinned in `uv.lock`.

```sh
cp .env.example .env
# Replace both placeholder passwords with distinct URL-safe values.
# Update DATABASE_URL and MIGRATION_DATABASE_URL to match.
make setup
make app-up
```

`app-up` builds a non-root image, waits for PostgreSQL, runs the explicit one-shot
migration service, then starts the API. The API never migrates its schema at startup.
Ports are bound to loopback. Override `APP_PORT` or `POSTGRES_PORT` in `.env` if needed.
Local Compose interpolates URL-safe passwords into its internal connection URLs.
For example, generate a new value with `uv run python -c 'import secrets; print(secrets.token_urlsafe(24))'`.

- [Interactive API documentation](http://127.0.0.1:8000/docs)
- [Liveness](http://127.0.0.1:8000/health/live)
- [Database/schema readiness](http://127.0.0.1:8000/health/ready)

`make app-down` stops services and preserves the database volume. For development
without the application container, use `make db-up`, `make migrate` and `make run`.

## Initialize fictional demo data

Use a fresh, empty local database. The initializer refuses existing accounts or
rooms and commits the entire fictional dataset atomically.

```sh
make seed-demo
bash scripts/walkthrough.sh
```

Choose a password of 12–128 characters at the hidden initializer prompt. The
fictional accounts `owner@example.test`, `trainer@example.test`, `member@example.test`
and `other@example.test` share this explicitly chosen demo password. Enter it again
when the walkthrough asks. There is no default password in the application.

The walkthrough logs in, creates and lists catalog/class records, reserves a place,
checks the duplicate conflict, cancels and rebooks, cancels the class, and verifies
logout. Temporary credential and token files have private permissions and are
removed on exit. Tokens are supplied to curl through header files. Repeating the
walkthrough retains demonstration history and releases its class slot on exit.
Set `APP_BASE_URL` when using a different local port.

For an empty database that should receive only an initial owner, use this command
instead of the demo initializer:

```sh
make bootstrap-owner EMAIL=owner@example.test FIRST_NAME=Sample LAST_NAME=Owner
```

## HTTP API

Business routes have the `/api/v1` prefix. Protected routes require an ACTIVE
account and `Authorization: Bearer <token>`. Login returns the raw token once;
PostgreSQL stores its digest and an eight-hour expiry. Logout revokes that token.

| Methods and paths | Behavior |
|---|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /me` | Authentication and current identity |
| `POST /users`, `GET /users` | Owner-created MEMBER/TRAINER accounts and account listing |
| `GET /trainers`, `PATCH /trainers/{id}` | Trainer catalog and owner-managed bio/activity |
| `POST /rooms`, `GET /rooms`, `PATCH /rooms/{id}` | Room catalog with immutable capacity |
| `POST /sessions`, `GET /sessions`, `GET /sessions/{id}` | Create and inspect dated classes |
| `POST /sessions/{id}/cancellation` | Owner cancellation with original audit retained on replay |
| `GET /sessions/{id}/bookings` | Roster for the owner or assigned trainer |
| `POST /bookings`, `GET /me/bookings`, `GET /bookings/{id}` | Member reservations and role-safe history |
| `POST /bookings/{id}/cancellation` | Owning member cancellation before class start |

Lists return `items`, zero-based `page`, `size` and `total_items`. Default size is
20, maximum 100. Schedule queries use inclusive `from` and exclusive `to`, default
to the next 14 days, and allow at most 90 days. Timestamps require UTC offsets.
Inactive catalog entries require an owner's explicit `include_inactive=true`.

Named PostgreSQL exclusion constraints reject overlapping SCHEDULED room or trainer
intervals while permitting adjacent classes. A class row lock protects reservation
counts and every operation that releases a seat. A partial unique index guards
against duplicate active member/class reservations. Cancelled history is retained.

Errors contain `code`, `message` and `request_id`, matching `X-Request-ID`.
Validation is 422, authentication 401, role rejection 403, inaccessible private
resources 404, business conflicts 409, and temporary database/lock failures 503.
Readiness checks schema revision `0004`; liveness has no database dependency.

## Verify

```sh
make check
make test
make test-integration
bash -n scripts/walkthrough.sh
shellcheck scripts/walkthrough.sh
```

Integration and race tests start a disposable PostgreSQL container with generated
credentials, migrate it and clone a separate database per test. They never target
the development database. SQLite is not used as a substitute for PostgreSQL locks
or exclusion constraints. CI runs these commands and builds the application image.
An actual remote CI result must be checked separately from local results.

See the [Stage 1 implementation and verification notes](docs/phase-1.md) and the
[Python documentation conventions](docs/code-documentation.md). The historical Java
and broader design diagrams in local planning notes are not the current schema.
