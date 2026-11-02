# SQL migrations

Alembic plumbing is ready; there are no business revisions or tables yet.

Create your first revision in M05 using `uv run alembic revision -m "create room"`.
Write explicit SQL in its upgrade function using Alembic operations. The template
intentionally raises until the author replaces it; an empty revision must not
silently look applied. A generated revision is a working draft, not a migration
ready to execute. Do not use `--autogenerate` before ORM metadata is deliberately
configured, or use application startup/create_all to manage the schema.

`make migration-history` needs no database connection. `make migrate` reads the
explicit migration-owner URL from the ignored `.env` file and changes that database.
Do not point this command at shared/production data without checking the target.

Applied migrations are immutable. Downgrades are exercised on disposable databases,
with their data-loss implications documented. The runtime application uses a
different, restricted database role.
