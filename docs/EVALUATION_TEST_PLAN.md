# Evaluation Test Plan: Drummond Geometry Trading Signals

## Executive Summary

This document outlines the plan for setting up a comprehensive evaluation test of the Drummond Geometry trading signals across the Nasdaq 100 universe. The test will validate signal accuracy and strategy performance using historical data, simulating real-world trading conditions during regular market hours.

---

## Test Objectives

1. **Signal Accuracy Validation**: Evaluate how accurate the prediction engine signals are when analyzing market data as it would appear during regular market hours
2. **Strategy Performance**: Measure Drummond Geometry strategy performance across 100 Nasdaq 100 symbols
3. **Risk Management**: Validate portfolio-level risk management with 2% risk per trade
4. **Short Selling**: Test both long and short signals to evaluate bidirectional strategy performance

---

## Test Configuration

### Date Range
- **Start Date**: 2025-09-07 (3 months minus 1 day from end)
- **End Date**: 2025-11-07
- **Duration**: ~61 trading days (excluding weekends and holidays)

### Capital & Risk Parameters
- **Initial Capital**: $100,000 (shared across all symbols)
- **Risk per Trade**: 2% of portfolio ($2,000 per trade)
- **Max Concurrent Positions**: 20 (configurable)
- **Max Portfolio Risk**: 10% total (sum of all position risks)

### Trading Costs
- **Commission**: 0% (as specified)
- **Slippage**: 2 basis points (0.02%)
- **Short Selling**: Enabled

### Market Hours
- **Trading Hours**: Regular hours only (9:30 AM - 4:00 PM EST)
- **Exchange**: US (NASDAQ/NYSE)
- **Pre-market/After-hours**: Excluded

### Symbol Universe
- **Source**: `/opt/DrummondGeometry-evals/data/nasdaq100_constituents.csv`
- **Expected Symbols**: ~100 symbols
- **Data Interval**: 30-minute bars
- **Higher Timeframe (HTF)**: 1-day bars
- **Trading Timeframe**: 30-minute bars

---

## Architecture Overview

### Current System Capabilities

The system already has:
- ✅ Portfolio-level backtesting engine (`PortfolioBacktestEngine`)
- ✅ Multi-timeframe strategy implementation
- ✅ Market hours filtering
- ✅ Short selling support
- ✅ Risk management (2% per trade)
- ✅ Commission and slippage modeling
- ✅ Database persistence for results

### Required Enhancements

1. **Prediction Engine Integration**: Create a strategy that uses the `PredictionEngine`'s `SignalGenerator` instead of the current `MultiTimeframeStrategy`
2. **Date Range Update**: Update scripts to use 2025-09-07 to 2025-11-07
3. **Parallel Processing**: Optimize for multi-core execution (though portfolio engine is inherently sequential per timestamp)
4. **Signal Evaluation**: Add metrics to track signal accuracy vs actual outcomes

---

## Implementation Plan

### Phase 1: Create Prediction-Based Strategy

**Goal**: Create a new strategy that uses the PredictionEngine's SignalGenerator to generate signals, matching how signals are generated in production.

**Tasks**:
1. Create `PredictionSignalStrategy` class in `src/dgas/backtesting/strategies/prediction_signal.py`
   - Wraps `SignalGenerator` from `prediction/engine.py`
   - Converts `GeneratedSignal` objects to `Signal` objects for backtesting
   - Handles entry/exit signals (LONG, SHORT, EXIT_LONG, EXIT_SHORT)
   - Uses signal confidence and strength for filtering

2. Register strategy in `src/dgas/backtesting/strategies/registry.py`
   - Add "prediction_signal" to `STRATEGY_REGISTRY`

3. Update `PortfolioBacktestEngine` to support prediction-based strategies
   - Ensure indicator calculator can provide HTF and trading TF data
   - Verify signal conversion logic works correctly

**Files to Create/Modify**:
- `src/dgas/backtesting/strategies/prediction_signal.py` (NEW)
- `src/dgas/backtesting/strategies/registry.py` (MODIFY)
- `src/dgas/backtesting/portfolio_engine.py` (VERIFY compatibility)

**Estimated Effort**: 4-6 hours

---

### Phase 2: Update Evaluation Script

**Goal**: Create a new evaluation script with the correct parameters and date range.

**Tasks**:
1. Create `scripts/run_evaluation_backtest.py`
   - Load Nasdaq 100 symbols from CSV
   - Configure with exact parameters:
     - Date range: 2025-09-07 to 2025-11-07
     - Initial capital: $100,000
     - Risk per trade: 2%
     - Commission: 0%
     - Slippage: 2 bps
     - Short selling: Enabled
     - Regular hours only: Enabled
   - Use `PredictionSignalStrategy` instead of `MultiTimeframeStrategy`
   - Add comprehensive logging and progress tracking
   - Save results to database with metadata

2. Add data validation
   - Verify all symbols have data for the date range
   - Report missing symbols
   - Check data quality (gaps, completeness)

**Files to Create**:
- `scripts/run_evaluation_backtest.py` (NEW)

**Estimated Effort**: 2-3 hours

---

### Phase 3: Performance Optimization

**Goal**: Optimize for multi-core execution where possible.

**Current Limitation**: The portfolio engine processes all symbols sequentially at each timestamp (by design, as signals need to be ranked across the portfolio). However, we can optimize:

1. **Indicator Calculation Parallelization**
   - Current: Indicators calculated sequentially per symbol
   - Optimization: Use `ThreadPoolExecutor` with CPU count workers
   - Location: `PortfolioIndicatorCalculator` in `portfolio_engine.py`

2. **HTF Data Pre-loading**
   - Already implemented: HTF data is pre-loaded and cached
   - Verify: Ensure caching is working efficiently

3. **Database Query Optimization**
   - Already implemented: Batch queries for portfolio data loading
   - Verify: Check query performance for 100 symbols

**Files to Modify**:
- `src/dgas/backtesting/portfolio_indicator_calculator.py` (if exists)
- `src/dgas/backtesting/portfolio_engine.py` (MODIFY for parallel indicator calculation)

**Estimated Effort**: 2-3 hours

---

### Phase 4: Signal Accuracy Tracking

**Goal**: Add metrics to track signal accuracy and compare predictions to actual outcomes.

**Tasks**:
1. Extend `PortfolioBacktestResult` to include signal accuracy metrics
   - Track: signal_id, predicted_entry, predicted_exit, actual_entry, actual_exit
   - Calculate: prediction accuracy, timing accuracy, price accuracy

2. Create signal evaluation module
   - Compare `GeneratedSignal` predictions to actual trade outcomes
   - Calculate win rate by confidence bucket
   - Track false positives/negatives

3. Generate evaluation report
   - Signal accuracy by confidence level
   - Win rate by signal type (LONG vs SHORT)
   - Performance by symbol
   - Risk-adjusted returns

**Files to Create/Modify**:
- `src/dgas/backtesting/signal_evaluator.py` (NEW)
- `src/dgas/backtesting/portfolio_engine.py` (MODIFY to track signals)
- `src/dgas/backtesting/reporting.py` (MODIFY to include accuracy metrics)

**Estimated Effort**: 4-5 hours

---

### Phase 5: Testing & Validation

**Goal**: Validate the evaluation system works correctly before running the full test.

**Tasks**:
1. Create small-scale test script
   - Test with 5 symbols over 1 week
   - Verify all parameters are correct
   - Check signal generation works
   - Validate results persistence

2. Create medium-scale test script
   - Test with 20 symbols over 1 month
   - Verify performance is acceptable
   - Check memory usage
   - Validate parallel processing

3. Full test dry-run
   - Run with all 100 symbols but shorter date range (1 week)
   - Verify no errors
   - Check timing estimates

**Files to Create**:
- `scripts/test_evaluation_small.py` (NEW)
- `scripts/test_evaluation_medium.py` (NEW)

**Estimated Effort**: 2-3 hours

---

## Execution Plan

### Pre-Flight Checklist

Before running the full evaluation test:

- [ ] Verify database has data for all 100 symbols for date range 2025-09-07 to 2025-11-07
- [ ] Run data quality check (no gaps, complete coverage)
- [ ] Test prediction engine signal generation on sample symbols
- [ ] Verify market hours filtering works correctly
- [ ] Test short selling logic
- [ ] Verify commission/slippage calculations
- [ ] Check database has sufficient space for results
- [ ] Verify logging and progress tracking work

### Running the Full Test

**Estimated Runtime**: 8-15 hours (depending on CPU count and data volume)

**Command**:
```bash
# Activate virtual environment
source .venv/bin/activate

# Run in background with logging
nohup python scripts/run_evaluation_backtest.py > evaluation_backtest.log 2>&1 &

# Monitor progress
tail -f evaluation_backtest.log
```

**Expected Output**:
- Progress updates every 5% of timesteps
- Real-time equity curve updates
- Trade execution logs
- Final summary with performance metrics

### Post-Test Analysis

1. **Generate Reports**:
   - Performance summary (returns, Sharpe, max drawdown)
   - Signal accuracy report
   - Trade analysis (win rate, avg win/loss)
   - Symbol-level performance breakdown

2. **Database Queries**:
   - Query `backtest_results` table for summary
   - Query `backtest_trades` table for individual trades
   - Query `generated_signals` table (if persisted) for signal analysis

3. **Validation**:
   - Compare results to expected ranges
   - Verify all symbols were processed
   - Check for any errors or anomalies

---

## Risk Mitigation

### Potential Issues

1. **Data Availability**: Some symbols may not have complete data
   - **Mitigation**: Pre-validate data availability, skip symbols with insufficient data

2. **Memory Usage**: Processing 100 symbols simultaneously may use significant memory
   - **Mitigation**: Monitor memory usage, optimize data structures, use generators where possible

3. **Runtime**: Test may take many hours
   - **Mitigation**: Run in background, add checkpoint/resume capability (future enhancement)

4. **Signal Generation Errors**: Prediction engine may fail on some symbols
   - **Mitigation**: Add error handling, log failures, continue with remaining symbols

5. **Database Performance**: Large result sets may slow database operations
   - **Mitigation**: Use batch inserts, optimize queries, consider indexing

---

## Success Criteria

The evaluation test will be considered successful if:

1. ✅ All 100 symbols are processed without critical errors
2. ✅ Results are persisted to database correctly
3. ✅ Performance metrics are calculated accurately
4. ✅ Signal accuracy can be measured and reported
5. ✅ Test completes within expected timeframe (8-15 hours)
6. ✅ All specified parameters are correctly applied:
   - Date range: 2025-09-07 to 2025-11-07 ✓
   - Capital: $100,000 ✓
   - Risk: 2% per trade ✓
   - Commission: 0% ✓
   - Slippage: 2 bps ✓
   - Short selling: Enabled ✓
   - Regular hours only: Enabled ✓

---

## Future Enhancements

1. **Checkpoint/Resume**: Save progress periodically to allow resuming interrupted tests
2. **Distributed Processing**: Split symbols across multiple machines
3. **Real-time Monitoring**: Dashboard showing live progress and metrics
4. **Parameter Sweeps**: Test multiple parameter combinations automatically
5. **Monte Carlo Simulation**: Run multiple iterations with randomized entry timing

---

## Timeline Estimate

| Phase | Tasks | Estimated Time |
|-------|-------|----------------|
| Phase 1 | Prediction-based strategy | 4-6 hours |
| Phase 2 | Evaluation script | 2-3 hours |
| Phase 3 | Performance optimization | 2-3 hours |
| Phase 4 | Signal accuracy tracking | 4-5 hours |
| Phase 5 | Testing & validation | 2-3 hours |
| **Total** | | **14-20 hours** |

**Note**: This is development time. The actual test execution will take 8-15 hours to run.

---

## Questions for Approval

Before proceeding with implementation, please confirm:

1. ✅ **Date Range**: Use 2025-09-07 to 2025-11-07 (3 months minus 1 day)?
2. ✅ **Strategy**: Use PredictionEngine's SignalGenerator (not MultiTimeframeStrategy)?
3. ✅ **Parallel Processing**: Optimize indicator calculation for multi-core (portfolio engine remains sequential per timestamp)?
4. ✅ **Signal Tracking**: Add signal accuracy metrics to compare predictions vs actuals?
5. ✅ **Testing Approach**: Create small/medium test scripts before full run?

---

## Next Steps

Once approved:

1. Begin Phase 1: Create `PredictionSignalStrategy`
2. Update evaluation script with correct parameters
3. Test on small dataset (5 symbols, 1 week)
4. Test on medium dataset (20 symbols, 1 month)
5. Run full evaluation test (100 symbols, 3 months)
6. Generate evaluation report

---

**Document Version**: 1.0  
**Created**: 2025-01-XX  
**Status**: Awaiting Approval
