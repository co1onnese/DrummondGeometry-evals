-- ============================================================================
-- CLEAN DATABASE SCHEMA DUMP
-- Generated: 2025-11-08
-- Purpose: Production-ready schema with only tables used by current code
-- ============================================================================

-- ACTIVE TABLES (used by production code & has data):
-- 1. market_data (7,145,384 rows) - Core OHLCV data
-- 2. market_symbols (518 rows) - Symbol registry
-- 3. exchanges (1 row) - Exchange definitions
-- 4. trading_days (361 rows) - Exchange calendar
-- 5. backtest_results (1,968 rows) - Backtest results
-- 6. backtest_trades (16,633 rows) - Individual trades
-- 7. generated_signals (90 rows) - Generated trading signals
-- 8. prediction_runs (135 rows) - Prediction system runs
-- 9. prediction_metrics (60 rows) - Prediction metrics
-- 10. scheduler_state (1 row) - Scheduler state
-- 11. schema_migrations (6 rows) - Migration tracking (REQUIRED)

-- UNUSED TABLES DROPPED (safe to remove):
-- - backfill_status (1,036 rows) - UNUSED by current code
-- - drummond_lines (0 rows) - UNUSED
-- - envelope_bands (0 rows) - UNUSED
-- - market_data_metadata (0 rows) - UNUSED
-- - market_state (0 rows) - UNUSED
-- - pldot_calculations (0 rows) - UNUSED
-- - trading_signals (0 rows) - UNUSED

-- TABLES RETAINED BUT EMPTY (used by code, may be populated later):
-- - confluence_zones
-- - market_holidays
-- - market_states_v2
-- - multi_timeframe_analysis
-- - pattern_events

-- ============================================================================
-- TABLE: market_symbols
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_symbols (
    symbol_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(255),
    exchange VARCHAR(20) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap NUMERIC(15,2),
    index_membership TEXT[],  -- Array of indices (e.g., NASDAQ100, SP500)
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_market_symbols_symbol ON market_symbols(symbol);
CREATE INDEX IF NOT EXISTS idx_market_symbols_exchange ON market_symbols(exchange);
CREATE INDEX IF NOT EXISTS idx_market_symbols_active ON market_symbols(is_active);
CREATE INDEX IF NOT EXISTS idx_market_symbols_index_membership ON market_symbols USING GIN(index_membership);

-- ============================================================================
-- TABLE: market_data
-- ============================================================================
CREATE TABLE IF NOT EXISTS market_data (
    data_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    interval_type VARCHAR(20) NOT NULL DEFAULT '30m',
    open_price NUMERIC(12,6) NOT NULL,
    high_price NUMERIC(12,6) NOT NULL,
    low_price NUMERIC(12,6) NOT NULL,
    close_price NUMERIC(12,6) NOT NULL,
    volume BIGINT NOT NULL DEFAULT 0,
    vwap NUMERIC(12,6),
    true_range NUMERIC(12,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_prices_positive CHECK (
        open_price > 0 AND high_price > 0 AND low_price > 0 AND close_price > 0
    ),
    CONSTRAINT chk_ohlc_relationships CHECK (
        high_price >= open_price AND
        high_price >= close_price AND
        low_price <= open_price AND
        low_price <= close_price AND
        (high_price - low_price) >= ABS(open_price - close_price)
    ),
    CONSTRAINT chk_volume_positive CHECK (volume >= 0),
    CONSTRAINT uq_market_data_symbol_timestamp UNIQUE (symbol_id, timestamp, interval_type)
);

CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp
    ON market_data (symbol_id, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_recent
    ON market_data (timestamp DESC, symbol_id);
CREATE INDEX IF NOT EXISTS idx_market_data_interval
    ON market_data (interval_type);
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_interval
    ON market_data (symbol_id, interval_type, timestamp DESC);

-- ============================================================================
-- TABLE: exchanges
-- ============================================================================
CREATE TABLE IF NOT EXISTS exchanges (
    exchange_code VARCHAR(10) PRIMARY KEY,
    country_name VARCHAR(100) NOT NULL,
    timezone VARCHAR(50) NOT NULL,
    market_open TIME NOT NULL,
    market_close TIME NOT NULL,
    country_code VARCHAR(3),  -- Fixed from VARCHAR(2) to VARCHAR(3)
    currency_code VARCHAR(3) NOT NULL DEFAULT 'USD',
    last_synced_at TIMESTAMPTZ,
    sync_range_start DATE,
    sync_range_end DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================================
-- TABLE: trading_days
-- ============================================================================
CREATE TABLE IF NOT EXISTS trading_days (
    trading_date DATE NOT NULL,
    exchange_code VARCHAR(10) NOT NULL REFERENCES exchanges(exchange_code) ON DELETE CASCADE,
    is_trading_day BOOLEAN NOT NULL,
    actual_open TIME,
    actual_close TIME,
    holiday_name VARCHAR(100),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (trading_date, exchange_code)
);

CREATE INDEX IF NOT EXISTS idx_trading_days_exchange
    ON trading_days (exchange_code, trading_date DESC);
CREATE INDEX IF NOT EXISTS idx_trading_days_date
    ON trading_days (trading_date DESC);
CREATE INDEX IF NOT EXISTS idx_trading_days_trading
    ON trading_days (exchange_code, is_trading_day, trading_date);

-- ============================================================================
-- TABLE: backtest_results
-- ============================================================================
CREATE TABLE IF NOT EXISTS backtest_results (
    result_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    strategy_name VARCHAR(100) NOT NULL,
    config JSONB NOT NULL,
    starting_cash NUMERIC(15,2) NOT NULL DEFAULT 100000.00,
    ending_cash NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    ending_equity NUMERIC(15,2) NOT NULL DEFAULT 0.00,
    total_return NUMERIC(10,6),
    annual_return NUMERIC(10,6),
    sharpe_ratio NUMERIC(10,6),
    max_drawdown NUMERIC(10,6),
    max_drawdown_pct NUMERIC(10,6),
    win_rate NUMERIC(10,6),
    profit_factor NUMERIC(10,6),
    total_trades INTEGER NOT NULL DEFAULT 0,
    winning_trades INTEGER NOT NULL DEFAULT 0,
    losing_trades INTEGER NOT NULL DEFAULT 0,
    avg_win NUMERIC(15,2),
    avg_loss NUMERIC(15,2),
    best_trade NUMERIC(15,2),
    worst_trade NUMERIC(15,2),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_results_symbol
    ON backtest_results (symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy
    ON backtest_results (strategy_name);
CREATE INDEX IF NOT EXISTS idx_backtest_results_created
    ON backtest_results (created_at DESC);

-- ============================================================================
-- TABLE: backtest_trades
-- ============================================================================
CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id SERIAL PRIMARY KEY,
    result_id INTEGER NOT NULL REFERENCES backtest_results(result_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    entry_time TIMESTAMPTZ NOT NULL,
    exit_time TIMESTAMPTZ,
    entry_price NUMERIC(12,6) NOT NULL,
    exit_price NUMERIC(12,6),
    quantity INTEGER NOT NULL,
    direction VARCHAR(10) NOT NULL,  -- 'LONG' or 'SHORT'
    pnl NUMERIC(15,2),
    pnl_pct NUMERIC(10,6),
    commission NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    slippage NUMERIC(10,2) NOT NULL DEFAULT 0.00,
    duration_hours NUMERIC(10,2),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_result
    ON backtest_trades (result_id);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol
    ON backtest_trades (symbol);
CREATE INDEX IF NOT EXISTS idx_backtest_trades_entry
    ON backtest_trades (entry_time);

-- ============================================================================
-- TABLE: generated_signals
-- ============================================================================
CREATE TABLE IF NOT EXISTS generated_signals (
    signal_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    signal_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    interval_type VARCHAR(20) NOT NULL DEFAULT '30m',
    strength NUMERIC(5,2) NOT NULL,
    price NUMERIC(12,6) NOT NULL,
    stop_loss NUMERIC(12,6),
    target_price NUMERIC(12,6),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_generated_signals_symbol
    ON generated_signals (symbol);
CREATE INDEX IF NOT EXISTS idx_generated_signals_timestamp
    ON generated_signals (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_generated_signals_type
    ON generated_signals (signal_type);

-- ============================================================================
-- TABLE: prediction_runs
-- ============================================================================
CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id SERIAL PRIMARY KEY,
    model_name VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    symbols TEXT[] NOT NULL,  -- Array of symbols
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',  -- PENDING, RUNNING, COMPLETED, FAILED
    config JSONB,
    metrics JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_model
    ON prediction_runs (model_name, model_version);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_status
    ON prediction_runs (status);
CREATE INDEX IF NOT EXISTS idx_prediction_runs_created
    ON prediction_runs (created_at DESC);

-- ============================================================================
-- TABLE: prediction_metrics
-- ============================================================================
CREATE TABLE IF NOT EXISTS prediction_metrics (
    metric_id SERIAL PRIMARY KEY,
    run_id INTEGER NOT NULL REFERENCES prediction_runs(run_id) ON DELETE CASCADE,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    actual_price NUMERIC(12,6),
    predicted_price NUMERIC(12,6),
    error NUMERIC(12,6),
    error_pct NUMERIC(10,6),
    direction_correct BOOLEAN,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prediction_metrics_run
    ON prediction_metrics (run_id);
CREATE INDEX IF NOT EXISTS idx_prediction_metrics_symbol
    ON prediction_metrics (symbol);
CREATE INDEX IF NOT EXISTS idx_prediction_metrics_timestamp
    ON prediction_metrics (timestamp DESC);

-- ============================================================================
-- TABLE: scheduler_state
-- ============================================================================
CREATE TABLE IF NOT EXISTS scheduler_state (
    state_id SERIAL PRIMARY KEY,
    job_name VARCHAR(100) NOT NULL UNIQUE,
    last_run TIMESTAMPTZ,
    next_run TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'IDLE',  -- IDLE, RUNNING, FAILED
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_scheduler_state_job
    ON scheduler_state (job_name);

-- ============================================================================
-- TABLE: schema_migrations
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    id SERIAL PRIMARY KEY,
    version VARCHAR(50) NOT NULL UNIQUE,
    description TEXT,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schema_migrations_version
    ON schema_migrations (version);

-- ============================================================================
-- RETAINED BUT EMPTY TABLES (used by code, may be populated later)
-- ============================================================================

-- confluence_zones (EMPTY - used by code)
CREATE TABLE IF NOT EXISTS confluence_zones (
    zone_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    zone_level NUMERIC(12,6) NOT NULL,
    strength NUMERIC(5,2) NOT NULL,
    zone_type VARCHAR(50) NOT NULL,  -- SUPPORT, RESISTANCE, S/R
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_confluence_zones_symbol
    ON confluence_zones (symbol);
CREATE INDEX IF NOT EXISTS idx_confluence_zones_timestamp
    ON confluence_zones (timestamp DESC);

-- market_holidays (EMPTY - used by code)
CREATE TABLE IF NOT EXISTS market_holidays (
    holiday_id SERIAL PRIMARY KEY,
    exchange_code VARCHAR(10) NOT NULL REFERENCES exchanges(exchange_code) ON DELETE CASCADE,
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(100) NOT NULL,
    is_half_day BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_holidays_exchange
    ON market_holidays (exchange_code, holiday_date);

-- market_states_v2 (EMPTY - used by code)
CREATE TABLE IF NOT EXISTS market_states_v2 (
    state_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    state_type VARCHAR(50) NOT NULL,  -- ACCUMULATION, MARKUP, DISTRIBUTION, DOWNDOWN
    strength NUMERIC(5,2) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_states_v2_symbol
    ON market_states_v2 (symbol);
CREATE INDEX IF NOT EXISTS idx_market_states_v2_timestamp
    ON market_states_v2 (timestamp DESC);

-- multi_timeframe_analysis (EMPTY - used by code)
CREATE TABLE IF NOT EXISTS multi_timeframe_analysis (
    analysis_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    timeframe VARCHAR(10) NOT NULL,  -- 30m, 1h, 1d, etc
    analysis_data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_multi_timeframe_symbol
    ON multi_timeframe_analysis (symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_multi_timeframe_tf
    ON multi_timeframe_analysis (timeframe);

-- pattern_events (EMPTY - used by code)
CREATE TABLE IF NOT EXISTS pattern_events (
    event_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    pattern_type VARCHAR(50) NOT NULL,  -- e.g., 'BREAKOUT', 'REVERSAL'
    strength NUMERIC(5,2) NOT NULL,
    price NUMERIC(12,6) NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pattern_events_symbol
    ON pattern_events (symbol);
CREATE INDEX IF NOT EXISTS idx_pattern_events_timestamp
    ON pattern_events (timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_pattern_events_type
    ON pattern_events (pattern_type);

-- ============================================================================
-- END OF SCHEMA
-- ============================================================================
