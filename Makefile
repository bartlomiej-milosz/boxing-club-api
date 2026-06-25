.PHONY: help setup check lint format typecheck test test-integration run db-up db-down db-logs db-shell migration-history migrate

help:
	@printf '%s\n' \
	  'make setup              Install locked runtime and development dependencies' \
	  'make check              Check lint, formatting and types (not tests)' \
	  'make format             Format Python files' \
	  'make test               Run the default suite without PostgreSQL' \
	  'make test-integration   Run tests on disposable PostgreSQL' \
	  'make run                Run the application with Uvicorn' \
	  'make db-up              Start local PostgreSQL and wait for readiness' \
	  'make db-down            Stop PostgreSQL; preserve its named volume' \
	  'make db-logs            Follow PostgreSQL logs' \
	  'make db-shell           Open psql as the local migration owner' \
	  'make migration-history  Show Alembic revisions without connecting to DB' \
	  'make migrate            Apply migrations to MIGRATION_DATABASE_URL from .env'

setup:
	uv sync --locked

check: lint typecheck
	uv run --locked ruff format --check .

lint:
	uv run --locked ruff check .

format:
	uv run --locked ruff format .

typecheck:
	uv run --locked ty check

test:
	uv run --locked pytest

test-integration:
	uv run --locked pytest --postgres -m integration

run:
	uv run --locked uvicorn boxing_club_api.application.factory:create_app --factory --reload

db-up:
	docker compose up -d --wait postgres

db-down:
	docker compose down

db-logs:
	docker compose logs -f postgres

db-shell:
	docker compose exec postgres psql -U boxing_owner -d boxing_club

migration-history:
	uv run --locked alembic history

migrate:
	uv run --locked --env-file .env alembic upgrade head

