-- Migration: Enhanced market states and pattern detection tables
-- Date: 2025-11-06
-- Description: Add tables for enhanced Drummond Geometry state classification and pattern events

-- Enhanced market state classification table (replaces old market_state approach)
CREATE TABLE IF NOT EXISTS market_states_v2 (
    state_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    interval_type VARCHAR(20) NOT NULL DEFAULT '30min',
    timestamp TIMESTAMPTZ NOT NULL,

    -- State classification (from MarketState enum)
    state VARCHAR(30) NOT NULL,  -- TREND, CONGESTION_ENTRANCE, CONGESTION_ACTION, CONGESTION_EXIT, REVERSAL

    -- Trend direction (from TrendDirection enum)
    trend_direction VARCHAR(10) NOT NULL,  -- UP, DOWN, NEUTRAL

    -- State tracking
    bars_in_state INTEGER NOT NULL DEFAULT 1,
    previous_state VARCHAR(30),
    state_change_reason TEXT,

    -- PLdot slope classification
    pldot_slope_trend VARCHAR(15) NOT NULL,  -- rising, falling, horizontal

    -- Confidence score (0.0-1.0)
    confidence NUMERIC(6,4) NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_state_valid CHECK (
        state IN ('TREND', 'CONGESTION_ENTRANCE', 'CONGESTION_ACTION', 'CONGESTION_EXIT', 'REVERSAL')
    ),
    CONSTRAINT chk_trend_direction_valid CHECK (
        trend_direction IN ('UP', 'DOWN', 'NEUTRAL')
    ),
    CONSTRAINT chk_slope_trend_valid CHECK (
        pldot_slope_trend IN ('rising', 'falling', 'horizontal')
    ),
    CONSTRAINT chk_confidence_range CHECK (
        confidence >= 0.0 AND confidence <= 1.0
    ),
    CONSTRAINT chk_bars_positive CHECK (
        bars_in_state >= 1
    ),
    CONSTRAINT uq_market_states_v2_symbol_interval_timestamp UNIQUE (symbol_id, interval_type, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_market_states_v2_symbol_timestamp
    ON market_states_v2 (symbol_id, interval_type, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_states_v2_state_type
    ON market_states_v2 (symbol_id, state, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_states_v2_trend_direction
    ON market_states_v2 (symbol_id, trend_direction, timestamp DESC);

-- Pattern detection events table
CREATE TABLE IF NOT EXISTS pattern_events (
    pattern_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,
    interval_type VARCHAR(20) NOT NULL DEFAULT '30min',

    -- Pattern classification
    pattern_type VARCHAR(40) NOT NULL,  -- PLDOT_PUSH, PLDOT_REFRESH, EXHAUST, C_WAVE, CONGESTION_OSCILLATION

    -- Pattern direction (1=bullish, -1=bearish, 0=neutral)
    direction SMALLINT NOT NULL,

    -- Time span
    start_timestamp TIMESTAMPTZ NOT NULL,
    end_timestamp TIMESTAMPTZ NOT NULL,

    -- Pattern strength (number of bars/quality)
    strength INTEGER NOT NULL,

    -- Optional pattern-specific metadata
    metadata JSONB,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_pattern_type_valid CHECK (
        pattern_type IN ('PLDOT_PUSH', 'PLDOT_REFRESH', 'EXHAUST', 'C_WAVE', 'CONGESTION_OSCILLATION')
    ),
    CONSTRAINT chk_direction_valid CHECK (
        direction IN (-1, 0, 1)
    ),
    CONSTRAINT chk_strength_positive CHECK (
        strength >= 1
    ),
    CONSTRAINT chk_time_ordering CHECK (
        end_timestamp >= start_timestamp
    )
);

CREATE INDEX IF NOT EXISTS idx_pattern_events_symbol_timestamp
    ON pattern_events (symbol_id, interval_type, start_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pattern_events_type
    ON pattern_events (symbol_id, pattern_type, start_timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_pattern_events_recent
    ON pattern_events (end_timestamp DESC, symbol_id);

-- Multi-timeframe analysis results table
CREATE TABLE IF NOT EXISTS multi_timeframe_analysis (
    analysis_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,

    -- Timeframe configuration
    htf_interval VARCHAR(20) NOT NULL,  -- Higher timeframe (e.g., '4h', '1d')
    trading_interval VARCHAR(20) NOT NULL,  -- Trading timeframe (e.g., '1h', '30min')
    ltf_interval VARCHAR(20),  -- Optional lower timeframe

    -- Analysis timestamp
    timestamp TIMESTAMPTZ NOT NULL,

    -- HTF trend analysis
    htf_trend VARCHAR(10) NOT NULL,  -- UP, DOWN, NEUTRAL
    htf_trend_strength NUMERIC(6,4) NOT NULL,

    -- Trading TF trend
    trading_tf_trend VARCHAR(10) NOT NULL,

    -- Alignment metrics
    alignment_score NUMERIC(6,4) NOT NULL,
    alignment_type VARCHAR(20) NOT NULL,  -- perfect, partial, divergent, conflicting
    trade_permitted BOOLEAN NOT NULL,

    -- PLdot overlay data
    htf_pldot_value NUMERIC(12,6) NOT NULL,
    trading_pldot_value NUMERIC(12,6) NOT NULL,
    pldot_distance_percent NUMERIC(8,4),

    -- Signal analysis
    signal_strength NUMERIC(6,4) NOT NULL,
    risk_level VARCHAR(10) NOT NULL,  -- low, medium, high
    recommended_action VARCHAR(20) NOT NULL,  -- long, short, wait, reduce

    -- Pattern confluence
    pattern_confluence BOOLEAN NOT NULL DEFAULT FALSE,

    -- Confluence zones count
    confluence_zones_count INTEGER NOT NULL DEFAULT 0,

    -- Full analysis details (JSON for flexibility)
    full_analysis JSONB,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_htf_trend_valid CHECK (
        htf_trend IN ('UP', 'DOWN', 'NEUTRAL')
    ),
    CONSTRAINT chk_trading_trend_valid CHECK (
        trading_tf_trend IN ('UP', 'DOWN', 'NEUTRAL')
    ),
    CONSTRAINT chk_alignment_type_valid CHECK (
        alignment_type IN ('perfect', 'partial', 'divergent', 'conflicting')
    ),
    CONSTRAINT chk_risk_level_valid CHECK (
        risk_level IN ('low', 'medium', 'high')
    ),
    CONSTRAINT chk_action_valid CHECK (
        recommended_action IN ('long', 'short', 'wait', 'reduce')
    ),
    CONSTRAINT chk_strength_ranges CHECK (
        htf_trend_strength >= 0.0 AND htf_trend_strength <= 1.0 AND
        alignment_score >= 0.0 AND alignment_score <= 1.0 AND
        signal_strength >= 0.0 AND signal_strength <= 1.0
    ),
    CONSTRAINT uq_mtf_analysis_symbol_intervals_timestamp UNIQUE (
        symbol_id, htf_interval, trading_interval, timestamp
    )
);

CREATE INDEX IF NOT EXISTS idx_mtf_analysis_symbol_timestamp
    ON multi_timeframe_analysis (symbol_id, htf_interval, trading_interval, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_mtf_analysis_recommended_action
    ON multi_timeframe_analysis (symbol_id, recommended_action, timestamp DESC)
    WHERE trade_permitted = TRUE;

CREATE INDEX IF NOT EXISTS idx_mtf_analysis_high_signal_strength
    ON multi_timeframe_analysis (symbol_id, signal_strength, timestamp DESC)
    WHERE signal_strength >= 0.6;

-- Confluence zones table
CREATE TABLE IF NOT EXISTS confluence_zones (
    zone_id BIGSERIAL PRIMARY KEY,
    analysis_id BIGINT REFERENCES multi_timeframe_analysis(analysis_id) ON DELETE CASCADE,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id) ON DELETE CASCADE,

    -- Zone definition
    level NUMERIC(12,6) NOT NULL,  -- Central price level
    upper_bound NUMERIC(12,6) NOT NULL,
    lower_bound NUMERIC(12,6) NOT NULL,

    -- Zone characteristics
    strength INTEGER NOT NULL,  -- Number of timeframes confirming
    timeframes TEXT[] NOT NULL,  -- Array of confirming timeframes
    zone_type VARCHAR(20) NOT NULL,  -- support, resistance, pivot

    -- Time tracking
    first_touch TIMESTAMPTZ NOT NULL,
    last_touch TIMESTAMPTZ NOT NULL,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_zone_type_valid CHECK (
        zone_type IN ('support', 'resistance', 'pivot')
    ),
    CONSTRAINT chk_zone_strength_positive CHECK (
        strength >= 2
    ),
    CONSTRAINT chk_zone_bounds CHECK (
        upper_bound >= level AND level >= lower_bound
    ),
    CONSTRAINT chk_zone_time_ordering CHECK (
        last_touch >= first_touch
    )
);

CREATE INDEX IF NOT EXISTS idx_confluence_zones_symbol
    ON confluence_zones (symbol_id, strength DESC, last_touch DESC);

CREATE INDEX IF NOT EXISTS idx_confluence_zones_analysis
    ON confluence_zones (analysis_id);

-- Comments for documentation
COMMENT ON TABLE market_states_v2 IS 'Enhanced Drummond Geometry market state classification using 5-state model';
COMMENT ON TABLE pattern_events IS 'Detected Drummond Geometry patterns (PLdot push, exhaust, C-wave, etc.)';
COMMENT ON TABLE multi_timeframe_analysis IS 'Multi-timeframe coordination analysis results';
COMMENT ON TABLE confluence_zones IS 'Support/resistance zones confirmed by multiple timeframes';

COMMENT ON COLUMN market_states_v2.state IS 'One of: TREND, CONGESTION_ENTRANCE, CONGESTION_ACTION, CONGESTION_EXIT, REVERSAL';
COMMENT ON COLUMN market_states_v2.trend_direction IS 'Current trend direction: UP, DOWN, NEUTRAL';
COMMENT ON COLUMN market_states_v2.confidence IS 'State classification confidence (0.0-1.0)';

COMMENT ON COLUMN pattern_events.pattern_type IS 'Pattern type: PLDOT_PUSH, PLDOT_REFRESH, EXHAUST, C_WAVE, CONGESTION_OSCILLATION';
COMMENT ON COLUMN pattern_events.direction IS 'Bullish (1), Bearish (-1), or Neutral (0)';
COMMENT ON COLUMN pattern_events.strength IS 'Number of bars/confidence in pattern detection';

COMMENT ON COLUMN multi_timeframe_analysis.alignment_score IS 'How well HTF and trading TF align (0.0-1.0)';
COMMENT ON COLUMN multi_timeframe_analysis.signal_strength IS 'Composite signal strength (0.0-1.0)';
COMMENT ON COLUMN multi_timeframe_analysis.trade_permitted IS 'Whether HTF trend permits trading in current direction';

COMMENT ON COLUMN confluence_zones.strength IS 'Number of timeframes confirming this zone (minimum 2)';
COMMENT ON COLUMN confluence_zones.timeframes IS 'Array of timeframe intervals that confirm this zone';
