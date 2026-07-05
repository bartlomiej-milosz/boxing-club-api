.PHONY: help setup check lint format typecheck test test-integration run db-up db-down db-logs db-shell migration-history migrate bootstrap-owner

help:
	@printf '%s\n' \
	  'make setup              Install locked runtime and development dependencies' \
	  'make check              Check lint, formatting and types (not tests)' \
	  'make format             Format Python files' \
	  'make test               Run the default suite without PostgreSQL' \
	  'make test-integration   Run tests on disposable PostgreSQL' \
	  'make run                Run the application with Uvicorn' \
	  'make bootstrap-owner    Create the initial owner (EMAIL, FIRST_NAME, LAST_NAME)' \
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
	uv run --locked $(if $(wildcard .env),--env-file .env) \
	  env -u MIGRATION_DATABASE_URL -u POSTGRES_PASSWORD -u APP_DB_PASSWORD \
	  uvicorn boxing_club_api.application.factory:create_app --factory --reload

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

bootstrap-owner: export EMAIL := $(EMAIL)
bootstrap-owner: export FIRST_NAME := $(FIRST_NAME)
bootstrap-owner: export LAST_NAME := $(LAST_NAME)
bootstrap-owner:
	@if [ -z "$$EMAIL" ] || [ -z "$$FIRST_NAME" ] || [ -z "$$LAST_NAME" ]; then \
	  printf '%s\n' 'Usage: make bootstrap-owner EMAIL=owner@example.test FIRST_NAME=Jan LAST_NAME=Kowalski' >&2; \
	  exit 2; \
	fi
	uv run --locked --env-file .env python -m boxing_club_api.identity.bootstrap \
	  --email "$$EMAIL" --first-name "$$FIRST_NAME" --last-name "$$LAST_NAME"
