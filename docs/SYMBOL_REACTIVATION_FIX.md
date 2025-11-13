# Symbol Reactivation Fix

**Date**: November 13, 2025  
**Issue**: Dashboard showed 518 symbols with data, but only 516 should be active  
**Status**: ✅ **FIXED**

---

## Problem Summary

After fixing the initial symbol count issue (719 → 516), the dashboard started showing **518 symbols with data** instead of 516. Investigation revealed that `QQQ` and `SPY` were being reactivated during data collection.

### Root Cause

The `ensure_market_symbol()` function in `src/dgas/data/repository.py` had a bug in its `ON CONFLICT` clause:

```sql
is_active = EXCLUDED.is_active
```

This meant that whenever data collection called `ensure_market_symbol()` (which defaults to `is_active=True`), it would overwrite the existing `is_active` status, reactivating symbols that had been intentionally deactivated.

### Why It Happened

1. Symbols `QQQ` and `SPY` were deactivated (not in CSV)
2. Data collection service collected data for these symbols
3. `ensure_market_symbol()` was called with default `is_active=True`
4. The `ON CONFLICT` clause overwrote `is_active=False` with `is_active=True`
5. Symbols were reactivated, increasing count from 516 → 518

---

## Solution

Modified `ensure_market_symbol()` to preserve existing `is_active=False` status when updating existing symbols:

```sql
-- Preserve existing is_active status unless explicitly provided (not default True)
-- This prevents data collection from reactivating deactivated symbols
is_active = CASE 
    WHEN EXCLUDED.is_active = true AND market_symbols.is_active = false THEN market_symbols.is_active
    ELSE EXCLUDED.is_active
END,
```

**Logic**:
- If new value is `True` AND existing value is `False` → preserve `False` (prevent reactivation)
- Otherwise → use new value (allows explicit activation/deactivation)

---

## Verification

✅ **Active symbols**: 516 (matches CSV)  
✅ **Symbols with data**: 516 (matches active count)  
✅ **Inactive symbols preserved**: `QQQ` and `SPY` remain inactive even after data collection  
✅ **Test passed**: `ensure_market_symbol()` preserves `is_active=False` status

---

## Prevention

The fix ensures that:
1. **Data collection won't reactivate deactivated symbols** - When collecting data for existing symbols, their `is_active` status is preserved
2. **New symbols are still activated by default** - New symbols inserted with `is_active=True` will be active
3. **Explicit activation still works** - If code explicitly sets `is_active=True` for an existing symbol, it will be activated (though this should be done through proper sync scripts)

---

## Files Changed

1. `src/dgas/data/repository.py`:
   - Updated `ensure_market_symbol()` function
   - Modified `ON CONFLICT` clause to preserve `is_active=False` status

---

## Related Issues

- See `docs/SYMBOL_SYNC_FIX.md` for the initial symbol count fix (719 → 516)
- This fix prevents the reactivation issue that caused 516 → 518

---

**Status**: ✅ **RESOLVED**  
**Active Symbols**: 516 (matches CSV)  
**Data Coverage**: 516 symbols (matches active count)
