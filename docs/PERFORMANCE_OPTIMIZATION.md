# Performance Optimization Analysis

## Problem Identified

The evaluation backtest was running extremely slowly:
- **Rate**: 0.57 timesteps/minute (~105 seconds per timestep)
- **Per symbol**: ~1.04 seconds per symbol calculation
- **Estimated total**: ~40.8 hours (vs. expected 8-15 hours)

## Root Causes

### 1. Unbounded History Growth
**Issue**: For each timestep, the code recalculates indicators using ALL historical bars, which keeps growing.

- Timestep 1: Uses 5 bars
- Timestep 100: Uses 100 bars  
- Timestep 1000: Uses 1000 bars
- Each calculation gets progressively slower

**Impact**: O(n²) complexity where n = number of timesteps

### 2. Full Recalculation Every Timestep
**Issue**: `build_timeframe_data()` recalculates everything from scratch:
- PLdot calculation (rolling window over all bars)
- Envelope calculation
- State classification
- Pattern detection (multiple patterns)
- Drummond lines calculation
- Multi-timeframe analysis

**Impact**: Even with limited history, each calculation is expensive

### 3. Processing All Symbols Every Timestep
**Issue**: For each timestep, indicators are calculated for ALL 101 symbols, even if:
- Symbol already has a position (won't generate new signals)
- Symbol hasn't changed significantly

**Impact**: 101 × expensive calculations per timestep

### 4. Limited Parallelization
**Issue**: System has 3 CPUs, so only 3 symbols processed in parallel
- 101 symbols ÷ 3 workers = ~34 batches
- Each batch waits for slowest symbol

**Impact**: Parallelization helps but doesn't solve the fundamental slowness

## Optimizations Applied

### 1. Limit History Size (✅ Implemented)
**Change**: Limit history to last 200 bars instead of unlimited growth

```python
# In portfolio_engine.py
self.max_history_bars = 200

# Limit history when it exceeds max
if len(history) > self.max_history_bars:
    excess = len(history) - self.max_history_bars
    for _ in range(excess):
        history.popleft()
```

**Expected Impact**: Prevents O(n²) growth, keeps calculation time constant

### 2. Limit Bars Used in Calculation (✅ Implemented)
**Change**: Only use last 200 bars for indicator calculation

```python
# In portfolio_indicator_calculator.py
max_bars_for_calc = 200
trading_bars_for_calc = list(historical_bars[-max_bars_for_calc:]) if len(historical_bars) > max_bars_for_calc else list(historical_bars)
```

**Expected Impact**: Reduces calculation time per symbol from ~1s to ~0.1-0.2s

### 3. Skip Symbols with Positions (✅ Already Implemented)
**Change**: Already skips symbols that have positions

```python
if portfolio_state.has_position(symbol):
    continue
```

**Impact**: Reduces number of symbols processed per timestep

## Expected Performance Improvement

### Before Optimization
- Time per timestep: ~105 seconds
- Time per symbol: ~1.04 seconds
- Estimated total: ~40.8 hours

### After Optimization (Expected)
- Time per timestep: ~10-20 seconds (5-10x improvement)
- Time per symbol: ~0.1-0.2 seconds (5-10x improvement)
- Estimated total: ~4-8 hours (5-10x improvement)

**Rationale**: 
- Limiting to 200 bars reduces calculation time significantly
- Most indicators only need recent data (PLdot uses 3-period window)
- 200 bars is sufficient for pattern detection and state classification

## Additional Optimization Opportunities

### 1. Incremental Calculation (Future)
**Idea**: Cache previous timeframe data and only calculate new indicators for latest bar

**Complexity**: High - requires refactoring calculation pipeline
**Impact**: Could reduce per-symbol time to ~0.01-0.05 seconds

### 2. Skip Unchanged Symbols (Future)
**Idea**: Track which symbols had price changes and only recalculate those

**Complexity**: Medium
**Impact**: Could reduce symbols processed by 50-80%

### 3. Pre-filter Low-Confidence Signals (Future)
**Idea**: Quick confidence check before full indicator calculation

**Complexity**: Low
**Impact**: Could skip 50-70% of calculations

### 4. Use Cached Calculators (Future)
**Idea**: Use `CachedPLDotCalculator` and `CachedEnvelopeCalculator` from calculations/cache.py

**Complexity**: Low-Medium
**Impact**: Could reduce calculation time by 20-30%

## Testing the Optimizations

### Current Run
The current backtest was started before optimizations. It will continue with old code.

### New Run
To test optimizations:
1. Stop current run (if desired)
2. Restart with optimized code
3. Monitor performance improvement

### Monitoring
Use the monitor to track:
- Time per timestep
- Progress rate
- CPU usage

```bash
python3 scripts/monitor_evaluation.py --interval 10
```

## Files Modified

1. `src/dgas/backtesting/portfolio_engine.py`
   - Added `max_history_bars = 200`
   - Added history limiting logic

2. `src/dgas/backtesting/portfolio_indicator_calculator.py`
   - Added `max_bars_for_calc = 200`
   - Limited bars used in calculation

## Recommendations

1. **Let current run complete** (if close to completion) OR **restart with optimizations** (if early)
2. **Monitor new run** to verify performance improvement
3. **Consider additional optimizations** if still too slow
4. **Profile specific operations** if needed to identify remaining bottlenecks

## Notes

- 200 bars ≈ 100 hours of data at 30-minute intervals
- This is sufficient for:
  - PLdot (3-period window)
  - Envelopes (3-period window)
  - State classification (3-bar rule)
  - Pattern detection (needs recent data)
  - Multi-timeframe analysis (uses recent HTF bars)

- Trade-off: Limiting history means we lose very old patterns, but:
  - Most trading signals are based on recent patterns
  - Very old patterns are less relevant for current signals
  - This is a reasonable trade-off for performance
