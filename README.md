# Boxing Club API

A learning and portfolio project for managing training bookings at one boxing club.

**Current state: liveness, local PostgreSQL, room and identity schema, initial owner bootstrap and login.** The application serves `GET /health/live` and `POST /api/v1/auth/login`. Login issues an expiring opaque bearer token. Authenticated endpoints and booking workflows are planned.

The development notes describe the learning workflow and the project specifications.

## Local development

From the repository directory, with uv installed, run the checks and start the app.

```sh
make setup
make check
make test
make run
```

In another terminal, run `curl -i http://127.0.0.1:8000/health/live`. The expected response is `200` with `{"status":"ok"}`. Set `APP_ENV` in the app process environment to override `local`.

For the database steps, copy `.env.example` to `.env` if needed. Set distinct local passwords and update both connection URLs to match. Start Docker, then run `make db-up`, `make migrate` and `make db-shell`. `make migrate` applies SQL to the database selected by `MIGRATION_DATABASE_URL`.

### Bootstrap the initial owner and try login

After migrating the database, run:

```sh
uv run --locked --env-file .env python -m boxing_club_api.identity.bootstrap \
  --email owner@example.test --first-name Sample --last-name Owner
```

Enter a password of 12–128 characters at the hidden prompt. The bootstrap uses
`DATABASE_URL` and refuses to overwrite an existing account or create a second
initial owner. Start the API with `make run`, then submit the owner's email and
password as JSON to `POST /api/v1/auth/login`. The response contains
`access_token`, `token_type` and `expires_at`. Keep the password and token out of
shell history and logs. The development server provides interactive API docs at
`http://127.0.0.1:8000/docs`.

### PostgreSQL integration tests

Run `make test-integration` with Docker available. The suite starts its own
loopback-only PostgreSQL container, applies Alembic and gives each test a separate
database. It generates its own credentials and connection URLs. `make test`
runs the default suite with PostgreSQL tests skipped.

## Start here

1. [Documentation map](docs/README.md)
2. [Product and three release stages](docs/product.md)
3. [Roadmap and milestone index](docs/roadmap.md)
4. [Actual progress and next step](docs/progress.md)
5. [Working with an agent](docs/agent-workflow.md)

## Planned releases

| Release | Outcome | Milestones |
|---|---|---|
| 0.1 / Stage 1 | Locally reproducible booking MVP, real authentication, PostgreSQL, race protection, tests, Docker and CI; first portfolio checkpoint | M01–M32 |
| 0.2 / Stage 2 | Memberships, manual payment records, attendance and a first controlled VPS demo | M33–M56 |
| 1.0 / Stage 3 | Repeatable operations, companion Python CLI, deployment automation, monitoring and recovery evidence | M57–M73 |

Release numbers are targets. Stage 1 can be presented and used in applications once its evidence and explanation gates pass; later stages must not delay that checkpoint. This is not a guarantee of recruitment outcomes.

## Selected direction

Python, FastAPI, Pydantic, synchronous SQLAlchemy, psycopg, PostgreSQL, Alembic with hand-written SQL, uv, Ruff, ty and pytest. One modular monolith. Bash and curl support learning, smoke tests and operations. See [architecture](docs/architecture.md) for boundaries and [decisions](docs/decisions.md) for tradeoffs.

The project declares Python >=3.15. The selected environment was checked on Python 3.15.2; versions are locked in uv.lock. M01 still includes the author’s explanation checkpoint.

The supplied [draw.io file](docs/diagrams/boxing-club-api.drawio) is design input. It contains a broader model and Java-oriented learning pages; it is not evidence of Python implementation. Current textual contracts take precedence until the diagram is reconciled.

Code and public project descriptions are in English. Learning notes can be in Polish.

Follow the [Python documentation conventions](docs/code-documentation.md) when
adding or changing code.
