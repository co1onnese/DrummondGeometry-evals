-- Migration 004: Exchange Calendar and Trading Hours
-- Purpose: Store exchange metadata, market holidays, and trading days from EODHD API
-- This enables market-hours-aware scheduling without excessive API calls

-- ============================================================================
-- Exchange Metadata
-- ============================================================================

CREATE TABLE IF NOT EXISTS exchanges (
    exchange_code VARCHAR(10) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    timezone VARCHAR(50) NOT NULL,  -- e.g., "America/New_York"

    -- Standard trading hours (can be overridden per day)
    market_open TIME NOT NULL,      -- e.g., 09:30:00
    market_close TIME NOT NULL,     -- e.g., 16:00:00

    -- Metadata
    country_code VARCHAR(2),         -- ISO country code
    currency VARCHAR(3),             -- ISO currency code

    -- API sync tracking
    last_synced_at TIMESTAMP WITH TIME ZONE,
    sync_range_start DATE,           -- Start of cached calendar range
    sync_range_end DATE,             -- End of cached calendar range

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

COMMENT ON TABLE exchanges IS 'Exchange metadata from EODHD API';
COMMENT ON COLUMN exchanges.exchange_code IS 'Exchange identifier (e.g., US, NYSE, NASDAQ)';
COMMENT ON COLUMN exchanges.timezone IS 'IANA timezone for exchange location';
COMMENT ON COLUMN exchanges.market_open IS 'Standard market open time (local to exchange)';
COMMENT ON COLUMN exchanges.market_close IS 'Standard market close time (local to exchange)';
COMMENT ON COLUMN exchanges.last_synced_at IS 'Last time calendar data was fetched from EODHD';
COMMENT ON COLUMN exchanges.sync_range_start IS 'Earliest date with cached calendar data';
COMMENT ON COLUMN exchanges.sync_range_end IS 'Latest date with cached calendar data';

-- ============================================================================
-- Market Holidays
-- ============================================================================

CREATE TABLE IF NOT EXISTS market_holidays (
    id SERIAL PRIMARY KEY,
    exchange_code VARCHAR(10) NOT NULL REFERENCES exchanges(exchange_code) ON DELETE CASCADE,

    -- Holiday details
    holiday_date DATE NOT NULL,
    holiday_name VARCHAR(200),

    -- Half-day support
    is_half_day BOOLEAN DEFAULT FALSE,
    early_close_time TIME,           -- Market close time for half-days

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_exchange_holiday UNIQUE(exchange_code, holiday_date)
);

COMMENT ON TABLE market_holidays IS 'Market closure and half-day schedules from EODHD';
COMMENT ON COLUMN market_holidays.is_half_day IS 'True if market closes early (not full closure)';
COMMENT ON COLUMN market_holidays.early_close_time IS 'Early close time for half-days (NULL for full closures)';

-- Index for fast holiday lookups
CREATE INDEX idx_market_holidays_exchange_date
    ON market_holidays(exchange_code, holiday_date);

-- ============================================================================
-- Trading Days Cache
-- ============================================================================

CREATE TABLE IF NOT EXISTS trading_days (
    id SERIAL PRIMARY KEY,
    exchange_code VARCHAR(10) NOT NULL REFERENCES exchanges(exchange_code) ON DELETE CASCADE,

    -- Date and trading status
    trading_date DATE NOT NULL,
    is_trading_day BOOLEAN NOT NULL DEFAULT TRUE,

    -- Actual hours for this specific day (may differ from exchange defaults)
    actual_open TIME,                -- Overrides exchange.market_open if set
    actual_close TIME,               -- Overrides exchange.market_close if set

    -- Metadata
    notes TEXT,                      -- e.g., "Early close before Thanksgiving"
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_exchange_trading_date UNIQUE(exchange_code, trading_date)
);

COMMENT ON TABLE trading_days IS 'Cached trading day calendar for fast lookups';
COMMENT ON COLUMN trading_days.is_trading_day IS 'False for weekends, holidays, and special closures';
COMMENT ON COLUMN trading_days.actual_open IS 'Market open time (NULL uses exchange default)';
COMMENT ON COLUMN trading_days.actual_close IS 'Market close time (NULL uses exchange default)';
COMMENT ON COLUMN trading_days.notes IS 'Human-readable notes about special trading conditions';

-- Indexes for fast date range queries
CREATE INDEX idx_trading_days_exchange_date
    ON trading_days(exchange_code, trading_date);

CREATE INDEX idx_trading_days_is_trading
    ON trading_days(exchange_code, trading_date)
    WHERE is_trading_day = TRUE;

-- ============================================================================
-- Data Integrity Constraints
-- ============================================================================

-- Ensure market_open < market_close
ALTER TABLE exchanges
    ADD CONSTRAINT check_market_hours
    CHECK (market_open < market_close);

-- Ensure early_close_time is set for half-days
ALTER TABLE market_holidays
    ADD CONSTRAINT check_half_day_time
    CHECK (
        (is_half_day = FALSE AND early_close_time IS NULL) OR
        (is_half_day = TRUE AND early_close_time IS NOT NULL)
    );

-- Ensure actual_close > actual_open if both set
ALTER TABLE trading_days
    ADD CONSTRAINT check_actual_hours
    CHECK (
        actual_open IS NULL OR
        actual_close IS NULL OR
        actual_open < actual_close
    );

-- ============================================================================
-- Default Exchange Data
-- ============================================================================

-- Insert US market defaults (updated by API sync)
INSERT INTO exchanges (
    exchange_code,
    name,
    timezone,
    market_open,
    market_close,
    country_code,
    currency
) VALUES (
    'US',
    'US Stock Exchanges',
    'America/New_York',
    '09:30:00',
    '16:00:00',
    'US',
    'USD'
) ON CONFLICT (exchange_code) DO NOTHING;

COMMENT ON TABLE exchanges IS 'Exchange metadata and standard trading hours';
COMMENT ON TABLE market_holidays IS 'Market closures and early close days from EODHD API';
COMMENT ON TABLE trading_days IS 'Pre-computed trading calendar for fast market hours checks';
