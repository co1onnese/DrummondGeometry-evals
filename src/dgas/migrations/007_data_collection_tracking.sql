-- Migration: Data Collection Tracking
-- Purpose: Track data collection service runs and metrics
-- Created: 2025-11-11

-- Table to track data collection cycles
CREATE TABLE IF NOT EXISTS data_collection_runs (
    run_id SERIAL PRIMARY KEY,
    run_timestamp TIMESTAMP NOT NULL DEFAULT NOW(),
    interval_type VARCHAR(10) NOT NULL,
    symbols_requested INTEGER NOT NULL,
    symbols_updated INTEGER NOT NULL,
    symbols_failed INTEGER DEFAULT 0,
    bars_fetched INTEGER NOT NULL,
    bars_stored INTEGER NOT NULL,
    execution_time_ms INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    error_count INTEGER DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_collection_runs_timestamp ON data_collection_runs(run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_status ON data_collection_runs(status, run_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_collection_runs_interval ON data_collection_runs(interval_type, run_timestamp DESC);

-- Comments
COMMENT ON TABLE data_collection_runs IS 'Tracks data collection service execution cycles';
COMMENT ON COLUMN data_collection_runs.run_id IS 'Unique identifier for collection run';
COMMENT ON COLUMN data_collection_runs.run_timestamp IS 'When the collection cycle started';
COMMENT ON COLUMN data_collection_runs.interval_type IS 'Data interval used (e.g., 5m, 15m, 30m)';
COMMENT ON COLUMN data_collection_runs.symbols_requested IS 'Total number of symbols requested for collection';
COMMENT ON COLUMN data_collection_runs.symbols_updated IS 'Number of symbols successfully updated';
COMMENT ON COLUMN data_collection_runs.symbols_failed IS 'Number of symbols that failed to update';
COMMENT ON COLUMN data_collection_runs.bars_fetched IS 'Total number of bars fetched from API';
COMMENT ON COLUMN data_collection_runs.bars_stored IS 'Total number of new bars stored in database';
COMMENT ON COLUMN data_collection_runs.execution_time_ms IS 'Total execution time in milliseconds';
COMMENT ON COLUMN data_collection_runs.status IS 'Run status (SUCCESS, PARTIAL, FAILED)';
COMMENT ON COLUMN data_collection_runs.error_count IS 'Number of errors encountered during collection';
