# Drummond Geometry Analysis System

This repository hosts a local-first implementation of the Drummond Geometry Analysis System. It follows the staged roadmap captured in `implementation_plan.md`, beginning with environment scaffolding and expanding toward data ingestion, analytics, and scheduled predictions.

## Quick Start

```bash
# create and activate a uv-managed virtual environment
uv venv
source .venv/bin/activate

# install dependencies
uv pip install -e .[dev]

# run the CLI skeleton
python -m dgas --version

# run the test suite
pytest
```

## Prerequisites

- Python 3.11 managed via [uv](https://github.com/astral-sh/uv)
- Local PostgreSQL instance (required from Phase 1 onward)
- Valid EODHD ALL-IN-ONE API token

## Environment Configuration

1. Duplicate `.env.example` to `.env` and keep it outside version control:

   ```bash
   cp .env.example .env
   ```

2. Populate the following variables:

   - `EODHD_API_TOKEN` - API key issued by EODHD
   - `DGAS_DATABASE_URL` - PostgreSQL connection string (defaults to `postgresql+psycopg://fireworks_app:changeme_secure_password@localhost:5432/dgas`)
   - `DGAS_DATA_DIR` - Local path used for cached market data and generated reports

3. Additional secrets can be appended as the project evolves. The `.env` file is ignored by Git.

4. Provision the database user and permissions using the SQL snippets in `docs/setup_postgres.md` before running migrations.

## Dependency Management with uv

- Install runtime and development dependencies:

  ```bash
  uv pip install -e .[dev]
  ```

- Add a new dependency:

  ```bash
  uv pip install <package>
  ```

- Run quality checks:

  ```bash
  ruff check src tests
  ruff format src tests
  mypy src
  pytest
  ```

## Repository Layout

- `implementation_plan.md` - phased delivery roadmap
- `prd/` - product requirement and design documents
- `src/dgas/` - Python package source code (currently scaffolded)
- `tests/` - automated tests
- `.env.example` - template for local configuration

Further setup and credential guidance will be refined as Phase 0 progresses.
