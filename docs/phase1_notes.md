# Phase 1 Notes ? Data Ingestion & Storage

## Goals

- Implement resilient access to EODHD 30-minute OHLCV data for US equities.
- Persist normalized market data and Drummond calculation scaffolding in PostgreSQL.
- Provide utilities for historical backfill and incremental refresh with data-quality validation.
- Produce lightweight monitoring outputs (CLI/Markdown/CSV) to summarise ingestion health.

## Source Requirements

- **API**: EODHD ALL-IN-ONE package (per `prd/04_eodhd_api_integration.md`).
  - Endpoints: `/intraday/{symbol}` for 30-minute bars (`interval=30m`), `/eod/{symbol}` fallback.
  - Auth via token query parameter (`api_token`).
  - Rate limits: target ?80 requests/min with burst ?10 req/s; daily 50k.
  - Retry policy: exponential backoff, respect `Retry-After` headers.
  - Data fields: code (symbol), date/timestamp, OHLC, adjusted close, volume.

- **Scheduling**: For local system, cron/uv runner triggered every 30 minutes post market close for incremental updates. Historical backfill chunks sized ?50 symbols per batch, ?365 days per request (per design doc).

## Storage Requirements

From `prd/02_database_schema.md` (focusing on immediate needs):

### Core Tables (initial scope)

1. `market_symbols`
   - Tracks metadata for each symbol (symbol, name, exchange, sector, active flag).
   - Useful for deduplicating symbol IDs and joining to other tables.

2. `market_data`
   - Stores OHLCV bars (initially 30-minute interval).
   - Enforce unique `(symbol_id, timestamp, interval_type)`.
   - Constraints to guarantee price logic and positive volume.
   - Additional fields `vwap`, `true_range` reserved for later phases.

3. `market_data_metadata`
   - Optional per-bar metadata (source, gap fill method). Can be deferred but maintain structure for compatibility.

4. `pldot_calculations`, `envelope_bands`, `drummond_lines`, `market_state`
   - Not populated in Phase 1, but create tables to support future phases (ensures migrations stable early).

5. `trading_signals`, `backtest_results`, `backtest_trades`
   - Optional for later phases; consider creating in initial migration if minimal cost to avoid future destructive changes.

### Indexing Strategy

- Time-based composite indexes for `market_data` (`symbol_id`, `timestamp DESC`).
- Partial indexes for recent data (rolling 2 years) for performance.
- Additional indexes for analytics tables as per design doc.

### Partitioning

- Phase 1: keep schema simple (single table). Evaluate TimescaleDB/partitioning in Phase 6 after data volumes quantified.

## Configuration Strategy

- Introduce `src/dgas/settings.py` using `pydantic` BaseSettings to load `.env` values.
- Keys: `EODHD_API_TOKEN`, `DGAS_DATABASE_URL`, `DGAS_DATA_DIR`, `EODHD_RATE_LIMIT_PER_MINUTE` (optional override).

## Client Architecture

- Module structure under `src/dgas/data/`:
  - `client.py` ? session management, rate limiter, request utilities.
  - `models.py` ? typed data classes (Pydantic) for API responses and normalized OHLCV records.
  - `ingestion.py` ? orchestrators for backfill/incremental updates.
  - `quality.py` ? validation checks (price relationships, volume thresholds, gap detection).

- Rate Limiting Implementation Options:
  - In-memory leaky bucket using `asyncio` or synchronous token bucket (since single-user, simple loop acceptable).
  - Use `tenacity`? prefer lightweight custom to avoid dependency bloat.

## Backfill Workflow Outline

1. Load symbol universe (initial: manual list or from `market_symbols`).
2. For each chunk (?50 symbols):
   - Fetch 30-minute data between start/end using `_fetch_intraday`.
   - Transform JSON to normalized dataclass -> DataFrame -> bulk insert via `psycopg` `COPY`.
   - Record data-quality summary (missing bars, duplicates, anomaly counts).
3. After ingestion, run validation queries for counts vs expected intervals.
4. Persist results to `market_data` and optionally log to `data/reports/backfill_YYYYMMDD.md`.

## Incremental Update Outline

- Determine last stored timestamp per symbol.
- Request bars from `last_timestamp` to now with buffer (e.g. 2 intervals).
- Apply conflict handling (UPSERT on unique constraint) to avoid duplicates.
- Trigger validations: ensure continuity (no >1 interval gaps), volume thresholds, price anomalies.

## Monitoring Outputs

- CLI command `dgas data status` (future Phase 5) should summarise latest timestamp per symbol, missing intervals, last run time.
- Phase 1 deliverable: script or CLI subcommand that prints Markdown/CSV with metrics:
  - Total bars inserted, gaps detected, average volume, last timestamp per symbol.
  - Write to `data/reports/ingestion_summary_<date>.md`.

## Open Questions / Next Steps

- Symbol universe source: initial manual list (config file) vs pulling from EODHD `exchange-symbols` endpoint.
- Handling EODHD premium limits (50k/day): need config for max symbols per run.
- For migrations: choose simple Python script vs `alembic`. Given single-user, propose plain SQL files plus `dgas data init-db` command.
- Consider storing raw JSON payloads temporarily for debugging (phase1 optional).

## Immediate Action Items

1. Scaffold migrations directory with numbered SQL files and helper runner.
2. Implement settings loader to access credentials and DB path.
3. Build synchronous EODHD client with rate limiting wrapper.
4. Create transformation pipeline for raw JSON -> normalized records.
5. Write initial integration test stubs (with mocked responses) to validate fetch & conversion logic.
