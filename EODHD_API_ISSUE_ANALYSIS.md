# EODHD API Backfill Issue Analysis

## Problem
Many symbols are returning "No data available from API" when trying to backfill Nov 6-13, 2025 data.

## Root Causes Identified

### 1. **Symbol Format Issue** ⚠️ LIKELY PRIMARY CAUSE

**Current Implementation:**
- API call: `intraday/{symbol}` (e.g., `intraday/ABT`)
- Code normalizes symbols by REMOVING `.US` suffix when storing

**EODHD API Documentation Format:**
According to https://eodhd.com/financial-apis/intraday-historical-data-api:
- Format: `intraday/{SYMBOL}.{EXCHANGE}`
- For US stocks: `intraday/{SYMBOL}.US` (e.g., `intraday/ABT.US`)

**Issue:**
The code is calling `intraday/ABT` but EODHD expects `intraday/ABT.US` for US stocks.

**Evidence:**
- Some symbols work (ACGL, ALGN, APA) - might be working by coincidence or different API behavior
- Most symbols fail - likely because they need `.US` suffix

### 2. **Date Range Logic Issue** ⚠️ CRITICAL

**Current Code in `backfill_intraday`:**
```python
historical_end = min(end_dt, today - timedelta(days=1))
```

**Problem:**
If `end_date` is Nov 13, 2025 and `today` is Nov 14, 2024:
- `end_dt` = Nov 13, 2025
- `today - timedelta(days=1)` = Nov 13, 2024
- `historical_end` = Nov 13, 2024 (the earlier date)

This means it's trying to fetch from Nov 1, 2025 to Nov 13, 2024, which is:
- Backwards (start > end)
- In the future (Nov 2025 doesn't exist yet)
- Will return empty data

**However:** If the user actually meant Nov 6-13, **2024** (not 2025), this wouldn't be an issue.

### 3. **Empty Response Handling**

**Current Behavior:**
- API returns empty array `[]` when no data available
- Code treats this as "No data available from API"
- No distinction between:
  - Symbol doesn't exist
  - Symbol exists but no data for date range
  - API error

**EODHD API Behavior:**
- Returns empty array `[]` for valid symbols with no data
- Returns error for invalid symbols (but we might not be catching it)

## Recommended Fixes

### Fix 1: Add `.US` Suffix to API Calls (HIGH PRIORITY)

**File:** `src/dgas/data/client.py`

**Change:**
```python
def fetch_intraday(
    self,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    interval: str = "30m",
    limit: int = 50000,
    exchange: str = "US",  # Add exchange parameter
) -> List[IntervalData]:
    # ... existing code ...
    
    # Add .US suffix for US stocks
    if exchange == "US" and not symbol.endswith(".US"):
        api_symbol = f"{symbol}.US"
    else:
        api_symbol = symbol
    
    path = f"intraday/{api_symbol}"
    # ... rest of code ...
```

**Also update:**
- `fetch_eod()` - same fix
- `fetch_live_ohlcv()` - same fix
- All callers to pass `exchange="US"` parameter

### Fix 2: Fix Date Range Logic for Future Dates

**File:** `src/dgas/data/ingestion.py`

**Change:**
```python
def backfill_intraday(...):
    # ... existing code ...
    
    today = datetime.now(timezone.utc).date()
    
    # Fix: Don't cap end_date to yesterday if it's explicitly requested
    # Only cap if end_date is in the future beyond today
    if end_dt > today:
        # If end date is in future, only fetch up to today
        historical_end = today
    else:
        # If end date is in past, fetch up to yesterday (to avoid today's incomplete data)
        historical_end = min(end_dt, today - timedelta(days=1))
    
    # ... rest of code ...
```

### Fix 3: Better Error Handling and Logging

**Improvements:**
1. Log the actual API URL being called
2. Log the API response status and body for empty responses
3. Distinguish between:
   - Empty response (no data available)
   - API error (4xx/5xx)
   - Network error

## Testing Recommendations

1. **Test Symbol Format:**
   ```bash
   python scripts/test_eodhd_api_symbol_format.py
   ```
   This will test both `ABT` and `ABT.US` formats to see which works.

2. **Check Current Date:**
   Verify what the actual current date is. If we're in 2024, Nov 6-13, 2025 is in the future and won't have data.

3. **Test with Known Working Symbol:**
   Test with a symbol that's working (like ACGL) to see what format it's using.

## Immediate Action Items

1. ✅ Create test script to verify symbol format requirement
2. ⏳ Fix `EODHDClient.fetch_intraday()` to add `.US` suffix
3. ⏳ Fix date range logic in `backfill_intraday()`
4. ⏳ Update backfill script to handle empty responses better
5. ⏳ Test with a small batch of symbols after fixes

## Questions to Clarify

1. **What is the current date?** If we're in 2024, Nov 6-13, 2025 is in the future and the API won't have that data.
2. **Did you mean Nov 6-13, 2024?** If so, we should update the backtest dates.
3. **Why do some symbols work?** (ACGL, ALGN, APA) - Are they using a different format or do they have special handling?
