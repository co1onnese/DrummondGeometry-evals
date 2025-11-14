# Backtest Plan: Nov 6 - Nov 13, 2025
## 1-Week Portfolio Backtest with $100,000 Initial Capital

---

## Executive Summary

This plan outlines the setup for a 1-week backtest (November 6-13, 2025) that will:
- Use historical data to generate predictions via the PredictionEngine's SignalGenerator
- Simulate trading a $100,000 portfolio using the PortfolioBacktestEngine
- Track signal accuracy using the built-in SignalEvaluator
- Generate comprehensive performance metrics and evaluation reports
- Write all results to a file for analysis

---

## 1. Objectives

### Primary Goals
1. **Validate Signal Generation**: Test the PredictionEngine's SignalGenerator accuracy over a 1-week period
2. **Portfolio Performance**: Measure portfolio returns, Sharpe ratio, max drawdown, and other key metrics
3. **Signal Evaluation**: Track predicted signals vs actual trade outcomes to measure signal accuracy
4. **Risk Management**: Validate position sizing, stop-loss execution, and portfolio risk controls
5. **Data Validation**: Ensure all required data exists before running backtest

### Success Criteria
- Data validation confirms all 518 symbols have complete data for Nov 6-13
- Backtest completes successfully with all symbols processed
- Signal accuracy metrics are calculated and reported
- Performance metrics are generated and saved to database
- All results written to file for analysis

---

## 2. Configuration Parameters

### Date Range
- **Start Date**: November 6, 2025 (Thursday) - First trading day of the week
- **End Date**: November 13, 2025 (Thursday) - End of 1-week period
- **Note**: Nov 11 (Veterans Day) is a market holiday - system should handle this automatically

### Trading Parameters
- **Initial Capital**: $100,000
- **Risk per Trade**: 2% of portfolio ($2,000 per trade)
- **Max Positions**: 20 concurrent positions
- **Max Portfolio Risk**: 10% total risk across all positions
- **Commission Rate**: 0% (for clean signal evaluation)
- **Slippage**: 2 basis points (0.02%)
- **Short Selling**: Enabled
- **Trading Hours**: Regular hours only (9:30 AM - 4:00 PM EST)

### Timeframe Configuration
- **Higher Timeframe (HTF)**: 1d (daily bars for trend analysis)
- **Trading Timeframe**: 30m (30-minute bars for entry/exit signals)
- **Data Interval**: 30m (primary trading interval)

### Strategy Configuration
- **Strategy**: `PredictionSignalStrategy` (uses PredictionEngine.SignalGenerator)
- **Min Alignment Score**: 0.6 (timeframe alignment threshold)
- **Min Signal Strength**: 0.5 (minimum signal strength to execute)
- **Stop Loss ATR Multiplier**: 1.5
- **Target R:R Ratio**: 2.0
- **Min Zone Weight**: 2.5 (confluence zone strength)
- **Required Pattern Strength**: 2

### Symbol Universe
- **Source**: All active symbols from database (`market_symbols` table where `is_active = true`)
- **Expected Symbols**: 518 symbols (all active symbols in database)
- **Filtering**: Only symbols with sufficient historical data for the timeframe (validated before backtest)

---

## 3. Data Requirements

### Historical Data Needs
1. **30-minute bars** for all symbols from:
   - **Minimum**: Nov 1, 2025 (to ensure sufficient lookback for indicators)
   - **Maximum**: Nov 13, 2025 (end of backtest period)
   - **Reason**: Need historical bars for indicator calculation (PLdot, envelopes, states, patterns)

2. **Daily bars** for all symbols from:
   - **Minimum**: Oct 1, 2025 (for HTF trend analysis)
   - **Maximum**: Nov 13, 2025
   - **Reason**: Higher timeframe analysis requires daily bars

### Data Verification Steps
1. **Check Data Availability** (using `check_data_gaps.py` logic):
   - Load all 518 active symbols from database
   - Verify all symbols have 30m data for Nov 6-13
   - Verify all symbols have 1d data for sufficient lookback period (Oct 1 - Nov 13)
   - Identify and log any symbols with missing data
   - Report symbols that are up-to-date, stale, or have no data

2. **Data Quality Checks**:
   - Ensure no gaps in data (especially around Nov 11 holiday)
   - Verify timestamps are in UTC and properly formatted
   - Check for duplicate bars
   - Validate minimum bar count (need > 10 bars for indicator calculation)

3. **Pre-Backtest Data Backfill** (if needed):
   - If gaps found, report which symbols need backfill
   - User can run backfill scripts before proceeding
   - Re-verify after backfill completes

---

## 4. Implementation Plan

### Phase 1: Data Validation
**File**: `scripts/run_nov6_nov13_backtest.py` (includes validation)

**Tasks**:
1. Load all 518 active symbols from database (`SELECT symbol FROM market_symbols WHERE is_active = true`)
2. Verify data availability for Nov 6-13 timeframe using `check_data_gaps.py` logic
3. Check for data gaps and missing symbols
4. Validate both 30m and 1d intervals
5. Generate data availability report
6. Exit with error if insufficient data (need at least 10 symbols with complete data)

**Outputs**:
- List of symbols with complete data
- List of symbols with missing data
- Data quality report printed to console

### Phase 2: Backtest Script Creation
**File**: `scripts/run_nov6_nov13_backtest.py` (new script)

**Based on**: `scripts/run_evaluation_backtest.py` (existing template)

**Key Components**:
1. **Cleanup Existing Evaluations**:
   - Remove old evaluation backtest results from database
   - Delete backtest_results and backtest_trades for symbol "SP500_EVAL" or similar
   - Ensure clean state before new backtest

2. **Configuration Section**:
   - Date range: Nov 6 - Nov 13, 2025
   - Initial capital: $100,000
   - Regular hours only: **True** (enabled)
   - All trading parameters as specified above

3. **Data Loading**:
   - Load all 518 active symbols from database
   - Verify data availability using `check_data_gaps.py` logic
   - Filter to symbols with complete data for both 30m and 1d intervals

4. **Portfolio Configuration**:
   - Create `PortfolioBacktestConfig` with all parameters
   - Set `regular_hours_only=True`
   - Set up `PredictionSignalStrategy` with proper config
   - Initialize `PortfolioBacktestEngine`

5. **Execution**:
   - Run portfolio backtest via `engine.run()`
   - Process all timesteps bar-by-bar
   - Track progress with periodic updates

6. **Results Processing**:
   - Calculate performance metrics
   - Generate signal accuracy metrics via `SignalEvaluator` (already in metadata)
   - Save results to database with symbol "EVAL_NOV6"
   - Print comprehensive summary report
   - **Write all results to file** (Markdown format with full details)

7. **Error Handling**:
   - Handle keyboard interrupts gracefully
   - Log errors with full traceback
   - Save partial results if backtest fails

### Phase 3: Results Reporting (Integrated)
**File**: `scripts/run_nov6_nov13_backtest.py` (includes reporting)

**Tasks**:
1. Extract all metrics from backtest result:
   - Portfolio performance metrics (returns, Sharpe, drawdown, etc.)
   - Signal accuracy metrics from metadata (win rate, confidence analysis, etc.)
   - Trade statistics (win rate, avg win/loss, profit factor)
   - Symbol count and data summary

2. Generate comprehensive report file:
   - Markdown format with full details
   - Include all performance metrics
   - Include all signal accuracy metrics
   - Include trade summary
   - Include configuration parameters

3. Write to file:
   - `reports/nov6_nov13_backtest_results.md` - Complete results report

---

## 5. Technical Implementation Details

### Key Classes and Modules

1. **PortfolioBacktestEngine** (`src/dgas/backtesting/portfolio_engine.py`)
   - Main orchestration engine
   - Manages multi-symbol backtesting with shared capital
   - Coordinates signal generation, ranking, and execution

2. **PredictionSignalStrategy** (`src/dgas/backtesting/strategies/prediction_signal.py`)
   - Uses `SignalGenerator` from `PredictionEngine`
   - Converts `GeneratedSignal` objects to backtesting `Signal` objects
   - Ensures backtest uses same signal logic as production

3. **SignalEvaluator** (`src/dgas/backtesting/signal_evaluator.py`)
   - Tracks predicted signals vs actual trade outcomes
   - Calculates win rate, confidence analysis, signal accuracy metrics
   - Already integrated into `PortfolioBacktestEngine`

4. **PortfolioIndicatorCalculator** (`src/dgas/backtesting/portfolio_indicator_calculator.py`)
   - Calculates indicators on-the-fly during backtest
   - Pre-loads HTF data for all symbols
   - Provides `TimeframeData` objects to strategy

5. **PortfolioPositionManager** (`src/dgas/backtesting/portfolio_position_manager.py`)
   - Manages positions across multiple symbols
   - Handles position sizing based on risk
   - Tracks portfolio equity and available capital

### Signal Generation Flow

1. **For each timestep** (30-minute bar):
   - `PortfolioBacktestEngine._process_timestep()` is called
   - For each symbol, `PortfolioIndicatorCalculator` calculates indicators
   - `PredictionSignalStrategy.on_bar()` is called with `StrategyContext`
   - Strategy calls `SignalGenerator.generate_signals()` with HTF and trading TF data
   - `SignalGenerator` uses `MultiTimeframeCoordinator` to analyze alignment
   - Generated signals are converted to backtesting `Signal` objects
   - Signals are registered with `SignalEvaluator` for tracking

2. **Signal Execution**:
   - `PortfolioBacktestEngine._generate_entry_signals()` ranks all signals
   - Top signals are selected based on ranking criteria
   - `PortfolioPositionManager` calculates position sizes
   - Positions are opened with stop-loss and target prices

3. **Exit Management**:
   - `PortfolioBacktestEngine._check_exits()` monitors all positions
   - Exits are triggered when stop-loss or target is hit
   - Completed trades are registered with `SignalEvaluator`
   - Signal accuracy is calculated by comparing predictions to outcomes

### Database Persistence

1. **Backtest Results**:
   - Saved via `persist_backtest()` in `src/dgas/backtesting/persistence.py`
   - Stored in `backtest_results` table with synthetic symbol "EVAL_NOV6"
   - Includes all performance metrics

2. **Trades**:
   - Saved to `backtest_trades` table
   - Links to backtest result via foreign key
   - Includes entry/exit prices, P&L, timestamps

3. **Metadata**:
   - Test type: "evaluation"
   - Date range: Nov 6-13, 2025
   - Symbol count, configuration parameters
   - Signal generator: "PredictionEngine.SignalGenerator"

---

## 6. Expected Outputs

### Performance Metrics
- **Total Return**: Percentage gain/loss over the week
- **Sharpe Ratio**: Risk-adjusted return metric
- **Sortino Ratio**: Downside risk-adjusted return
- **Max Drawdown**: Largest peak-to-trough decline
- **Win Rate**: Percentage of profitable trades
- **Profit Factor**: Gross profit / gross loss
- **Average Win/Loss**: Average profit per winning/losing trade

### Signal Accuracy Metrics
- **Total Signals Generated**: Count of all signals from SignalGenerator
- **Executed Signals**: Signals that resulted in trades
- **Win Rate**: Percentage of executed signals that were profitable
- **Confidence Analysis**: Win rate by confidence bucket (0-50%, 50-70%, 70-85%, 85-100%)
- **Signal Type Breakdown**: Win rate for LONG vs SHORT signals
- **Average Confidence**: For winning vs losing signals

### Trade Statistics
- **Total Trades**: Number of completed trades
- **Winning Trades**: Count and average profit
- **Losing Trades**: Count and average loss
- **Trade Duration**: Average holding period
- **Symbol Distribution**: Trades per symbol

---

## 7. Execution Timeline

### Estimated Duration
- **Data Verification**: 5-10 minutes
- **Backtest Execution**: 30-60 minutes (depending on symbol count and data volume)
- **Results Analysis**: 5-10 minutes
- **Total**: ~1-1.5 hours

### Progress Tracking
- Progress updates every 5% of timesteps processed
- Real-time trade count and equity updates
- Estimated time remaining (if possible)

---

## 8. Validation and Quality Assurance

### Pre-Execution Checks
1. ✅ Database connection is working
2. ✅ All required symbols have data for the timeframe
3. ✅ Configuration parameters are correct
4. ✅ Strategy is properly initialized
5. ✅ SignalGenerator can generate signals (test with sample data)

### During Execution
1. Monitor for errors or exceptions
2. Verify signals are being generated
3. Check that trades are being executed
4. Ensure equity curve is updating correctly

### Post-Execution Validation
1. Verify results were saved to database
2. Check that all expected metrics are present
3. Validate signal accuracy calculations
4. Compare results to expected ranges (if available)

---

## 9. Risk Considerations

### Data Risks
- **Missing Data**: Some symbols may not have complete data for Nov 6-13
  - **Mitigation**: Filter to symbols with complete data, log missing symbols
- **Data Quality**: Gaps or errors in historical data
  - **Mitigation**: Data quality checks before backtest, handle missing bars gracefully

### Execution Risks
- **Long Runtime**: Backtest may take 30-60 minutes
  - **Mitigation**: Progress updates, ability to resume from checkpoint (if implemented)
- **Memory Usage**: Large symbol universe may consume significant memory
  - **Mitigation**: System already has memory management in place

### Results Interpretation
- **Short Timeframe**: 1 week may not be statistically significant
  - **Note**: This is intentional for focused evaluation
- **Market Conditions**: Nov 6-13 may have specific market conditions
  - **Note**: Results should be interpreted in context

---

## 10. Files to Create/Modify

### New Files
1. `scripts/run_nov6_nov13_backtest.py` - Main backtest execution script (includes validation, execution, and reporting)

### Modified Files
- None (all functionality exists in existing codebase)

### Output Files (Generated)
1. `reports/nov6_nov13_backtest_results.md` - Complete results report with all metrics

---

## 11. Dependencies

### Required Data
- All 518 active symbols from database (`market_symbols` table)
- Historical 30m bars for Nov 1-13, 2025 (for all symbols)
- Historical 1d bars for Oct 1 - Nov 13, 2025 (for all symbols)

### Required Code
- All existing backtesting infrastructure (already in place)
- PortfolioBacktestEngine
- PredictionSignalStrategy
- SignalEvaluator
- Database persistence layer

### External Dependencies
- PostgreSQL database with market data
- Python 3.11+
- All project dependencies (already installed)

---

## 12. Success Metrics

### Technical Success
- ✅ Backtest completes without errors
- ✅ All symbols processed successfully
- ✅ Results saved to database
- ✅ Signal accuracy metrics calculated

### Business Success
- Signal accuracy metrics provide actionable insights
- Performance metrics are within expected ranges
- Results can be compared to other evaluation periods
- Reports are clear and comprehensive

---

## 13. Implementation Details

### Data Validation Function
Reuse logic from `check_data_gaps.py`:
- Query all active symbols from database
- Check latest timestamp for each symbol
- Verify data exists for Nov 6-13 date range
- Report symbols with missing or incomplete data

### Symbol Loading Function
```python
def get_all_active_symbols() -> list[str]:
    """Get all active symbols from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]
```

### Cleanup Function
```python
def cleanup_old_evaluations() -> None:
    """Remove old evaluation backtest results from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Find old evaluation backtest IDs
            cur.execute("""
                SELECT backtest_id FROM backtest_results 
                WHERE symbol IN ('SP500_EVAL', 'EVAL_NOV6', 'SP500_EVAL_NOV6')
            """)
            old_ids = [row[0] for row in cur.fetchall()]
            
            if old_ids:
                # Delete trades first (foreign key constraint)
                cur.execute("""
                    DELETE FROM backtest_trades 
                    WHERE backtest_id = ANY(%s)
                """, (old_ids,))
                
                # Delete backtest results
                cur.execute("""
                    DELETE FROM backtest_results 
                    WHERE backtest_id = ANY(%s)
                """, (old_ids,))
                
                conn.commit()
                print(f"✓ Cleaned up {len(old_ids)} old evaluation backtests")
```

### Results File Writing
Write comprehensive Markdown report including:
- Configuration summary
- Data validation results
- Portfolio performance metrics
- Signal accuracy metrics (from metadata)
- Trade statistics
- Symbol count and data summary

---

## 14. Next Steps After Approval

Once this plan is approved, the implementation will proceed as follows:

1. **Create TODO list** with specific tasks
2. **Implement main backtest script** (`run_nov6_nov13_backtest.py`) with:
   - Cleanup function for old evaluations
   - Data validation using `check_data_gaps.py` logic
   - Symbol loading from database (all 518 active symbols)
   - Backtest execution with regular hours only
   - Results saving to database with "EVAL_NOV6" symbol
   - Comprehensive results file writing
3. **Test with small symbol subset** (10-20 symbols) first
4. **Run full backtest** with all 518 symbols
5. **Validate results** and verify file output
6. **Document findings** and any issues encountered

---

## Conclusion

This plan provides a comprehensive strategy for setting up a 1-week backtest for Nov 6-13, 2025. The implementation leverages existing, well-tested infrastructure and follows the same patterns as the existing evaluation backtest. Key changes:

- **Data validation**: Reuses `check_data_gaps.py` logic to verify all 518 symbols have complete data
- **Symbol loading**: Loads all active symbols from database (not CSV)
- **Regular hours**: Enabled for realistic trading simulation
- **Cleanup**: Removes old evaluation results before new backtest
- **Reporting**: Writes comprehensive results to file (no separate analysis script needed)
- **Symbol name**: Uses "EVAL_NOV6" (shorter, fits database constraints)

All required functionality already exists in the codebase - we just need to create the orchestration script with the correct configuration parameters for this specific timeframe.
