# Backtesting Critical Fixes - Remediation Plan

**Date:** 2025-01-XX  
**Focus:** Fix critical stop-loss/take-profit intraday checking issues  
**Scope:** Only Priority 1 Critical Fixes from realistic simulation review

---

## Executive Summary

This plan addresses **3 critical issues** that cause unrealistic backtest results:

1. **Stop-loss/take-profit only checked at bar.close** (not intraday)
2. **Position entity missing stop-loss/take-profit fields** (single-symbol engine)
3. **Single-symbol engine doesn't check stop-loss at all**

**Expected Impact:**
- Stop-losses will trigger when price touches level intraday (not just at close)
- More realistic and conservative backtest results
- Better risk estimation

---

## Data Availability Check

✅ **Confirmed Available:**
- `IntervalData` model has `high` and `low` fields
- Database `market_data` table has `high_price` and `low_price` columns
- Portfolio engine already stores `stop_loss`/`target` in `PortfolioPosition`
- Strategy generates stop-loss in signal metadata (`trail_stop`)

⚠️ **Missing/Needs Verification:**
- ❌ Strategy calculates `target_price` but **does NOT store it in metadata** (needs fix)
- Need to verify single-symbol engine extracts stop-loss from metadata

**Action:** Add `take_profit` to strategy metadata as prerequisite task.

---

## Critical Issue 1: Add Stop-Loss/Take-Profit to Position Entity

### Problem
- `Position` entity doesn't store `stop_loss`/`take_profit`
- Single-symbol engine can't check stops independently
- Currently relies on strategy signals or metadata dict (not type-safe)

### Solution
Add `stop_loss` and `take_profit` fields to `Position` dataclass.

### Tasks

**Task 1.1: Extend Position Entity**
- **File:** `src/dgas/backtesting/entities.py`
- **Change:** Add `stop_loss: Decimal | None = None` and `take_profit: Decimal | None = None` to `Position` class
- **Impact:** Breaking change - all Position creation sites need update
- **Effort:** 30 minutes
- **Dependencies:** None

**Task 1.2: Update Position Creation Sites**
- **Files:** 
  - `src/dgas/backtesting/engine.py` (`_enter_position`)
  - `src/dgas/backtesting/execution/trade_executor.py` (`open_position`)
- **Change:** Extract `stop_loss`/`take_profit` from signal metadata when creating Position
- **Effort:** 1 hour
- **Dependencies:** Task 1.1

**Task 1.3: Update Tests**
- **Files:** All test files that create `Position` objects
- **Change:** Update Position creation to include optional stop_loss/take_profit
- **Effort:** 1 hour
- **Dependencies:** Task 1.1

---

## Critical Issue 2: Fix Portfolio Engine Intraday Stop-Loss Checking

### Problem
- `PortfolioBacktestEngine._check_exits()` only uses `bar.close`
- Should check `bar.high`/`bar.low` to detect intraday touches
- Exit price should be stop-loss/target when hit, not always bar.close

### Solution
1. Use `bar.high`/`bar.low` for stop-loss/target checking
2. Determine appropriate exit price when level hit
3. Apply slippage to exit price

### Tasks

**Task 2.1: Fix Intraday Price Checking**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** Update `_check_exits()` to use `bar.high`/`bar.low` instead of `bar.close`
- **Logic:**
  - LONG stop-loss: Check if `bar.low <= stop_loss`
  - LONG take-profit: Check if `bar.high >= take_profit`
  - SHORT stop-loss: Check if `bar.high >= stop_loss`
  - SHORT take-profit: Check if `bar.low <= take_profit`
- **Effort:** 1 hour
- **Dependencies:** None

**Task 2.2: Fix Exit Price Determination**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** When stop-loss/target hit, exit at the level price (with slippage), not bar.close
- **Logic:**
  - If stop-loss hit: exit_price = stop_loss (with slippage applied)
  - If take-profit hit: exit_price = take_profit (with slippage applied)
  - Otherwise: exit_price = bar.close (with slippage applied)
- **Effort:** 1 hour
- **Dependencies:** Task 2.1

**Task 2.3: Update Tests**
- **File:** `tests/backtesting/test_portfolio_engine.py` (if exists) or create new tests
- **Change:** Add tests for intraday stop-loss/take-profit triggering
- **Test Cases:**
  - Stop-loss hit intraday but close above/below
  - Take-profit hit intraday but close below/above
  - Both hit in same bar (stop-loss takes precedence)
- **Effort:** 2 hours
- **Dependencies:** Task 2.1, Task 2.2

---

## Critical Issue 3: Add Stop-Loss Checking to Single-Symbol Engine

### Problem
- `SimulationEngine` doesn't check stop-loss/take-profit at all
- Relies entirely on strategy signals
- Strategy checks trailing stops but only at bar.close

### Solution
1. Check stop-loss/take-profit before strategy signal generation
2. Use intraday prices (`bar.high`/`bar.low`)
3. Generate exit signal if level touched

### Tasks

**Task 3.1: Add Stop-Loss/Take-Profit Check Method**
- **File:** `src/dgas/backtesting/engine.py`
- **Change:** Create `_check_stop_loss_take_profit()` method
- **Logic:**
  - Check if `bar.low <= stop_loss` for LONG positions
  - Check if `bar.high >= stop_loss` for SHORT positions
  - Check if `bar.high >= take_profit` for LONG positions
  - Check if `bar.low <= take_profit` for SHORT positions
  - Return exit Signal if level touched
- **Effort:** 1 hour
- **Dependencies:** Task 1.1 (Position needs stop_loss/take_profit fields)

**Task 3.2: Integrate Check into Main Loop**
- **File:** `src/dgas/backtesting/engine.py`
- **Change:** Call `_check_stop_loss_take_profit()` before strategy signal generation
- **Location:** In `run()` method, after executing pending signals, before strategy `on_bar()`
- **Logic:**
  - If stop-loss/take-profit hit, execute exit signal immediately
  - Skip strategy signal generation for this bar (already exited)
- **Effort:** 1 hour
- **Dependencies:** Task 3.1

**Task 3.3: Fix Exit Price Determination**
- **File:** `src/dgas/backtesting/engine.py`
- **Change:** When stop-loss/take-profit hit, exit at level price (with slippage)
- **Location:** In `_close_position()` or new helper method
- **Logic:** Similar to portfolio engine - use stop-loss/target price when hit
- **Effort:** 1 hour
- **Dependencies:** Task 3.1, Task 3.2

**Task 3.4: Extract Stop-Loss/Take-Profit from Signal Metadata**
- **File:** `src/dgas/backtesting/engine.py`
- **Change:** In `_enter_position()`, extract `stop_loss`/`take_profit` from signal metadata
- **Metadata Keys:** Check for `trail_stop`, `stop_loss`, `take_profit`, `target`
- **Store:** Pass to `executor.open_position()` or set on Position after creation
- **Effort:** 1 hour
- **Dependencies:** Task 1.2

**Task 3.5: Update Tests**
- **File:** `tests/backtesting/test_engine.py` (if exists) or create new tests
- **Change:** Add tests for stop-loss/take-profit checking
- **Test Cases:**
  - Stop-loss hit intraday triggers exit
  - Take-profit hit intraday triggers exit
  - Stop-loss not hit when price doesn't touch level
  - Exit price is stop-loss/target when hit
- **Effort:** 2 hours
- **Dependencies:** All Task 3 subtasks

---

## Critical Issue 4: Fix Strategy Trailing Stop Checking

### Problem
- `MultiTimeframeStrategy._manage_open_position()` checks trailing stops only at `bar.close`
- Should check `bar.high`/`bar.low` for intraday touches

### Solution
Update strategy to use `bar.high`/`bar.low` when checking trailing stops.

### Tasks

**Task 4.1: Fix Trailing Stop Check**
- **File:** `src/dgas/backtesting/strategies/multi_timeframe.py`
- **Change:** In `_manage_open_position()`, use `context.bar.low`/`context.bar.high` instead of `last_close`
- **Logic:**
  - LONG trailing stop: Check if `bar.low <= trail_price`
  - SHORT trailing stop: Check if `bar.high >= trail_price`
- **Effort:** 30 minutes
- **Dependencies:** None

**Task 4.2: Update Tests**
- **File:** `tests/backtesting/test_strategies.py` (if exists)
- **Change:** Add tests for intraday trailing stop checks
- **Effort:** 1 hour
- **Dependencies:** Task 4.1

---

## Implementation Order

### Phase 1: Foundation (Day 1)
1. ✅ Task 1.1: Extend Position Entity
2. ✅ Task 1.2: Update Position Creation Sites
3. ✅ Task 3.4: Extract Stop-Loss/Take-Profit from Signal Metadata

**Verification:** Position objects created with stop_loss/take_profit populated

### Phase 2: Single-Symbol Engine (Day 1-2)
4. ✅ Task 3.1: Add Stop-Loss/Take-Profit Check Method
5. ✅ Task 3.2: Integrate Check into Main Loop
6. ✅ Task 3.3: Fix Exit Price Determination

**Verification:** Single-symbol backtest triggers stops intraday

### Phase 3: Portfolio Engine (Day 2)
7. ✅ Task 2.1: Fix Intraday Price Checking
8. ✅ Task 2.2: Fix Exit Price Determination

**Verification:** Portfolio backtest triggers stops intraday

### Phase 4: Strategy Fix (Day 2)
9. ✅ Task 4.1: Fix Trailing Stop Check

**Verification:** Strategy trailing stops work intraday

### Phase 5: Testing (Day 2-3)
10. ✅ Task 1.3: Update Tests
11. ✅ Task 2.3: Update Portfolio Engine Tests
12. ✅ Task 3.5: Update Single-Symbol Engine Tests
13. ✅ Task 4.2: Update Strategy Tests

**Verification:** All tests pass, no regressions

---

## Testing Strategy

### Unit Tests
- Test stop-loss hit intraday (bar.low <= stop_loss for LONG)
- Test take-profit hit intraday (bar.high >= take_profit for LONG)
- Test stop-loss NOT hit when price doesn't touch level
- Test exit price is stop-loss/target when hit
- Test both stop-loss and take-profit in same bar (stop-loss takes precedence)

### Integration Tests
- Run single-symbol backtest with stop-loss
- Run portfolio backtest with stop-loss
- Compare results before/after fix (should be more conservative)

### Validation Tests
- Verify stop-loss triggers when price touches level intraday
- Verify exit prices are realistic (stop-loss price, not bar.close)
- Verify no regressions in existing functionality

---

## Risk Assessment

### Low Risk
- Adding fields to Position (backward compatible with defaults)
- Fixing portfolio engine (isolated change)

### Medium Risk
- Single-symbol engine changes (core logic)
- Exit price determination (affects P&L calculation)

### Mitigation
- Comprehensive testing before merge
- Run existing backtests to verify no regressions
- Compare results before/after (should be more conservative)

---

## Success Criteria

✅ **Must Have:**
1. Stop-loss triggers when `bar.low <= stop_loss` (LONG) or `bar.high >= stop_loss` (SHORT)
2. Take-profit triggers when `bar.high >= take_profit` (LONG) or `bar.low <= take_profit` (SHORT)
3. Exit price is stop-loss/target when level hit (with slippage)
4. Both single-symbol and portfolio engines work correctly
5. All existing tests pass (no regressions)

✅ **Should Have:**
6. Strategy trailing stops use intraday prices
7. Comprehensive test coverage for new functionality

---

## Estimated Effort

**Total:** ~15-18 hours

**Breakdown:**
- Prerequisite: 0.1 hours (5 minutes)
- Foundation: 2.5 hours
- Single-symbol engine: 4 hours
- Portfolio engine: 2 hours
- Strategy fix: 1.5 hours
- Testing: 5-8 hours

**Timeline:** 2-3 days

---

## Dependencies & Prerequisites

### Code Dependencies
- `IntervalData` model (has `high`/`low`) ✅
- `BaseTradeExecutor` for slippage ✅
- Signal metadata structure ✅

### Data Dependencies
- Database has `high_price`/`low_price` ✅
- Historical data available for testing ✅

### Missing Items (Will Fix)
- ✅ Strategy calculates `take_profit` but doesn't store in metadata → **Task P.1 fixes this**
- ⚠️ Test data with stop-loss scenarios (may need to create test cases)

---

## Rollback Plan

If issues arise:
1. Revert commits using `git revert`
2. No database migrations needed (no schema changes)
3. No external dependencies

---

## Next Steps

1. **Review this plan** - Confirm scope and approach
2. **Verify data availability** - Check strategy metadata for take_profit
3. **Begin Phase 1** - Extend Position entity
4. **Test incrementally** - After each phase
5. **Validate results** - Compare before/after backtest results

---

**End of Plan**
