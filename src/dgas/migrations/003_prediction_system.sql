-- Migration: Prediction system tables for scheduled signal generation and monitoring
-- Date: 2025-11-06
-- Description: Add tables for prediction runs, generated signals, performance metrics, and scheduler state

-- Prediction run tracking table
CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    interval_type VARCHAR(20) NOT NULL,

    -- Execution metrics
    symbols_requested INTEGER NOT NULL,
    symbols_processed INTEGER NOT NULL,
    signals_generated INTEGER NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,  -- SUCCESS, PARTIAL, FAILED

    -- Latency breakdown (milliseconds)
    data_fetch_ms INTEGER,
    indicator_calc_ms INTEGER,
    signal_generation_ms INTEGER,
    notification_ms INTEGER,

    -- Error tracking
    errors TEXT[],

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_prediction_runs_status CHECK (
        status IN ('SUCCESS', 'PARTIAL', 'FAILED')
    ),
    CONSTRAINT chk_prediction_runs_symbols CHECK (
        symbols_requested >= 0 AND
        symbols_processed >= 0 AND
        symbols_processed <= symbols_requested
    ),
    CONSTRAINT chk_prediction_runs_signals CHECK (
        signals_generated >= 0
    ),
    CONSTRAINT chk_prediction_runs_execution_time CHECK (
        execution_time_ms >= 0
    ),
    CONSTRAINT chk_prediction_runs_latency CHECK (
        (data_fetch_ms IS NULL OR data_fetch_ms >= 0) AND
        (indicator_calc_ms IS NULL OR indicator_calc_ms >= 0) AND
        (signal_generation_ms IS NULL OR signal_generation_ms >= 0) AND
        (notification_ms IS NULL OR notification_ms >= 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_timestamp
    ON prediction_runs(run_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_status
    ON prediction_runs(status, run_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_runs_recent_success
    ON prediction_runs(run_timestamp DESC)
    WHERE status = 'SUCCESS';

-- Generated trading signals table
CREATE TABLE IF NOT EXISTS generated_signals (
    signal_id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES prediction_runs(run_id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,

    -- Signal timing
    signal_timestamp TIMESTAMPTZ NOT NULL,

    -- Signal details
    signal_type VARCHAR(20) NOT NULL,  -- LONG, SHORT, EXIT_LONG, EXIT_SHORT
    entry_price NUMERIC(12,6) NOT NULL,
    stop_loss NUMERIC(12,6) NOT NULL,
    target_price NUMERIC(12,6) NOT NULL,

    -- Confidence & strength
    confidence NUMERIC(6,4) NOT NULL,
    signal_strength NUMERIC(6,4) NOT NULL,
    timeframe_alignment NUMERIC(6,4) NOT NULL,
    risk_reward_ratio NUMERIC(8,2),

    -- Context
    htf_trend VARCHAR(10),  -- UP, DOWN, NEUTRAL
    trading_tf_state VARCHAR(30),  -- Market state at trading timeframe
    confluence_zones_count INTEGER NOT NULL DEFAULT 0,
    pattern_context JSONB,  -- {patterns: [...], indicators: {...}}

    -- Notification tracking
    notification_sent BOOLEAN NOT NULL DEFAULT FALSE,
    notification_channels TEXT[],
    notification_timestamp TIMESTAMPTZ,

    -- Outcome tracking (populated later)
    outcome VARCHAR(20),  -- WIN, LOSS, NEUTRAL, PENDING
    actual_high NUMERIC(12,6),
    actual_low NUMERIC(12,6),
    actual_close NUMERIC(12,6),
    pnl_pct NUMERIC(10,4),
    evaluated_at TIMESTAMPTZ,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_generated_signals_type CHECK (
        signal_type IN ('LONG', 'SHORT', 'EXIT_LONG', 'EXIT_SHORT')
    ),
    CONSTRAINT chk_generated_signals_prices CHECK (
        entry_price > 0 AND
        stop_loss > 0 AND
        target_price > 0
    ),
    CONSTRAINT chk_generated_signals_confidence CHECK (
        confidence >= 0.0 AND confidence <= 1.0
    ),
    CONSTRAINT chk_generated_signals_strength CHECK (
        signal_strength >= 0.0 AND signal_strength <= 1.0
    ),
    CONSTRAINT chk_generated_signals_alignment CHECK (
        timeframe_alignment >= 0.0 AND timeframe_alignment <= 1.0
    ),
    CONSTRAINT chk_generated_signals_confluence CHECK (
        confluence_zones_count >= 0
    ),
    CONSTRAINT chk_generated_signals_htf_trend CHECK (
        htf_trend IS NULL OR htf_trend IN ('UP', 'DOWN', 'NEUTRAL')
    ),
    CONSTRAINT chk_generated_signals_outcome CHECK (
        outcome IS NULL OR outcome IN ('WIN', 'LOSS', 'NEUTRAL', 'PENDING')
    ),
    CONSTRAINT chk_generated_signals_actual_prices CHECK (
        (actual_high IS NULL AND actual_low IS NULL AND actual_close IS NULL) OR
        (actual_high >= actual_close AND actual_close >= actual_low)
    )
);

CREATE INDEX IF NOT EXISTS idx_generated_signals_symbol_timestamp
    ON generated_signals(symbol_id, signal_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_generated_signals_run
    ON generated_signals(run_id);

CREATE INDEX IF NOT EXISTS idx_generated_signals_confidence
    ON generated_signals(confidence DESC, signal_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_generated_signals_high_confidence
    ON generated_signals(signal_id, symbol_id, signal_timestamp DESC)
    WHERE confidence >= 0.7;

CREATE INDEX IF NOT EXISTS idx_generated_signals_pending_evaluation
    ON generated_signals(signal_timestamp, signal_id)
    WHERE outcome IS NULL;

CREATE INDEX IF NOT EXISTS idx_generated_signals_outcome
    ON generated_signals(outcome, signal_timestamp DESC)
    WHERE outcome IS NOT NULL;

-- Performance & calibration metrics table
CREATE TABLE IF NOT EXISTS prediction_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    metric_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_type VARCHAR(50) NOT NULL,  -- latency_p95, throughput_avg, win_rate, etc.
    metric_value NUMERIC(12,4) NOT NULL,

    -- Optional aggregation metadata
    aggregation_period VARCHAR(20),  -- hourly, daily, weekly
    metadata JSONB,  -- {symbol: "AAPL", confidence_bucket: "0.7-0.8", ...}

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_prediction_metrics_aggregation CHECK (
        aggregation_period IS NULL OR
        aggregation_period IN ('hourly', 'daily', 'weekly', 'monthly')
    )
);

CREATE INDEX IF NOT EXISTS idx_prediction_metrics_type_timestamp
    ON prediction_metrics(metric_type, metric_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_metrics_timestamp
    ON prediction_metrics(metric_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_prediction_metrics_aggregation
    ON prediction_metrics(metric_type, aggregation_period, metric_timestamp DESC)
    WHERE aggregation_period IS NOT NULL;

-- Scheduler state table (singleton)
CREATE TABLE IF NOT EXISTS scheduler_state (
    state_id INTEGER PRIMARY KEY DEFAULT 1,
    last_run_timestamp TIMESTAMPTZ,
    next_scheduled_run TIMESTAMPTZ,
    status VARCHAR(20) NOT NULL DEFAULT 'IDLE',  -- IDLE, RUNNING, STOPPED, ERROR
    current_run_id BIGINT REFERENCES prediction_runs(run_id),
    error_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_scheduler_state_singleton CHECK (state_id = 1),
    CONSTRAINT chk_scheduler_state_status CHECK (
        status IN ('IDLE', 'RUNNING', 'STOPPED', 'ERROR')
    )
);

-- Insert singleton row if not exists
INSERT INTO scheduler_state (state_id, status)
VALUES (1, 'IDLE')
ON CONFLICT (state_id) DO NOTHING;

-- Comments for documentation
COMMENT ON TABLE prediction_runs IS 'Tracks each scheduled prediction cycle with performance metrics';
COMMENT ON TABLE generated_signals IS 'All generated trading signals with context and outcome tracking';
COMMENT ON TABLE prediction_metrics IS 'Time-series performance and calibration metrics';
COMMENT ON TABLE scheduler_state IS 'Singleton table tracking scheduler status for recovery and monitoring';

COMMENT ON COLUMN prediction_runs.status IS 'Execution status: SUCCESS (complete), PARTIAL (some failures), FAILED (critical error)';
COMMENT ON COLUMN prediction_runs.execution_time_ms IS 'Total execution time from start to finish in milliseconds';
COMMENT ON COLUMN prediction_runs.data_fetch_ms IS 'Time spent fetching market data from EODHD API';
COMMENT ON COLUMN prediction_runs.indicator_calc_ms IS 'Time spent calculating Drummond indicators';
COMMENT ON COLUMN prediction_runs.signal_generation_ms IS 'Time spent generating and filtering signals';
COMMENT ON COLUMN prediction_runs.notification_ms IS 'Time spent delivering notifications';

COMMENT ON COLUMN generated_signals.signal_type IS 'Signal direction: LONG (buy), SHORT (sell), EXIT_LONG, EXIT_SHORT';
COMMENT ON COLUMN generated_signals.confidence IS 'Signal confidence score (0.0-1.0)';
COMMENT ON COLUMN generated_signals.signal_strength IS 'Signal strength based on pattern confluence (0.0-1.0)';
COMMENT ON COLUMN generated_signals.timeframe_alignment IS 'Multi-timeframe alignment score (0.0-1.0)';
COMMENT ON COLUMN generated_signals.pattern_context IS 'JSON object with triggering patterns and indicator values';
COMMENT ON COLUMN generated_signals.outcome IS 'Actual outcome after evaluation: WIN (target hit), LOSS (stop hit), NEUTRAL, PENDING';
COMMENT ON COLUMN generated_signals.pnl_pct IS 'Percentage profit/loss if signal was taken';

COMMENT ON COLUMN prediction_metrics.metric_type IS 'Type of metric: latency_p95, throughput_avg, win_rate, accuracy, etc.';
COMMENT ON COLUMN prediction_metrics.aggregation_period IS 'Time period for aggregated metrics';
COMMENT ON COLUMN prediction_metrics.metadata IS 'JSON object with additional metric dimensions (symbol, confidence_bucket, etc.)';

COMMENT ON COLUMN scheduler_state.status IS 'Current scheduler status: IDLE, RUNNING, STOPPED, ERROR';
COMMENT ON COLUMN scheduler_state.current_run_id IS 'Foreign key to prediction_runs for the currently executing run';
