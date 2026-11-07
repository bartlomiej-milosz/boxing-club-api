# SQL migrations

Alembic owns the PostgreSQL schema. Revision files execute explicit SQL through
`op.execute(...)`; ORM metadata is not used to generate or create tables.

## Current revision chain

```text
base -> 0001 -> 0002 -> 0003 -> 0004 (head)
```

| Revision | Schema change |
|---|---|
| `0001` | Room catalog with trimmed unique names and positive capacity |
| `0002` | Accounts, roles, member/trainer profiles and digest-only authentication sessions |
| `0003` | Dated classes, cancellation audit, schedule indexes and `btree_gist` exclusions preventing overlapping SCHEDULED room/trainer intervals |
| `0004` | Booking history, cancellation audit, lookup indexes and partial uniqueness for non-CANCELLED member/class reservations |

Room and trainer intervals use half-open ranges, so adjacent classes are allowed.
Cancelled classes do not occupy an excluded time range. Cancelled booking history
permits a later active reservation for the same member and class.

## Files and connection ownership

- `versions/` contains the ordered, applied schema changes.
- `env.py` requires an explicit `MIGRATION_DATABASE_URL` and opens the migration
  connection only for the command's lifetime.
- `script.py.mako` generates revision skeletons that raise until upgrade and
  downgrade behavior is implemented.
- The root `alembic.ini` selects this directory and configures migration logging.

Use the migration-owner connection for DDL and extension installation. The runtime
API uses `DATABASE_URL` with the separate application role. Installing `btree_gist`
requires suitable extension privileges for the migration role.

## Inspect and apply

Run commands from the repository root after `make setup`.

```sh
# Inspect files and the head without connecting to PostgreSQL.
make migration-history
uv run --locked alembic heads

# Apply pending revisions to the database explicitly selected in .env.
make migrate

# Inspect the revision recorded in that database.
uv run --locked --env-file .env alembic current
```

`make migrate` loads `.env` explicitly. Check that `MIGRATION_DATABASE_URL` selects
the intended database before running it. Merely creating `.env` does not make
Alembic read it automatically.

`make app-up` uses a separate one-shot Compose migration service before starting
the API. Application startup performs no DDL. Readiness currently expects schema
revision `0004`; update that expectation when a later schema release is implemented.

## Add a revision

Create a new revision after the current head, then implement its forward and
reverse SQL. Keep constraint and index names explicit. Add integration coverage
for direct SQL rejection, ORM/query behavior and the populated upgrade path where
those rules change.

Applied revisions are immutable. Correct an already-applied schema with a later
revision instead of editing its history. Downgrades in this project drop tables
and their data; exercise them only against disposable databases. The downgrade
of `0003` retains `btree_gist`, which may be shared by other schema objects.

## Verify on disposable PostgreSQL

```sh
make test-integration
```

The fixture migrates its own PostgreSQL template and creates a separate database
clone per test. Coverage includes role/profile atomicity, named checks and foreign
keys, overlapping and adjacent class ranges, active booking uniqueness, and
migration round trips preserving earlier identity/catalog data.

See the [test guide](../tests/README.md) for targeted commands and fixture lifecycle.
