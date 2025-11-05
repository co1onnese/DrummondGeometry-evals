# PostgreSQL Setup Guide

Use the following commands to provision the application database, user, and permissions. Run them from `psql` using a superuser (e.g. `postgres`). Adjust host/port as needed for your environment.

```sql
-- Create database (skip if it already exists)
CREATE DATABASE dgas;

-- Create application user with password
CREATE USER fireworks_app WITH PASSWORD 'changeme_secure_password';

-- Grant privileges on the database
GRANT CONNECT, TEMP ON DATABASE dgas TO fireworks_app;

\c dgas

-- Grant privileges on the public schema and future tables
GRANT USAGE, CREATE ON SCHEMA public TO fireworks_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fireworks_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, UPDATE ON SEQUENCES TO fireworks_app;

-- Ensure ownership for existing tables/sequences (run after migrations if needed)
ALTER SCHEMA public OWNER TO fireworks_app;
```

After running these commands, confirm that your `.env` file contains:

```dotenv
DGAS_DATABASE_URL=postgresql+psycopg://fireworks_app:changeme_secure_password@localhost:5432/dgas
```

You can then execute the migration runner:

```bash
uv run python -m dgas.db.migrations
```
