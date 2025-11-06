-- Initial database schema for the Drummond Geometry Analysis System

CREATE TABLE IF NOT EXISTS market_symbols (
    symbol_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(255),
    exchange VARCHAR(20) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap NUMERIC(15,2),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_data (
    data_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    interval_type VARCHAR(20) NOT NULL DEFAULT '30min',
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

CREATE TABLE IF NOT EXISTS market_data_metadata (
    metadata_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id) ON DELETE CASCADE,
    source VARCHAR(50) NOT NULL,
    data_quality_score NUMERIC(3,2),
    gap_fill_method VARCHAR(20),
    adjusted_for_splits BOOLEAN DEFAULT TRUE,
    adjusted_for_dividends BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pldot_calculations (
    pldot_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    pldot_value NUMERIC(12,6) NOT NULL,
    dot_high NUMERIC(12,6) NOT NULL,
    dot_low NUMERIC(12,6) NOT NULL,
    dot_midpoint NUMERIC(12,6) NOT NULL,
    volume_weighted_pldot NUMERIC(12,6),
    volume_weighted_dot_high NUMERIC(12,6),
    volume_weighted_dot_low NUMERIC(12,6),
    pldot_slope NUMERIC(10,6),
    pldot_momentum NUMERIC(12,6),
    calculation_period INTEGER NOT NULL DEFAULT 20,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_pldot_symbol_timestamp UNIQUE (symbol_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_pldot_symbol_timestamp
    ON pldot_calculations (symbol_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS envelope_bands (
    envelope_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    upper_band NUMERIC(12,6) NOT NULL,
    lower_band NUMERIC(12,6) NOT NULL,
    middle_band NUMERIC(12,6) NOT NULL,
    band_width NUMERIC(12,6),
    band_position NUMERIC(6,4),
    band_squeeze BOOLEAN NOT NULL DEFAULT FALSE,
    band_period INTEGER NOT NULL,
    band_multiplier NUMERIC(6,2) NOT NULL,
    envelope_type VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_envelope_symbol_timestamp
    ON envelope_bands (symbol_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS drummond_lines (
    line_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    line_start_timestamp TIMESTAMPTZ NOT NULL,
    line_end_timestamp TIMESTAMPTZ,
    line_start_price NUMERIC(12,6) NOT NULL,
    line_end_price NUMERIC(12,6),
    line_type VARCHAR(20) NOT NULL,
    line_slope NUMERIC(10,6),
    line_strength NUMERIC(6,4),
    line_confidence NUMERIC(6,4),
    volume_at_line NUMERIC(15,2),
    volume_weighted_line BOOLEAN NOT NULL DEFAULT FALSE,
    touches_count INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_drummond_lines_symbol_timestamp
    ON drummond_lines (symbol_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS market_state (
    state_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ NOT NULL,
    trend_state VARCHAR(20) NOT NULL,
    congestion_state VARCHAR(20) NOT NULL,
    reversal_state VARCHAR(20) NOT NULL,
    trend_confidence NUMERIC(6,4) NOT NULL DEFAULT 0,
    congestion_confidence NUMERIC(6,4) NOT NULL DEFAULT 0,
    reversal_confidence NUMERIC(6,4) NOT NULL DEFAULT 0,
    state_duration_intervals INTEGER NOT NULL DEFAULT 1,
    previous_state VARCHAR(50),
    state_change_reason TEXT,
    volatility_index NUMERIC(10,6),
    momentum_score NUMERIC(10,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_market_state_symbol_timestamp
    ON market_state (symbol_id, timestamp DESC);

CREATE TABLE IF NOT EXISTS trading_signals (
    signal_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    signal_timestamp TIMESTAMPTZ NOT NULL,
    signal_type VARCHAR(30) NOT NULL,
    signal_strength NUMERIC(6,4) NOT NULL,
    signal_confidence NUMERIC(6,4) NOT NULL,
    entry_price NUMERIC(12,6),
    stop_loss NUMERIC(12,6),
    target_price NUMERIC(12,6),
    risk_reward_ratio NUMERIC(8,4),
    signal_reason TEXT,
    technical_indicators JSONB,
    recommended_position_size NUMERIC(8,4),
    max_risk_per_trade NUMERIC(6,4),
    is_executed BOOLEAN NOT NULL DEFAULT FALSE,
    execution_timestamp TIMESTAMPTZ,
    execution_price NUMERIC(12,6),
    signal_status VARCHAR(20) NOT NULL DEFAULT 'active',
    profit_loss NUMERIC(12,6),
    return_percentage NUMERIC(8,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trading_signals_symbol_timestamp
    ON trading_signals (symbol_id, signal_timestamp DESC);

CREATE TABLE IF NOT EXISTS backtest_results (
    backtest_id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol_id INTEGER REFERENCES market_symbols(symbol_id) ON DELETE SET NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital NUMERIC(15,2) NOT NULL,
    commission_rate NUMERIC(6,4) NOT NULL DEFAULT 0.001,
    final_capital NUMERIC(15,2),
    total_return NUMERIC(8,4),
    annualized_return NUMERIC(8,4),
    volatility NUMERIC(8,4),
    sharpe_ratio NUMERIC(8,4),
    max_drawdown NUMERIC(8,4),
    max_drawdown_duration INTEGER,
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate NUMERIC(6,4),
    avg_win NUMERIC(12,6),
    avg_loss NUMERIC(12,6),
    profit_factor NUMERIC(8,4),
    value_at_risk NUMERIC(8,4),
    conditional_var NUMERIC(8,4),
    beta NUMERIC(10,6),
    alpha NUMERIC(8,4),
    calmar_ratio NUMERIC(8,4),
    sortino_ratio NUMERIC(8,4),
    information_ratio NUMERIC(8,4),
    test_config JSONB,
    benchmark_symbol_id INTEGER REFERENCES market_symbols(symbol_id) ON DELETE SET NULL,
    benchmark_return NUMERIC(8,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_backtest_results_strategy_dates
    ON backtest_results (strategy_name, start_date, end_date);

CREATE TABLE IF NOT EXISTS backtest_trades (
    trade_id BIGSERIAL PRIMARY KEY,
    backtest_id BIGINT NOT NULL REFERENCES backtest_results(backtest_id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    entry_timestamp TIMESTAMPTZ NOT NULL,
    exit_timestamp TIMESTAMPTZ,
    entry_price NUMERIC(12,6) NOT NULL,
    exit_price NUMERIC(12,6),
    position_size NUMERIC(12,6) NOT NULL,
    trade_type VARCHAR(10) NOT NULL,
    gross_profit_loss NUMERIC(12,6),
    net_profit_loss NUMERIC(12,6),
    return_percentage NUMERIC(8,4),
    trade_duration_hours INTEGER,
    signal_id BIGINT REFERENCES trading_signals(signal_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_backtest
    ON backtest_trades (backtest_id);

CREATE INDEX IF NOT EXISTS idx_backtest_trades_symbol
    ON backtest_trades (symbol_id, entry_timestamp);
