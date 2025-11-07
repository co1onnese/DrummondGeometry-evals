-- Backfill status tracking table
-- Tracks progress and status of historical data backfill operations

CREATE TABLE IF NOT EXISTS backfill_status (
    symbol VARCHAR(10) NOT NULL,
    interval VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    start_date DATE,
    end_date DATE,
    bars_fetched INTEGER DEFAULT 0,
    bars_stored INTEGER DEFAULT 0,
    quality_score NUMERIC(3,2),
    error_message TEXT,
    last_attempt TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (symbol, interval),

    CONSTRAINT chk_status_valid CHECK (
        status IN ('pending', 'in_progress', 'completed', 'failed', 'skipped')
    ),
    CONSTRAINT chk_quality_score_range CHECK (
        quality_score IS NULL OR (quality_score >= 0 AND quality_score <= 1)
    ),
    CONSTRAINT chk_bars_positive CHECK (
        bars_fetched >= 0 AND bars_stored >= 0
    )
);

-- Index for filtering by status
CREATE INDEX IF NOT EXISTS idx_backfill_status_status
    ON backfill_status (status, symbol);

-- Index for filtering by interval
CREATE INDEX IF NOT EXISTS idx_backfill_status_interval
    ON backfill_status (interval, status);

-- Index for finding failed backfills
CREATE INDEX IF NOT EXISTS idx_backfill_status_failed
    ON backfill_status (status, last_attempt DESC)
    WHERE status = 'failed';

-- Comments
COMMENT ON TABLE backfill_status IS
    'Tracks historical data backfill progress and status for symbols';

COMMENT ON COLUMN backfill_status.status IS
    'Current status: pending, in_progress, completed, failed, skipped';

COMMENT ON COLUMN backfill_status.quality_score IS
    'Data quality score from 0.0 to 1.0 based on completeness and integrity';
