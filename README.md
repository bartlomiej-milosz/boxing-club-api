# Boxing Club API

A learning and portfolio project for managing training bookings at one boxing club.

**Current state: development environment prepared; API not implemented.** Python dependencies, quality tools, package layout, Alembic plumbing and local PostgreSQL are scaffolded. The specifications describe planned business behavior. No commercial deployment or customer use is claimed.

The author implements the application personally. Agents act as mentors and reviewers by default. Read [AGENTS.md](AGENTS.md) before assisting.

## Local development

See [development setup](docs/development-setup.md) for the prepared layout and database credentials policy. From the repository directory:

```sh
make setup
make check
make db-up
```

The current checkout already has an ignored local `.env`. For a fresh clone, configure it from `.env.example` first. `make test` will report no tests until you write the first meaningful test. No application start command exists before M02.

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

Environment instructions are available now; application examples, badges and deployment links will be added only when verified. Code, technical documentation and public project descriptions are in English; mentoring conversations may be in Polish.
