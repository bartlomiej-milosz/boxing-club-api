-- Local development roles only; business tables are created by Alembic later.
-- psql reads credentials from the container environment without shell execution.
\getenv db_name POSTGRES_DB
\getenv owner_user POSTGRES_USER
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD

CREATE ROLE :"app_user" LOGIN PASSWORD :'app_password';
GRANT CONNECT ON DATABASE :"db_name" TO :"app_user";
GRANT USAGE ON SCHEMA public TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user" IN SCHEMA public
GRANT SELECT,
    INSERT,
    UPDATE,
    DELETE ON TABLES TO :"app_user";
ALTER DEFAULT PRIVILEGES FOR ROLE :"owner_user" IN SCHEMA public
GRANT USAGE,
    SELECT ON SEQUENCES TO :"app_user";
