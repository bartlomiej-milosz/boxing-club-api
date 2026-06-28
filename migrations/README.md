# SQL migrations

Revision `0001` creates the `public.room` table. Revision `0002` adds users,
roles, profiles and authentication sessions. Run `make migration-history` to
see revision history without a database connection.

`make migrate` loads `.env` and applies pending revisions to the PostgreSQL
database selected by `MIGRATION_DATABASE_URL`. Use the migration-owner
credentials. The runtime application uses a separate role with fewer privileges.

New revisions contain explicit SQL executed through Alembic operations.
The revision template raises until the upgrade and reversal are implemented.
Application startup does not manage the schema. Applied revisions are immutable.
Exercise destructive downgrades only in disposable databases.
