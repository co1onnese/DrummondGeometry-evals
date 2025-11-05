# Drummond Geometry Analysis System - PostgreSQL Database Schema

## Overview

This document outlines the comprehensive PostgreSQL database schema for the Drummond Geometry Analysis System, designed to support high-frequency US stock market analysis with 30-minute intervals, PLDot calculations, envelope bands, Drummond lines, market state tracking, and trading signals.

## Schema Architecture

### 1. Market Data Tables

#### 1.1 Market Symbols
```sql
CREATE TABLE market_symbols (
    symbol_id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) NOT NULL UNIQUE,
    company_name VARCHAR(255),
    exchange VARCHAR(20) NOT NULL,
    sector VARCHAR(100),
    industry VARCHAR(100),
    market_cap DECIMAL(15,2),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 1.2 Market Data (30-Minute OHLCV)
```sql
CREATE TABLE market_data (
    data_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    timestamp TIMESTAMP NOT NULL,
    interval_type VARCHAR(10) DEFAULT '30min',
    open_price DECIMAL(10,4) NOT NULL,
    high_price DECIMAL(10,4) NOT NULL,
    low_price DECIMAL(10,4) NOT NULL,
    close_price DECIMAL(10,4) NOT NULL,
    volume BIGINT DEFAULT 0,
    vwap DECIMAL(10,4), -- Volume Weighted Average Price
    true_range DECIMAL(10,4), -- For ATR calculations
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT chk_prices_positive CHECK (
        open_price > 0 AND high_price > 0 AND low_price > 0 AND close_price > 0
    ),
    CONSTRAINT chk_ohlc_logic CHECK (
        high_price >= open_price AND 
        high_price >= high_price AND 
        high_price >= close_price AND
        low_price <= open_price AND 
        low_price <= high_price AND 
        low_price <= close_price
    )
);

-- Unique constraint for symbol and timestamp
CREATE UNIQUE INDEX idx_market_data_symbol_timestamp 
ON market_data(symbol_id, timestamp);
```

#### 1.3 Market Data Metadata
```sql
CREATE TABLE market_data_metadata (
    metadata_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id),
    source VARCHAR(50) NOT NULL, -- 'alpha_vantage', 'polygon', 'yahoo'
    data_quality_score DECIMAL(3,2), -- 0.00 to 1.00
    gap_fill_method VARCHAR(20), -- 'none', 'linear', 'forward_fill'
    adjusted_for_splits BOOLEAN DEFAULT true,
    adjusted_for_dividends BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. PLDot Calculations Table

```sql
CREATE TABLE pldot_calculations (
    pldot_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id),
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    timestamp TIMESTAMP NOT NULL,
    
    -- PLDot Components
    pldot_value DECIMAL(10,4) NOT NULL,
    dot_high DECIMAL(10,4) NOT NULL,
    dot_low DECIMAL(10,4) NOT NULL,
    dot_midpoint DECIMAL(10,4) NOT NULL,
    
    -- Volume-weighted calculations
    volume_weighted_pldot DECIMAL(10,4),
    volume_weighted_dot_high DECIMAL(10,4),
    volume_weighted_dot_low DECIMAL(10,4),
    
    -- Slope and momentum
    pldot_slope DECIMAL(8,6),
    pldot_momentum DECIMAL(10,4),
    
    -- Time period context
    calculation_period INTEGER DEFAULT 20, -- Lookback period
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for PLDot queries
CREATE INDEX idx_pldot_symbol_timestamp ON pldot_calculations(symbol_id, timestamp DESC);
CREATE INDEX idx_pldot_value_range ON pldot_calculations(pldot_value) WHERE pldot_value IS NOT NULL;
CREATE INDEX idx_pldot_momentum ON pldot_calculations(pldot_momentum) WHERE plpot_momentum IS NOT NULL;
```

### 3. Envelope Bands Table

```sql
CREATE TABLE envelope_bands (
    envelope_id BIGSERIAL PRIMARY KEY,
    data_id BIGINT NOT NULL REFERENCES market_data(data_id),
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    timestamp TIMESTAMP NOT NULL,
    
    -- Band calculations
    upper_band DECIMAL(10,4) NOT NULL,
    lower_band DECIMAL(10,4) NOT NULL,
    middle_band DECIMAL(10,4) NOT NULL, -- Typically moving average
    
    -- Band characteristics
    band_width DECIMAL(10,4), -- Upper - Lower
    band_position DECIMAL(5,4), -- Current price position within bands (0 to 1)
    band_squeeze BOOLEAN DEFAULT false, -- Volatility squeeze detection
    
    -- Parameters used
    band_period INTEGER NOT NULL, -- e.g., 20, 50
    band_multiplier DECIMAL(4,2) NOT NULL, -- e.g., 2.0 for 2 standard deviations
    
    -- Envelope type
    envelope_type VARCHAR(20) NOT NULL, -- 'bollinger', 'keltner', 'donchian'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_envelope_symbol_timestamp ON envelope_bands(symbol_id, timestamp DESC);
CREATE INDEX idx_envelope_band_squeeze ON envelope_bands(symbol_id, band_squeeze, timestamp DESC);
CREATE INDEX idx_envelope_width ON envelope_bands(band_width) WHERE band_width IS NOT NULL;
```

### 4. Drummond Lines Table

```sql
CREATE TABLE drummond_lines (
    line_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    timestamp TIMESTAMP NOT NULL,
    
    -- Line coordinates
    line_start_timestamp TIMESTAMP NOT NULL,
    line_end_timestamp TIMESTAMP,
    line_start_price DECIMAL(10,4) NOT NULL,
    line_end_price DECIMAL(10,4),
    
    -- Line characteristics
    line_type VARCHAR(20) NOT NULL, -- 'support', 'resistance', 'trend', 'drummond'
    line_slope DECIMAL(8,6),
    line_strength DECIMAL(5,4), -- 0.00 to 1.00
    line_confidence DECIMAL(5,4), -- 0.00 to 1.00
    
    -- Volume context
    volume_at_line DECIMAL(15,2),
    volume_weighted_line BOOLEAN DEFAULT false,
    
    -- Line validation
    touches_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_drummond_lines_symbol_timestamp ON drummond_lines(symbol_id, timestamp DESC);
CREATE INDEX idx_drummond_lines_type ON drummond_lines(line_type, is_active);
CREATE INDEX idx_drummond_lines_strength ON drummond_lines(line_strength) WHERE line_strength IS NOT NULL;
CREATE INDEX idx_drummond_lines_active ON drummond_lines(symbol_id, is_active) WHERE is_active = true;
```

### 5. Market State Tracking Table

```sql
CREATE TABLE market_state (
    state_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    timestamp TIMESTAMP NOT NULL,
    
    -- State classifications
    trend_state VARCHAR(20) NOT NULL, -- 'bullish', 'bearish', 'neutral'
    congestion_state VARCHAR(20) NOT NULL, -- 'low', 'medium', 'high', 'none'
    reversal_state VARCHAR(20) NOT NULL, -- 'bullish_reversal', 'bearish_reversal', 'none'
    
    -- State confidence scores
    trend_confidence DECIMAL(5,4) DEFAULT 0.0000,
    congestion_confidence DECIMAL(5,4) DEFAULT 0.0000,
    reversal_confidence DECIMAL(5,4) DEFAULT 0.0000,
    
    -- State context
    state_duration_intervals INTEGER DEFAULT 1, -- How many intervals in current state
    previous_state VARCHAR(50),
    state_change_reason TEXT,
    
    -- Additional metrics
    volatility_index DECIMAL(8,6), -- Market volatility measure
    momentum_score DECIMAL(8,6), -- Overall momentum
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_market_state_symbol_timestamp ON market_state(symbol_id, timestamp DESC);
CREATE INDEX idx_market_state_trend ON market_state(trend_state, trend_confidence DESC);
CREATE INDEX idx_market_state_congestion ON market_state(congestion_state, timestamp DESC);
CREATE INDEX idx_market_state_reversal ON market_state(reversal_state, reversal_confidence DESC);
```

### 6. Trading Signals Table

```sql
CREATE TABLE trading_signals (
    signal_id BIGSERIAL PRIMARY KEY,
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    signal_timestamp TIMESTAMP NOT NULL,
    
    -- Signal details
    signal_type VARCHAR(30) NOT NULL, -- 'buy', 'sell', 'hold', 'wait'
    signal_strength DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    signal_confidence DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    
    -- Entry and exit points
    entry_price DECIMAL(10,4),
    stop_loss DECIMAL(10,4),
    target_price DECIMAL(10,4),
    risk_reward_ratio DECIMAL(6,2),
    
    -- Signal reasoning
    signal_reason TEXT NOT NULL,
    technical_indicators JSONB, -- JSON structure with supporting indicators
    
    -- Position sizing
    recommended_position_size DECIMAL(8,4), -- Percentage of portfolio
    max_risk_per_trade DECIMAL(5,4), -- Maximum risk as % of portfolio
    
    -- Validation
    is_executed BOOLEAN DEFAULT false,
    execution_timestamp TIMESTAMP,
    execution_price DECIMAL(10,4),
    
    -- Tracking
    signal_status VARCHAR(20) DEFAULT 'active', -- 'active', 'executed', 'expired', 'cancelled'
    profit_loss DECIMAL(10,4),
    return_percentage DECIMAL(8,4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_trading_signals_symbol_timestamp ON trading_signals(symbol_id, signal_timestamp DESC);
CREATE INDEX idx_trading_signals_type_strength ON trading_signals(signal_type, signal_strength DESC);
CREATE INDEX idx_trading_signals_confidence ON trading_signals(signal_confidence DESC) WHERE signal_confidence > 0.7;
CREATE INDEX idx_trading_signals_status ON trading_signals(signal_status, signal_timestamp);
CREATE INDEX idx_trading_signals_executed ON trading_signals(is_executed, signal_timestamp) WHERE is_executed = true;
```

### 7. Performance Metrics and Backtesting Table

```sql
CREATE TABLE backtest_results (
    backtest_id BIGSERIAL PRIMARY KEY,
    strategy_name VARCHAR(100) NOT NULL,
    symbol_id INTEGER REFERENCES market_symbols(symbol_id),
    
    -- Test parameters
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital DECIMAL(15,2) NOT NULL,
    commission_rate DECIMAL(5,4) DEFAULT 0.001, -- 0.1%
    
    -- Performance metrics
    final_capital DECIMAL(15,2),
    total_return DECIMAL(8,4),
    annualized_return DECIMAL(8,4),
    volatility DECIMAL(8,4),
    sharpe_ratio DECIMAL(8,4),
    max_drawdown DECIMAL(8,4),
    max_drawdown_duration INTEGER, -- Days
    
    -- Trading statistics
    total_trades INTEGER,
    winning_trades INTEGER,
    losing_trades INTEGER,
    win_rate DECIMAL(5,4),
    avg_win DECIMAL(10,4),
    avg_loss DECIMAL(10,4),
    profit_factor DECIMAL(8,4),
    
    -- Risk metrics
    value_at_risk DECIMAL(8,4), -- 95% VaR
    conditional_var DECIMAL(8,4), -- CVaR
    beta DECIMAL(8,6),
    alpha DECIMAL(8,4),
    
    -- Additional metrics
    calmar_ratio DECIMAL(8,4),
    sortino_ratio DECIMAL(8,4),
    information_ratio DECIMAL(8,4),
    
    -- Metadata
    test_config JSONB, -- Strategy parameters in JSON format
    benchmark_symbol_id INTEGER REFERENCES market_symbols(symbol_id),
    benchmark_return DECIMAL(8,4),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE INDEX idx_backtest_strategy_dates ON backtest_results(strategy_name, start_date, end_date);
CREATE INDEX idx_backtest_performance ON backtest_results(total_return DESC, sharpe_ratio DESC);
CREATE INDEX idx_backtest_symbol ON backtest_results(symbol_id) WHERE symbol_id IS NOT NULL;

-- Individual trade records from backtests
CREATE TABLE backtest_trades (
    trade_id BIGSERIAL PRIMARY KEY,
    backtest_id INTEGER NOT NULL REFERENCES backtest_results(backtest_id),
    symbol_id INTEGER NOT NULL REFERENCES market_symbols(symbol_id),
    
    -- Trade details
    entry_timestamp TIMESTAMP NOT NULL,
    exit_timestamp TIMESTAMP,
    entry_price DECIMAL(10,4) NOT NULL,
    exit_price DECIMAL(10,4),
    
    -- Position
    position_size DECIMAL(10,4) NOT NULL, -- Number of shares
    trade_type VARCHAR(10) NOT NULL, -- 'long', 'short'
    
    -- Performance
    gross_profit_loss DECIMAL(10,4),
    net_profit_loss DECIMAL(10,4), -- After commissions
    return_percentage DECIMAL(8,4),
    trade_duration_hours INTEGER,
    
    -- Signal that triggered the trade
    signal_id BIGINT REFERENCES trading_signals(signal_id),
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_backtest_trades_backtest ON backtest_trades(backtest_id);
CREATE INDEX idx_backtest_trades_symbol ON backtest_trades(symbol_id, entry_timestamp);
```

## Indexes for Optimization

### 8. Composite Indexes for Common Queries

```sql
-- Market data queries
CREATE INDEX idx_market_data_symbol_timestamp_interval 
ON market_data(symbol_id, timestamp DESC, interval_type);

CREATE INDEX idx_market_data_recent_volume 
ON market_data(symbol_id, timestamp DESC) 
INCLUDE (volume, close_price);

-- PLDot time-series analysis
CREATE INDEX idx_pldot_symbol_timestamp_value 
ON pldot_calculations(symbol_id, timestamp DESC, plpot_value)
INCLUDE (pldot_slope, pldot_momentum);

-- Envelope band analysis
CREATE INDEX idx_envelope_symbol_timestamp_bands 
ON envelope_bands(symbol_id, timestamp DESC, upper_band, lower_band)
INCLUDE (band_width, band_position);

-- Market state transitions
CREATE INDEX idx_market_state_symbol_trend_timestamp 
ON market_state(symbol_id, trend_state, timestamp DESC);

-- Signal generation and filtering
CREATE INDEX idx_trading_signals_comprehensive 
ON trading_signals(symbol_id, signal_timestamp DESC, signal_type, signal_confidence DESC)
INCLUDE (signal_strength, entry_price, stop_loss);

-- Time-based partitioning indexes (for large datasets)
CREATE INDEX idx_market_data_timestamp_partition 
ON market_data (timestamp, symbol_id) 
WHERE timestamp >= CURRENT_DATE - INTERVAL '2 years';
```

## Constraints and Relationships

### 9. Foreign Key Constraints

```sql
-- Ensure referential integrity
ALTER TABLE market_data 
ADD CONSTRAINT fk_market_data_symbol 
FOREIGN KEY (symbol_id) REFERENCES market_symbols(symbol_id);

ALTER TABLE pldot_calculations 
ADD CONSTRAINT fk_pldot_market_data 
FOREIGN KEY (data_id) REFERENCES market_data(data_id);

ALTER TABLE envelope_bands 
ADD CONSTRAINT fk_envelope_market_data 
FOREIGN KEY (data_id) REFERENCES market_data(data_id);

ALTER TABLE drummond_lines 
ADD CONSTRAINT fk_drummond_symbol 
FOREIGN KEY (symbol_id) REFERENCES market_symbols(symbol_id);

ALTER TABLE market_state 
ADD CONSTRAINT fk_market_state_symbol 
FOREIGN KEY (symbol_id) REFERENCES market_symbols(symbol_id);

ALTER TABLE trading_signals 
ADD CONSTRAINT fk_trading_signals_symbol 
FOREIGN KEY (symbol_id) REFERENCES market_symbols(symbol_id);

ALTER TABLE backtest_results 
ADD CONSTRAINT fk_backtest_symbol 
FOREIGN KEY (symbol_id) REFERENCES market_symbols(symbol_id);

ALTER TABLE backtest_trades 
ADD CONSTRAINT fk_backtest_trades_backtest 
FOREIGN KEY (backtest_id) REFERENCES backtest_results(backtest_id);
```

### 10. Business Logic Constraints

```sql
-- Ensure price relationships are logical
ALTER TABLE market_data 
ADD CONSTRAINT chk_ohlc_relationships CHECK (
    high_price >= open_price AND 
    high_price >= close_price AND
    low_price <= open_price AND 
    low_price <= close_price AND
    (high_price - low_price) >= ABS(open_price - close_price)
);

-- Ensure volume is non-negative
ALTER TABLE market_data 
ADD CONSTRAINT chk_volume_positive CHECK (volume >= 0);

-- Ensure percentages are within valid ranges
ALTER TABLE trading_signals 
ADD CONSTRAINT chk_signal_confidence CHECK (signal_confidence >= 0 AND signal_confidence <= 1);

ALTER TABLE market_state 
ADD CONSTRAINT chk_confidence_scores CHECK (
    trend_confidence >= 0 AND trend_confidence <= 1 AND
    congestion_confidence >= 0 AND congestion_confidence <= 1 AND
    reversal_confidence >= 0 AND reversal_confidence <= 1
);

-- Ensure position sizing is reasonable
ALTER TABLE trading_signals 
ADD CONSTRAINT chk_position_size CHECK (
    recommended_position_size > 0 AND recommended_position_size <= 1
);
```

## Sample Queries for Common Operations

### 11. Data Retrieval Queries

#### 11.1 Get Latest Market Data for a Symbol
```sql
SELECT 
    md.*,
    s.symbol,
    s.company_name
FROM market_data md
JOIN market_symbols s ON md.symbol_id = s.symbol_id
WHERE s.symbol = 'AAPL'
ORDER BY md.timestamp DESC
LIMIT 1;
```

#### 11.2 Get PLDot Values with Trend Analysis
```sql
WITH recent_pldot AS (
    SELECT 
        pl.*,
        LAG(pl.pldot_value) OVER (ORDER BY pl.timestamp) as prev_pldot,
        s.symbol
    FROM pldot_calculations pl
    JOIN market_symbols s ON pl.symbol_id = s.symbol_id
    WHERE s.symbol = 'MSFT'
    AND pl.timestamp >= CURRENT_DATE - INTERVAL '30 days'
)
SELECT 
    *,
    CASE 
        WHEN pldot_value > prev_pldot THEN 'Increasing'
        WHEN pldot_value < prev_pldot THEN 'Decreasing'
        ELSE 'Stable'
    END as pldot_trend
FROM recent_pldot
ORDER BY timestamp DESC;
```

#### 11.3 Market State Analysis
```sql
SELECT 
    ms.*,
    s.symbol,
    CASE 
        WHEN trend_confidence > 0.7 AND reversal_confidence > 0.6 THEN 'High Confidence Signal'
        WHEN trend_confidence > 0.5 THEN 'Moderate Confidence'
        ELSE 'Low Confidence'
    END as signal_quality
FROM market_state ms
JOIN market_symbols s ON ms.symbol_id = s.symbol_id
WHERE ms.timestamp >= CURRENT_DATE - INTERVAL '7 days'
ORDER BY ms.timestamp DESC, ms.trend_confidence DESC;
```

### 12. Signal Generation Queries

#### 12.1 Generate Buy Signals
```sql
WITH signal_analysis AS (
    SELECT 
        s.symbol_id,
        s.symbol,
        md.close_price,
        md.timestamp,
        pc.pldot_value,
        pc.pldot_momentum,
        eb.band_position,
        ms.trend_state,
        ms.reversal_state
    FROM market_symbols s
    JOIN market_data md ON s.symbol_id = md.symbol_id
    JOIN pldot_calculations pc ON md.data_id = pc.data_id
    JOIN envelope_bands eb ON md.data_id = eb.data_id
    JOIN market_state ms ON md.symbol_id = ms.symbol_id 
        AND md.timestamp = ms.timestamp
    WHERE md.timestamp >= CURRENT_DATE - INTERVAL '1 day'
    ORDER BY md.timestamp DESC
    LIMIT 1
)
INSERT INTO trading_signals (
    symbol_id, signal_timestamp, signal_type, signal_strength, 
    signal_confidence, entry_price, signal_reason
)
SELECT 
    symbol_id,
    timestamp,
    'buy',
    CASE 
        WHEN pldot_momentum > 0 AND trend_state = 'bullish' AND band_position < 0.8 THEN 0.8
        WHEN pldot_momentum > 0 AND trend_state = 'bullish' THEN 0.6
        ELSE 0.4
    END as signal_strength,
    0.75, -- Base confidence
    close_price,
    CASE 
        WHEN pldot_momentum > 0 AND trend_state = 'bullish' AND band_position < 0.8 
        THEN 'Bullish PLDot momentum with favorable band position'
        WHEN pldot_momentum > 0 AND trend_state = 'bullish'
        THEN 'Bullish PLDot momentum and trend alignment'
        ELSE 'Moderate bullish signal'
    END as signal_reason
FROM signal_analysis
WHERE NOT EXISTS (
    SELECT 1 FROM trading_signals ts 
    WHERE ts.symbol_id = signal_analysis.symbol_id 
    AND ts.signal_timestamp >= CURRENT_DATE
);
```

### 13. Performance Analysis Queries

#### 13.1 Backtest Performance Summary
```sql
SELECT 
    br.strategy_name,
    COUNT(br.backtest_id) as total_tests,
    AVG(br.total_return) as avg_return,
    AVG(br.sharpe_ratio) as avg_sharpe,
    AVG(br.max_drawdown) as avg_drawdown,
    AVG(br.win_rate) as avg_win_rate,
    SUM(br.total_trades) as total_trades
FROM backtest_results br
WHERE br.start_date >= CURRENT_DATE - INTERVAL '1 year'
GROUP BY br.strategy_name
ORDER BY avg_sharpe DESC, avg_return DESC;
```

#### 13.2 Signal Performance Tracking
```sql
SELECT 
    ts.signal_type,
    COUNT(ts.signal_id) as total_signals,
    AVG(ts.return_percentage) as avg_return,
    AVG(CASE WHEN ts.is_executed THEN ts.return_percentage END) as executed_avg_return,
    COUNT(CASE WHEN ts.is_executed THEN 1 END) as executed_count
FROM trading_signals ts
WHERE ts.signal_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY ts.signal_type
ORDER BY executed_avg_return DESC;
```

### 14. Maintenance and Cleanup Queries

#### 14.1 Data Retention Policy
```sql
-- Archive old market data (keep last 2 years)
CREATE OR REPLACE FUNCTION archive_old_data()
RETURNS void AS $$
BEGIN
    -- Move old data to archive tables or delete based on retention policy
    DELETE FROM market_data 
    WHERE timestamp < CURRENT_DATE - INTERVAL '2 years';
    
    -- Clean up orphaned calculations
    DELETE FROM pldot_calculations 
    WHERE data_id NOT IN (SELECT data_id FROM market_data);
    
    DELETE FROM envelope_bands 
    WHERE data_id NOT IN (SELECT data_id FROM market_data);
END;
$$ LANGUAGE plpgsql;
```

#### 14.2 Index Maintenance
```sql
-- Rebuild fragmented indexes
REINDEX INDEX CONCURRENTLY idx_market_data_symbol_timestamp;
REINDEX INDEX CONCURRENTLY idx_pldot_symbol_timestamp;
REINDEX INDEX CONCURRENTLY idx_trading_signals_symbol_timestamp;

-- Update table statistics
ANALYZE market_data;
ANALYZE pldot_calculations;
ANALYZE trading_signals;
ANALYZE market_state;
```

## Optimization Recommendations

### 15. Performance Optimization

#### 15.1 Partitioning Strategy
```sql
-- Partition market_data by date for better performance
CREATE TABLE market_data_partitioned (
    LIKE market_data INCLUDING ALL
) PARTITION BY RANGE (timestamp);

-- Create monthly partitions
CREATE TABLE market_data_2024_01 PARTITION OF market_data_partitioned
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

-- Create future partitions
CREATE TABLE market_data_default PARTITION OF market_data_partitioned
FOR VALUES FROM (MINVALUE) TO (MAXVALUE);
```

#### 15.2 Materialized Views for Common Aggregations
```sql
-- Daily summary view
CREATE MATERIALIZED VIEW daily_market_summary AS
SELECT 
    symbol_id,
    DATE(timestamp) as trade_date,
    MIN(open_price) as day_open,
    MAX(high_price) as day_high,
    MIN(low_price) as day_low,
    MAX(close_price) as day_close,
    SUM(volume) as day_volume,
    AVG(close_price) as avg_close
FROM market_data
GROUP BY symbol_id, DATE(timestamp);

-- Refresh daily
CREATE INDEX ON daily_market_summary (symbol_id, trade_date DESC);
```

#### 15.3 Query Optimization Tips
1. Use covering indexes with INCLUDE clause for frequently accessed columns
2. Implement partial indexes for active records only
3. Use materialized views for complex aggregations
4. Consider table partitioning for time-series data
5. Regularly vacuum and analyze tables
6. Monitor query performance and adjust indexes accordingly

### 16. Data Quality and Monitoring

#### 16.1 Data Quality Checks
```sql
CREATE OR REPLACE FUNCTION validate_market_data()
RETURNS TABLE (validation_result text) AS $$
BEGIN
    -- Check for missing OHLC data
    IF EXISTS (SELECT 1 FROM market_data WHERE open_price IS NULL OR high_price IS NULL OR low_price IS NULL OR close_price IS NULL) THEN
        RETURN QUERY SELECT 'Missing OHLC data found' as validation_result;
    END IF;
    
    -- Check for negative prices
    IF EXISTS (SELECT 1 FROM market_data WHERE open_price <= 0 OR high_price <= 0 OR low_price <= 0 OR close_price <= 0) THEN
        RETURN QUERY SELECT 'Negative or zero prices found' as validation_result;
    END IF;
    
    -- Check for unusual volume spikes
    IF EXISTS (
        SELECT 1 FROM market_data md 
        WHERE volume > (
            SELECT AVG(volume) * 10 
            FROM market_data 
            WHERE symbol_id = md.symbol_id 
            AND timestamp >= md.timestamp - INTERVAL '30 days'
        )
    ) THEN
        RETURN QUERY SELECT 'Unusual volume spikes detected' as validation_result;
    END IF;
    
    RETURN QUERY SELECT 'All data validation checks passed' as validation_result;
END;
$$ LANGUAGE plpgsql;
```

#### 16.2 Monitoring Queries
```sql
-- Monitor data freshness
SELECT 
    s.symbol,
    MAX(md.timestamp) as last_update,
    CURRENT_TIMESTAMP - MAX(md.timestamp) as data_age
FROM market_symbols s
LEFT JOIN market_data md ON s.symbol_id = md.symbol_id
WHERE s.is_active = true
GROUP BY s.symbol
ORDER BY data_age DESC;

-- Monitor signal generation performance
SELECT 
    DATE(signal_timestamp) as signal_date,
    COUNT(*) as signals_generated,
    AVG(signal_confidence) as avg_confidence,
    COUNT(CASE WHEN is_executed THEN 1 END) as executed_signals
FROM trading_signals
WHERE signal_timestamp >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(signal_timestamp)
ORDER BY signal_date DESC;
```

## Conclusion

This comprehensive PostgreSQL schema provides a robust foundation for the Drummond Geometry Analysis System, supporting:

- High-frequency market data storage and retrieval
- Advanced technical analysis calculations (PLDot, envelope bands, Drummond lines)
- Market state classification and tracking
- Signal generation and execution tracking
- Performance analysis and backtesting
- Optimized queries and indexes
- Data quality monitoring and maintenance

The schema is designed for scalability, performance, and maintainability while ensuring data integrity through comprehensive constraints and foreign key relationships.