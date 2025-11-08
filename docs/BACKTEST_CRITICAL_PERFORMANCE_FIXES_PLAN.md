# Backtesting Critical Performance Fixes - Remediation Plan

**Date:** 2025-01-XX  
**Focus:** Fix Priority 1 Critical Performance Issues  
**Scope:** Equity curve sampling, HTF binary search, equity caching, batch confluence zones, equity bug fix, thread pool optimization

---

## Executive Summary

This plan addresses **5 critical performance issues** and **1 critical bug** that significantly impact backtesting performance and correctness:

1. **Equity curve storage inefficiency** - Store snapshots for every bar
2. **HTF bars filtering inefficiency** - Linear scan O(n) every time
3. **Redundant equity calculations** - Recalculated 500+ times per timestep
4. **N+1 query pattern** - Confluence zones loaded one query per timestamp
5. **Critical bug:** Equity calculation uses entry_price instead of current price
6. **Thread pool optimization** - Use system CPU count

**Expected Impact:**
- Performance: **3-5× faster** for large portfolios
- Memory: **2-5× reduction**
- Database queries: **10-50× fewer**
- Correctness: **Fixed equity calculation bug**

---

## Critical Issue 1: Equity Curve Storage Inefficiency

### Problem
- `PortfolioSnapshot` created for **every bar** (~2,500 for 1 year)
- Memory: 50-200 MB for equity curve alone
- Metrics calculation processes all snapshots

### Solution
Implement equity curve sampling: store snapshots at intervals and on significant changes.

### Tasks

**Task 1.1: Create EquityCurveSampler Class**
- **File:** `src/dgas/backtesting/equity_sampler.py` (new file)
- **Change:** Create sampler class with configurable interval and change threshold
- **Logic:**
  - Sample every N bars (configurable, default 10)
  - Sample when equity changes > threshold (default 1%)
  - Always sample at trade entry/exit
- **Effort:** 1 hour
- **Dependencies:** None

**Task 1.2: Integrate Sampler into SimulationEngine**
- **File:** `src/dgas/backtesting/engine.py`
- **Change:** Use sampler to decide when to append to equity_curve
- **Logic:**
  - Initialize sampler in `__init__` or `run()`
  - Check `sampler.should_sample(equity)` before appending
  - Always sample at trade entry/exit
- **Effort:** 1 hour
- **Dependencies:** Task 1.1

**Task 1.3: Integrate Sampler into PortfolioBacktestEngine**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** Use sampler in `_process_timestep()`
- **Logic:** Same as single-symbol engine
- **Effort:** 1 hour
- **Dependencies:** Task 1.1

**Task 1.4: Add Configuration Options**
- **File:** `src/dgas/backtesting/entities.py` or `portfolio_engine.py`
- **Change:** Add sampling config to `SimulationConfig` and `PortfolioBacktestConfig`
- **Options:**
  - `equity_sample_interval: int = 10` - Sample every N bars
  - `equity_min_change_pct: Decimal = Decimal("0.01")` - Sample on >1% change
  - `equity_sampling_enabled: bool = True` - Enable/disable
- **Effort:** 30 minutes
- **Dependencies:** None

**Task 1.5: Update Tests**
- **Files:** `tests/backtesting/test_engine.py`, `tests/backtesting/test_portfolio_engine.py`
- **Change:** Add tests for sampling logic
- **Test Cases:**
  - Samples at configured interval
  - Samples on significant change
  - Always samples at trade entry/exit
  - Can disable sampling
- **Effort:** 1 hour
- **Dependencies:** Tasks 1.1-1.3

---

## Critical Issue 2: HTF Bars Filtering Inefficiency

### Problem
- Linear scan O(n) through all HTF bars every time
- For 252 daily bars: 252 comparisons per indicator calculation
- Called once per symbol per timestep

### Solution
Use binary search for O(log n) lookup since bars are sorted by timestamp.

### Tasks

**Task 2.1: Implement Binary Search Filtering**
- **File:** `src/dgas/backtesting/portfolio_indicator_calculator.py`
- **Change:** Replace list comprehension with `bisect.bisect_right()`
- **Code:**
```python
import bisect

def _get_htf_bars_up_to(self, symbol: str, timestamp: datetime) -> List[IntervalData]:
    if symbol not in self.htf_cache:
        return []
    
    cache = self.htf_cache[symbol]
    bars = cache.bars
    
    # Binary search for insertion point
    idx = bisect.bisect_right(bars, timestamp, key=lambda b: b.timestamp)
    return bars[:idx]
```
- **Effort:** 30 minutes
- **Dependencies:** None

**Task 2.2: Verify Bars Are Sorted**
- **File:** `src/dgas/backtesting/portfolio_indicator_calculator.py`
- **Change:** Ensure bars are sorted when loaded (should already be sorted)
- **Verification:** Add assertion or sort if needed
- **Effort:** 15 minutes
- **Dependencies:** Task 2.1

**Task 2.3: Update Tests**
- **File:** `tests/backtesting/test_portfolio_indicator_calculator.py` (create if needed)
- **Change:** Add tests for binary search filtering
- **Test Cases:**
  - Returns correct bars up to timestamp
  - Handles empty cache
  - Handles timestamp before/after all bars
- **Effort:** 30 minutes
- **Dependencies:** Task 2.1

---

## Critical Issue 3: Redundant Equity Calculations

### Problem
- `calculate_position_size()` recalculates equity every time
- Called 500+ times per timestep (once per signal candidate)
- `get_current_state()` also recalculates equity

### Solution
Cache current equity in `PortfolioPositionManager` and invalidate on position changes.

### Tasks

**Task 3.1: Add Equity Caching to PortfolioPositionManager**
- **File:** `src/dgas/backtesting/portfolio_position_manager.py`
- **Change:** Add cache fields and cache invalidation logic
- **Code:**
```python
class PortfolioPositionManager:
    def __init__(self, ...):
        # ... existing code ...
        self._cached_equity: Decimal | None = None
        self._cached_equity_timestamp: datetime | None = None
        self._cached_equity_prices: Dict[str, Decimal] | None = None
    
    def _invalidate_equity_cache(self) -> None:
        """Invalidate equity cache when positions change."""
        self._cached_equity = None
        self._cached_equity_timestamp = None
        self._cached_equity_prices = None
```
- **Effort:** 30 minutes
- **Dependencies:** None

**Task 3.2: Update get_current_state() to Use Cache**
- **File:** `src/dgas/backtesting/portfolio_position_manager.py`
- **Change:** Check cache before recalculating
- **Logic:**
  - If cache valid (same timestamp and prices), return cached equity
  - Otherwise, recalculate and cache
- **Effort:** 1 hour
- **Dependencies:** Task 3.1

**Task 3.3: Update calculate_position_size() to Use Cached Equity**
- **File:** `src/dgas/backtesting/portfolio_position_manager.py`
- **Change:** Use cached equity instead of recalculating
- **Note:** Need to ensure cache is set before calling (via get_current_state)
- **Effort:** 30 minutes
- **Dependencies:** Task 3.2

**Task 3.4: Invalidate Cache on Position Changes**
- **File:** `src/dgas/backtesting/portfolio_position_manager.py`
- **Change:** Call `_invalidate_equity_cache()` in:
  - `open_position()` - after opening
  - `close_position()` - after closing
- **Effort:** 15 minutes
- **Dependencies:** Task 3.1

**Task 3.5: Update Tests**
- **File:** `tests/backtesting/test_portfolio_position_manager.py` (create if needed)
- **Change:** Add tests for equity caching
- **Test Cases:**
  - Cache is used when valid
  - Cache is invalidated on position changes
  - Cache is recalculated when prices change
- **Effort:** 1 hour
- **Dependencies:** Tasks 3.1-3.4

---

## Critical Issue 4: N+1 Query Pattern for Confluence Zones

### Problem
- `_load_confluence_zones()` called once per timestamp in batch load
- For 100 timestamps: 100 separate SQL queries
- Each query joins tables

### Solution
Batch load all confluence zones for all timestamps in a single query.

### Tasks

**Task 4.1: Modify load_indicators_batch() to Batch Load Zones**
- **File:** `src/dgas/backtesting/indicator_loader.py`
- **Change:** Load all zones for all timestamps in single query
- **Logic:**
  1. Extract all timestamps from rows
  2. Execute single query: `WHERE timestamp = ANY(%s)`
  3. Group zones by timestamp
  4. Attach zones to analyses
- **Effort:** 2 hours
- **Dependencies:** None

**Task 4.2: Update _load_confluence_zones() Signature (Optional)**
- **File:** `src/dgas/backtesting/indicator_loader.py`
- **Change:** May need to create batch version or keep single-timestamp version for compatibility
- **Note:** Keep single-timestamp version for `load_indicators_from_db()`
- **Effort:** 30 minutes
- **Dependencies:** Task 4.1

**Task 4.3: Update Tests**
- **File:** `tests/backtesting/test_indicator_loader.py`
- **Change:** Add tests for batch zone loading
- **Test Cases:**
  - Batch loads zones for multiple timestamps
  - Zones correctly attached to analyses
  - Handles timestamps with no zones
- **Effort:** 1 hour
- **Dependencies:** Task 4.1

---

## Critical Bug: Equity Calculation Uses Entry Price

### Problem
- `calculate_position_size()` uses `entry_price` instead of current market price
- Leads to incorrect equity calculation and risk sizing

**Current Code:**
```python
current_equity = self.cash + sum(
    pos.position.market_value(pos.position.entry_price)  # WRONG!
    for pos in self.positions.values()
)
```

### Solution
Use current market prices from `get_current_state()` or pass prices parameter.

### Tasks

**Task 5.1: Fix calculate_position_size() to Accept Prices**
- **File:** `src/dgas/backtesting/portfolio_position_manager.py`
- **Change:** Add `current_prices` parameter to `calculate_position_size()`
- **Logic:**
  - Use current_prices[symbol] if available
  - Fall back to entry_price if symbol not in prices
  - Calculate equity using current prices
- **Effort:** 1 hour
- **Dependencies:** None

**Task 5.2: Update Callers to Pass Current Prices**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** Pass `current_prices` when calling `calculate_position_size()`
- **Location:** In `_generate_entry_signals()`
- **Effort:** 30 minutes
- **Dependencies:** Task 5.1

**Task 5.3: Update Tests**
- **File:** `tests/backtesting/test_portfolio_position_manager.py`
- **Change:** Add tests verifying current prices are used
- **Test Cases:**
  - Uses current price when provided
  - Falls back to entry_price if symbol not in prices
  - Equity calculation is correct with current prices
- **Effort:** 1 hour
- **Dependencies:** Task 5.1

---

## Critical Issue 6: Thread Pool Optimization

### Problem
- Hardcoded to 3 workers: `ThreadPoolExecutor(max_workers=3)`
- Underutilizes systems with more cores
- Over-subscribes systems with fewer cores

### Solution
Use system CPU count with reasonable bounds.

### Tasks

**Task 6.1: Implement Dynamic Worker Count**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** Calculate optimal worker count based on CPU cores and symbol count
- **Code:**
```python
import os

# Calculate optimal worker count
cpu_count = os.cpu_count() or 4
symbol_count = len(eligible_symbols)
optimal_workers = min(cpu_count, symbol_count, 8)  # Cap at 8

with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
```
- **Effort:** 15 minutes
- **Dependencies:** None

**Task 6.2: Add Configuration Option (Optional)**
- **File:** `src/dgas/backtesting/portfolio_engine.py`
- **Change:** Add `max_workers` override to `PortfolioBacktestConfig`
- **Logic:** Use config value if provided, otherwise calculate dynamically
- **Effort:** 15 minutes
- **Dependencies:** Task 6.1

**Task 6.3: Update Tests**
- **File:** `tests/backtesting/test_portfolio_engine.py` (create if needed)
- **Change:** Add tests for worker count calculation
- **Test Cases:**
  - Uses CPU count when available
  - Caps at symbol count
  - Caps at maximum (8)
  - Uses override if configured
- **Effort:** 30 minutes
- **Dependencies:** Task 6.1

---

## Implementation Order

### Phase 1: Foundation & Critical Bug Fix (Day 1)
1. ✅ Task 5.1: Fix equity calculation bug (CRITICAL - correctness issue)
2. ✅ Task 5.2: Update callers to pass current prices
3. ✅ Task 3.1: Add equity caching infrastructure
4. ✅ Task 1.1: Create EquityCurveSampler class
5. ✅ Task 1.4: Add sampling configuration

**Verification:** Equity calculation uses current prices, caching infrastructure ready

### Phase 2: Performance Optimizations (Day 1-2)
6. ✅ Task 3.2: Update get_current_state() to use cache
7. ✅ Task 3.3: Update calculate_position_size() to use cached equity
8. ✅ Task 3.4: Invalidate cache on position changes
9. ✅ Task 2.1: Implement HTF binary search filtering
10. ✅ Task 2.2: Verify bars are sorted
11. ✅ Task 6.1: Implement dynamic thread pool sizing

**Verification:** Caching works, binary search faster, thread pool optimized

### Phase 3: Database & Sampling (Day 2)
12. ✅ Task 4.1: Batch load confluence zones
13. ✅ Task 4.2: Update zone loading signature
14. ✅ Task 1.2: Integrate sampler into SimulationEngine
15. ✅ Task 1.3: Integrate sampler into PortfolioBacktestEngine

**Verification:** Batch loading works, sampling reduces memory

### Phase 4: Testing (Day 2-3)
16. ✅ Task 1.5: Update equity sampling tests
17. ✅ Task 2.3: Update HTF filtering tests
18. ✅ Task 3.5: Update equity caching tests
19. ✅ Task 4.3: Update batch zone loading tests
20. ✅ Task 5.3: Update equity calculation tests
21. ✅ Task 6.3: Update thread pool tests

**Verification:** All tests pass, no regressions

---

## Testing Strategy

### Unit Tests
- Test equity sampling logic (interval, change threshold)
- Test binary search filtering (correct bars returned)
- Test equity caching (cache hit/miss, invalidation)
- Test batch zone loading (zones attached correctly)
- Test equity calculation fix (uses current prices)
- Test thread pool sizing (correct worker count)

### Integration Tests
- Run portfolio backtest with all optimizations
- Compare results before/after (must be identical)
- Measure performance improvements
- Measure memory usage reduction

### Validation Tests
- Verify equity curve has fewer snapshots (80-90% reduction)
- Verify HTF filtering is faster (30-50×)
- Verify equity caching works (10-50× faster)
- Verify batch zone loading (10-50× fewer queries)
- Verify equity calculation uses current prices (correctness)
- Verify thread pool uses CPU count

---

## Risk Assessment

### Low Risk
- Thread pool optimization (backward compatible)
- HTF binary search (algorithmic improvement, same results)
- Equity caching (internal optimization)

### Medium Risk
- Equity curve sampling (changes output format)
- Batch zone loading (database query changes)
- Equity calculation fix (changes behavior - correctness fix)

### Mitigation
- Sampling can be disabled via config
- Comprehensive testing before merge
- Compare results before/after (must be identical)
- Verify equity calculation fix produces correct results

---

## Success Criteria

✅ **Must Have:**
1. Equity curve sampling reduces snapshots by 80-90%
2. HTF binary search is 30-50× faster
3. Equity caching eliminates redundant calculations
4. Batch zone loading reduces queries by 10-50×
5. Equity calculation uses current prices (bug fixed)
6. Thread pool uses system CPU count
7. All existing tests pass (no regressions)
8. Results identical before/after optimizations

✅ **Should Have:**
9. Configuration options for sampling
10. Comprehensive test coverage
11. Performance benchmarks showing improvements

---

## Estimated Effort

**Total:** ~12-15 hours

**Breakdown:**
- Foundation & bug fix: 3 hours
- Performance optimizations: 4 hours
- Database & sampling: 3 hours
- Testing: 3-5 hours

**Timeline:** 2-3 days

---

## Dependencies & Prerequisites

### Code Dependencies
- `bisect` module (standard library) ✅
- `os.cpu_count()` (standard library) ✅
- Bars sorted by timestamp ✅
- Database connection available ✅

### Data Dependencies
- Historical data available ✅
- Confluence zones in database ✅

---

## Rollback Plan

If issues arise:
1. Disable sampling via `equity_sampling_enabled = False`
2. Revert to linear scan (remove binary search)
3. Disable caching (remove cache logic)
4. Revert batch loading (use per-timestamp queries)
5. Revert thread pool (hardcode to 3)
6. Use `git revert` for code changes

---

## Next Steps

1. **Review this plan** - Confirm scope and approach
2. **Begin Phase 1** - Fix critical bug first (correctness)
3. **Test incrementally** - After each phase
4. **Validate results** - Compare before/after (must be identical)
5. **Measure performance** - Benchmark improvements

---

**End of Plan**
