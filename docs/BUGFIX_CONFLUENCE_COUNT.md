# Bug Fix: TypeError in Signal Ranker

## Problem

The evaluation backtest failed with:
```
TypeError: unsupported operand type(s) for /: 'str' and 'int'
```

**Location**: `src/dgas/backtesting/signal_ranker.py`, line 177

## Root Cause

The `confluence_zones_count` value is stored as a **string** in signal metadata (from `prediction_signal.py`), but the signal ranker was trying to perform arithmetic operations (`/ 5`) on it without converting to an integer first.

### Code Flow

1. **Signal Creation** (`prediction_signal.py:170`):
   ```python
   "confluence_zones_count": str(gen_signal.confluence_zones_count),
   ```
   Stores value as string

2. **Signal Ranking** (`signal_ranker.py:175-177`):
   ```python
   confluence_count = signal.metadata.get("confluence_zones_count", 0)
   scores[RankingCriteria.CONFLUENCE] = Decimal(str(min(confluence_count / 5, 1))) * Decimal("100")
   ```
   Tries to divide string by integer → **ERROR**

## Fix Applied

Added type checking and conversion for `confluence_zones_count` and other metadata fields that might be strings:

```python
# Confluence (number of confluence zones)
confluence_count = signal.metadata.get("confluence_zones_count", 0)
# Convert to int if it's a string (metadata stores values as strings)
if isinstance(confluence_count, str):
    confluence_count = int(confluence_count) if confluence_count else 0
elif not isinstance(confluence_count, (int, float)):
    confluence_count = 0
# Normalize to 0-100 (cap at 5 zones)
scores[RankingCriteria.CONFLUENCE] = Decimal(str(min(confluence_count / 5, 1))) * Decimal("100")
```

Also added similar type conversion for:
- `signal_strength` (string → float)
- `alignment_score` (string → float)
- `volatility` (string → float)

## Files Modified

- `src/dgas/backtesting/signal_ranker.py`
  - Added type checking and conversion for metadata values
  - Handles string, int, float types safely

## Testing

The fix ensures that:
1. String values are converted to appropriate numeric types
2. Invalid values default to safe defaults (0 or 0.5)
3. Arithmetic operations work correctly

## Status

✅ **Fixed** - Ready for retest
