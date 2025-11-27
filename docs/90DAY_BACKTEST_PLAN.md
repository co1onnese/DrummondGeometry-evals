# 90-Day Backtest Plan - November 26, 2025

## Overview

This document outlines the plan to backfill market data and run a 90-day backtest using the new signal generation logic, ending on Wednesday, November 26, 2025.

## Date Calculations

### Backtest Period
- **End Date**: Wednesday, November 26, 2025 (end of trading day)
- **Backtest Duration**: 90 days
- **Start Date**: August 28, 2025 (90 days before Nov 26)

### Data Requirements
- **Total Data Needed**: 180 days
  - 90 days for the backtest period (Aug 28 - Nov 26, 2025)
  - 90 days of historical lookback data (June 1 - Aug 27, 2025)
- **Data Start Date**: June 1, 2025
- **Data End Date**: November 26, 2025

### Intervals Required
1. **5m (Trading Interval)**: June 1, 2025 to Nov 26, 2025
   - Used for actual trading signals and execution
   - Required for all active symbols

2. **1d (Higher Timeframe)**: June 1, 2025 to Nov 26, 2025
   - Used for HTF trend analysis
   - Required for all active symbols

## Backfill Strategy

### Data Overwrite Behavior
The `bulk_upsert_market_data` function uses PostgreSQL's `ON CONFLICT DO UPDATE` clause, which means:
- Existing data will be **overwritten** with new data
- This is appropriate since the backfill logic has been updated
- No need to delete existing data first

### Backfill Process

1. **Get Active Symbols**
   - Query database for all symbols where `is_active = true`
   - Use these symbols for backfill

2. **Backfill 5m Data**
   - Date range: 2025-06-01 to 2025-11-26
   - Use `backfill_intraday()` function
   - Process in batches (50 symbols per batch)
   - Rate limiting: 45 seconds delay between batches
   - Use historical endpoint (not live data)

3. **Backfill 1d Data**
   - Date range: 2025-06-01 to 2025-11-26
   - Use `backfill_eod()` function
   - Process in batches (50 symbols per batch)
   - Rate limiting: 45 seconds delay between batches

4. **Progress Tracking**
   - Track successful/failed symbols
   - Report bars fetched vs stored
   - Handle errors gracefully

### Estimated Time
- **5m Data**: ~2-3 hours (assuming ~500 symbols, 50 per batch, 45s delay)
- **1d Data**: ~30-45 minutes (fewer bars per symbol)
- **Total**: ~3-4 hours

## Backtest Configuration

### Updated Parameters
- **Duration**: 90 days (was 30 days)
- **Start Date**: August 28, 2025
- **End Date**: November 26, 2025
- **Trading Interval**: 5m
- **HTF Interval**: 1d
- **Strategy**: PredictionSignalStrategy (uses new SignalGenerator)

### Signal Generation Logic
The backtest uses `PredictionSignalStrategy` which:
- Uses `SignalGenerator` from `PredictionEngine`
- Implements tiered signal system (HIGH/MEDIUM/LOW)
- Supports termination pattern detection
- Includes exhaust-based exit signals
- Uses updated congestion state tracking

### Portfolio Configuration
- **Initial Capital**: $100,000
- **Risk per Trade**: 2%
- **Max Positions**: 20 concurrent positions
- **Max Portfolio Risk**: 10%
- **Commission**: 0.1%
- **Slippage**: 2 basis points
- **Short Selling**: Enabled

## Implementation Steps

### Step 1: Create Backfill Script
Create `scripts/backfill_90day_nov26.py`:
- Load all active symbols
- Backfill 5m data (June 1 - Nov 26, 2025)
- Backfill 1d data (June 1 - Nov 26, 2025)
- Report progress and statistics

### Step 2: Update Backtest Script
Update `scripts/run_30day_backtest.py`:
- Rename to `run_90day_backtest.py` (or keep name, update internally)
- Change date range to Aug 28 - Nov 26, 2025
- Update metadata to reflect 90-day backtest
- Ensure it uses PredictionSignalStrategy (already does)

### Step 3: Verify Data Availability
Before running backtest:
- Check data coverage for all symbols
- Verify minimum bar requirements (at least 100 5m bars per symbol)
- Report symbols with insufficient data

### Step 4: Run Backtest
Execute the updated backtest script:
- Monitor progress
- Save results to database
- Generate summary report

## Verification Checklist

- [ ] Backfill script created and tested
- [ ] 5m data backfilled for all active symbols (June 1 - Nov 26, 2025)
- [ ] 1d data backfilled for all active symbols (June 1 - Nov 26, 2025)
- [ ] Data quality verified (no major gaps)
- [ ] Backtest script updated with correct dates
- [ ] Backtest runs successfully
- [ ] Results saved to database
- [ ] Summary report generated

## Notes

- The backfill will overwrite existing data, which is desired since the backfill logic has been updated
- Use `use_live_for_today=False` in backfill to ensure we only use historical data
- The backtest uses the same signal generation logic as production (via PredictionSignalStrategy)
- All Python code runs under `uv` as specified
