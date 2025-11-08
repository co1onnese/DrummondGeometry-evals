# Backtesting High-Impact Fixes - Remediation Plan

**Date:** 2025-01-XX  
**Focus:** Fix Priority 2 High-Impact improvements from realistic simulation review  
**Scope:** Confidence score utilization for position sizing and signal filtering

---

## Executive Summary

This plan addresses **1 high-impact improvement** that will significantly improve risk-adjusted returns:

**High-Impact Item:** Utilize confidence scores for position sizing and signal filtering

**Expected Impact:**
- Better risk-adjusted position sizing (scale by confidence)
- Filter out low-confidence signals
- Track confidence in trade records for analysis
- More optimal portfolio allocation

---

## Current State Analysis

### What Exists
✅ **Confidence data available:**
- `MultiTimeframeAnalysis.signal_strength` (0.0-1.0) - composite signal strength
- Available in strategy context via `analysis.signal_strength`
- Already used in `SignalRanker` for ranking (but not for sizing)

### What's Missing
❌ **Confidence not used for:**
- Position sizing (all signals get same size regardless of confidence)
- Signal filtering (low-confidence signals still executed)
- Trade records (confidence not tracked)

### Current Code Flow
```python
# portfolio_engine.py _generate_entry_signals()
# 1. Calculate indicators (includes MultiTimeframeAnalysis with signal_strength)
# 2. Generate strategy signals
# 3. Extract stop_loss from metadata
# 4. Calculate position size (NO confidence scaling)
# 5. Create RankedSignal (confidence not stored)
```

---

## High-Impact Item: Utilize Confidence Scores

### Problem Description

Signals have confidence scores (`signal_strength` from `MultiTimeframeAnalysis`), but they are **not used** for:
- Position sizing (should scale size by confidence)
- Signal filtering (low confidence signals still executed)
- Risk management (should reduce size for lower confidence)

**Current Behavior:**
- All signals get same position size (based on risk_per_trade_pct)
- Low-confidence signals (e.g., 0.3) get same allocation as high-confidence (e.g., 0.9)
- No filtering based on confidence threshold

**Impact:**
- Over-allocation to low-confidence trades
- Under-allocation to high-confidence trades
- Suboptimal risk-adjusted returns

### Solution Overview

1. **Extract confidence from analysis** when generating signals
2. **Filter low-confidence signals** (configurable threshold)
3. **Scale position size by confidence** (multiply base size by confidence)
4. **Store confidence in metadata** for trade records and analysis

---

## Implementation Plan

### Task 1: Add Confidence Configuration

**File:** `src/dgas/backtesting/portfolio_engine.py`

**Change:** Add confidence threshold to `PortfolioBacktestConfig`

```python
@dataclass
class PortfolioBacktestConfig:
    # ... existing fields ...
    min_signal_confidence: Decimal = Decimal("0.5")  # Minimum confidence to execute signal
    confidence_scaling_enabled: bool = True  # Enable confidence-based position sizing
```

**Effort:** 15 minutes  
**Dependencies:** None

---

### Task 2: Extract Confidence from Analysis

**File:** `src/dgas/backtesting/portfolio_engine.py`

**Change:** In `_generate_entry_signals()`, extract `signal_strength` from `MultiTimeframeAnalysis`

**Location:** After calculating indicators, before generating signals

**Code:**
```python
# After calculating indicators
indicators = indicator_results[symbol]
analysis = indicators.get("analysis")
if isinstance(analysis, MultiTimeframeAnalysis):
    confidence = float(analysis.signal_strength)  # 0.0 to 1.0
else:
    confidence = 0.5  # Default if no analysis
```

**Effort:** 30 minutes  
**Dependencies:** None

---

### Task 3: Filter Low-Confidence Signals

**File:** `src/dgas/backtesting/portfolio_engine.py`

**Change:** Skip signals below confidence threshold

**Location:** In `_generate_entry_signals()`, after extracting confidence

**Code:**
```python
# Filter by minimum confidence
if confidence < float(self.config.min_signal_confidence):
    continue  # Skip low-confidence signals
```

**Effort:** 15 minutes  
**Dependencies:** Task 2

---

### Task 4: Scale Position Size by Confidence

**File:** `src/dgas/backtesting/portfolio_engine.py`

**Change:** Multiply base position size by confidence multiplier

**Location:** In `_generate_entry_signals()`, when calculating position size

**Code:**
```python
# Calculate base position size
base_quantity, base_risk = self.position_manager.calculate_position_size(
    symbol,
    entry_price,
    stop_loss,
    1 if signal.action == SignalAction.ENTER_LONG else -1,
)

# Scale by confidence if enabled
if self.config.confidence_scaling_enabled:
    confidence_multiplier = Decimal(str(confidence))  # 0.0 to 1.0
    adjusted_quantity = base_quantity * confidence_multiplier
    adjusted_risk = base_risk * confidence_multiplier
    
    # Normalize quantity (round to whole shares)
    adjusted_quantity = adjusted_quantity.quantize(Decimal("1"), rounding=ROUND_DOWN)
    
    # Use adjusted values
    quantity = adjusted_quantity
    risk_amount = adjusted_risk
else:
    quantity = base_quantity
    risk_amount = base_risk
```

**Effort:** 1 hour  
**Dependencies:** Task 2

---

### Task 5: Store Confidence in Signal Metadata

**File:** `src/dgas/backtesting/portfolio_engine.py`

**Change:** Add confidence to signal metadata and RankedSignal

**Location:** When creating RankedSignal

**Code:**
```python
# Add confidence to metadata
metadata = dict(signal.metadata) if signal.metadata else {}
metadata["confidence"] = str(confidence)
metadata["signal_strength"] = str(analysis.signal_strength) if analysis else "0.5"

ranked_signal = RankedSignal(
    symbol=symbol,
    signal=signal,
    score=Decimal("0"),  # Will be set by ranker
    entry_price=entry_price,
    stop_loss=stop_loss,
    target=take_profit,
    risk_amount=risk_amount,
    metadata=metadata,  # Now includes confidence
)
```

**Effort:** 30 minutes  
**Dependencies:** Task 2

---

### Task 6: Store Confidence in Position Entity

**File:** `src/dgas/backtesting/entities.py`

**Change:** Add optional `confidence` field to Position

**Code:**
```python
@dataclass
class Position:
    # ... existing fields ...
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    confidence: Decimal | None = None  # Signal confidence (0.0-1.0)
    notes: Mapping[str, Any] = field(default_factory=dict)
```

**Effort:** 15 minutes  
**Dependencies:** None

---

### Task 7: Pass Confidence to Position Creation

**File:** `src/dgas/backtesting/execution/trade_executor.py`

**Change:** Extract confidence from metadata and store in Position

**Location:** In `open_position()` method

**Code:**
```python
# Extract confidence from metadata
confidence = None
if metadata:
    confidence_str = metadata.get("confidence")
    if confidence_str:
        if isinstance(confidence_str, str):
            confidence = Decimal(confidence_str)
        else:
            confidence = Decimal(str(confidence_str))

# Create position with confidence
position = Position(
    # ... existing fields ...
    stop_loss=stop_loss,
    take_profit=take_profit,
    confidence=confidence,
    notes=metadata or {},
)
```

**Effort:** 30 minutes  
**Dependencies:** Task 6

---

### Task 8: Update Portfolio Position Manager

**File:** `src/dgas/backtesting/portfolio_position_manager.py`

**Change:** Pass confidence when opening position

**Location:** In `open_position()` method

**Code:**
```python
# Extract confidence from metadata
confidence = None
if metadata:
    confidence_str = metadata.get("confidence")
    if confidence_str:
        confidence = Decimal(str(confidence_str)) if isinstance(confidence_str, str) else Decimal(str(confidence_str))

# Pass to executor
position, commission = self.executor.open_position(
    # ... existing parameters ...
    metadata=metadata,
    stop_loss=stop_loss,
    take_profit=target,
    confidence=confidence,  # ADD THIS
)
```

**Wait:** Actually, executor already extracts from metadata, so we just need to ensure metadata has confidence. Let me check...

Actually, looking at the code, the executor extracts from metadata automatically, so we just need to ensure confidence is in metadata (which Task 5 handles). But we should still update the executor signature to accept confidence directly for clarity.

**Effort:** 30 minutes  
**Dependencies:** Task 7

---

### Task 9: Update Single-Symbol Engine (Optional)

**File:** `src/dgas/backtesting/engine.py`

**Change:** Extract and use confidence for position sizing in single-symbol engine

**Note:** Single-symbol engine uses different position sizing logic. May want to add confidence scaling here too for consistency.

**Effort:** 1 hour  
**Dependencies:** Task 2-5  
**Priority:** Lower (portfolio engine is primary use case)

---

### Task 10: Add Tests

**Files:** 
- `tests/backtesting/test_portfolio_engine.py` (create if doesn't exist)
- `tests/backtesting/test_confidence_scaling.py` (new file)

**Test Cases:**
1. Low-confidence signals are filtered out
2. Position size scales with confidence (high confidence = larger size)
3. Confidence stored in Position entity
4. Confidence stored in trade metadata
5. Edge cases: confidence = 0.0, confidence = 1.0, confidence = None

**Effort:** 2 hours  
**Dependencies:** All implementation tasks

---

## Implementation Order

### Phase 1: Foundation (Day 1)
1. ✅ Task 1: Add confidence configuration
2. ✅ Task 6: Add confidence to Position entity
3. ✅ Task 2: Extract confidence from analysis

**Verification:** Confidence extracted and available

### Phase 2: Core Functionality (Day 1)
4. ✅ Task 3: Filter low-confidence signals
5. ✅ Task 4: Scale position size by confidence
6. ✅ Task 5: Store confidence in metadata

**Verification:** Position sizing scales with confidence

### Phase 3: Integration (Day 1-2)
7. ✅ Task 7: Pass confidence to Position creation
8. ✅ Task 8: Update portfolio position manager

**Verification:** Confidence stored in Position objects

### Phase 4: Testing (Day 2)
9. ✅ Task 10: Add comprehensive tests

**Verification:** All tests pass

### Phase 5: Optional Enhancement (Day 2)
10. ✅ Task 9: Update single-symbol engine (if time permits)

---

## Configuration Options

### PortfolioBacktestConfig Additions

```python
@dataclass
class PortfolioBacktestConfig:
    # ... existing fields ...
    
    # Confidence-based filtering and sizing
    min_signal_confidence: Decimal = Decimal("0.5")  # Minimum confidence to execute
    confidence_scaling_enabled: bool = True  # Enable confidence-based sizing
    confidence_scaling_min: Decimal = Decimal("0.3")  # Minimum multiplier (even low confidence gets some size)
    confidence_scaling_max: Decimal = Decimal("1.0")  # Maximum multiplier
```

**Rationale:**
- `min_signal_confidence`: Filter out very low confidence signals
- `confidence_scaling_enabled`: Toggle feature on/off
- `confidence_scaling_min`: Ensure even low-confidence signals get some allocation (optional)
- `confidence_scaling_max`: Cap maximum allocation (optional)

---

## Expected Behavior

### Before Fixes
- Signal with confidence 0.3: Gets full position size (e.g., $2,000 risk)
- Signal with confidence 0.9: Gets same position size ($2,000 risk)
- **Result:** Over-allocation to weak signals, under-allocation to strong signals

### After Fixes
- Signal with confidence 0.3: 
  - If below threshold (0.5): Filtered out (no position)
  - If above threshold: Gets scaled size (e.g., $600 risk = $2,000 * 0.3)
- Signal with confidence 0.9: Gets scaled size (e.g., $1,800 risk = $2,000 * 0.9)
- **Result:** Better risk-adjusted allocation

---

## Risk Assessment

### Low Risk
- Adding configuration options (backward compatible with defaults)
- Adding confidence field to Position (optional field)

### Medium Risk
- Position sizing changes (affects P&L)
- Signal filtering (may reduce number of trades)

### Mitigation
- Make confidence scaling optional (can disable)
- Default threshold (0.5) is conservative
- Comprehensive testing before merge
- Compare results before/after

---

## Success Criteria

✅ **Must Have:**
1. Confidence extracted from analysis
2. Low-confidence signals filtered (below threshold)
3. Position size scales with confidence
4. Confidence stored in Position and metadata
5. All existing tests pass (no regressions)

✅ **Should Have:**
6. Configuration options for threshold and scaling
7. Comprehensive test coverage
8. Documentation updated

---

## Estimated Effort

**Total:** ~6-8 hours

**Breakdown:**
- Foundation: 1 hour
- Core functionality: 2 hours
- Integration: 1 hour
- Testing: 2-3 hours
- Optional enhancements: 1 hour

**Timeline:** 1-2 days

---

## Dependencies & Prerequisites

### Code Dependencies
- `MultiTimeframeAnalysis` has `signal_strength` ✅
- Position entity supports optional fields ✅
- Metadata extraction already works ✅

### Data Dependencies
- Analysis available in strategy context ✅
- Signal strength calculated correctly ✅

---

## Testing Strategy

### Unit Tests
- Test confidence extraction from analysis
- Test filtering logic (below/above threshold)
- Test position size scaling (various confidence values)
- Test confidence storage in Position

### Integration Tests
- Run portfolio backtest with confidence scaling enabled
- Run portfolio backtest with confidence scaling disabled
- Compare results (should see better risk-adjusted returns with scaling)

### Validation Tests
- Verify low-confidence signals filtered
- Verify position sizes scale correctly
- Verify confidence stored in trade records

---

## Rollback Plan

If issues arise:
1. Set `confidence_scaling_enabled = False` to disable feature
2. Set `min_signal_confidence = Decimal("0.0")` to disable filtering
3. Revert commits using `git revert`
4. No database migrations needed

---

## Next Steps

1. **Review this plan** - Confirm scope and approach
2. **Begin Phase 1** - Add configuration and extract confidence
3. **Test incrementally** - After each phase
4. **Validate results** - Compare before/after backtest results

---

**End of Plan**
