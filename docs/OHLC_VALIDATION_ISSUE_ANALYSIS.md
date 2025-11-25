# OHLC Validation Issue Analysis

**Date**: 2025-11-21  
**Issue**: High rate of skipped records during data collection  
**Status**: Under Investigation

---

## Problem Summary

The data collection service is reporting high rates of skipped records with "invalid OHLC data":

```
Skipped 390 records with invalid OHLC data out of 469 total
Skipped 468 records with invalid OHLC data out of 547 total
High error rate detected: 12.5% (threshold: 10.0%)
High error rate detected: 14.7% (threshold: 10.0%)
```

This results in:
- Low data collection success rates
- High error rate alerts
- Potential gaps in market data

---

## Root Cause Analysis

### 1. Data Flow

When collecting 30m interval data:

1. **API Request**: EODHD API is called with `interval=5m` (since API doesn't support 30m directly)
2. **Response Parsing**: `IntervalData.from_api_list()` parses all 5m bars from API response
3. **Validation**: Records with `None` values for any OHLC field (open, high, low, close) are skipped
4. **Aggregation**: Valid 5m bars are aggregated into 30m bars using `aggregate_bars()`

### 2. Why Records Are Skipped

Records are skipped when `from_api_record()` raises a `ValueError` due to:

```python
# From models.py line 152-156
if open_val is None or high_val is None or low_val is None or close_val is None:
    raise ValueError(
        f"API record missing required OHLC data for {symbol}: "
        f"open={open_val}, high={high_val}, low={low_val}, close={close_val}"
    )
```

### 3. When None OHLC Values Occur

None OHLC values can occur in legitimate scenarios:

1. **Market Closure**: During non-trading hours, EODHD may return bars with None OHLC values
2. **Incomplete Bars**: Bars that haven't completed their interval yet
3. **API Errors**: Partial responses from EODHD API (e.g., 500 errors)
4. **Data Gaps**: Periods where no trading occurred

### 4. Diagnostic Results

Testing with diagnostic script:

- **AAPL**: 79 records in API response, all valid, successfully parsed
- **FI**: Empty API response (0 records), but client method returned 1052 bars (likely from different endpoint or cached data)

The discrepancy suggests:
- The issue may be symbol-specific
- Some symbols may have more market closure periods
- API may return different data formats for different symbols

---

## Impact Assessment

### Current Behavior

- **Skip Rate**: 83% for some symbols (390/469, 468/547)
- **Error Rate**: 12.5-14.7% (above 10% threshold)
- **Data Collection**: Still functional, but with reduced data coverage

### Expected vs Actual

- **Expected**: Some skipped records during market closure (normal)
- **Actual**: Very high skip rates (83%+) suggesting either:
  1. Extended market closure periods
  2. API returning incomplete data
  3. Data format issues

---

## Solutions Implemented

### 1. Improved Logging

**File**: `src/dgas/data/models.py`

**Changes**:
- Convert records to list once (avoid multiple iterations)
- Track skip reasons (which OHLC fields are missing)
- Only warn if skip rate > 5% OR skipped count > 100
- Log skip rate percentage
- Provide reason summary in warning messages

**Benefits**:
- Better visibility into why records are skipped
- Reduced log spam for normal market closure periods
- More actionable error messages

### 2. Diagnostic Script

**File**: `scripts/diagnose_ohlc_validation.py`

**Purpose**: Analyze API responses to understand skip patterns

**Features**:
- Fetches raw API response
- Analyzes missing data patterns
- Tests parsing with `IntervalData.from_api_list()`
- Shows examples of problematic records

---

## Recommendations

### Immediate Actions

1. **Monitor Skip Patterns**: Use improved logging to identify:
   - Which symbols have high skip rates
   - Which OHLC fields are most commonly missing
   - Whether skips correlate with market hours

2. **Investigate Problem Symbols**: Focus on symbols with >50% skip rates:
   - Check if they're delisted or inactive
   - Verify API response format
   - Test with different date ranges

3. **Review Error Threshold**: Current 10% threshold may be too low if market closure periods are expected. Consider:
   - Adjusting threshold based on market hours
   - Different thresholds for different symbols
   - Time-based thresholds (higher during market closure)

### Long-term Improvements

1. **Market Hours Awareness**: 
   - Only expect valid OHLC during trading hours
   - Adjust skip rate expectations based on time of day
   - Filter out market closure periods before validation

2. **Symbol Status Tracking**:
   - Track which symbols are active/delisted
   - Skip inactive symbols or handle differently
   - Update symbol status from exchange data

3. **API Response Validation**:
   - Validate API response format before parsing
   - Handle different response formats gracefully
   - Retry with different parameters if response is unexpected

4. **Data Quality Metrics**:
   - Track skip rates per symbol over time
   - Alert on unusual patterns (sudden increase in skips)
   - Generate reports on data completeness

---

## Testing

### Test Commands

```bash
# Test specific symbol
cd /opt/DrummondGeometry-evals
uv run python scripts/diagnose_ohlc_validation.py AAPL 30m

# Test problematic symbol
uv run python scripts/diagnose_ohlc_validation.py FI 30m

# Run manual collection to see new logging
uv run dgas data-collection run-once --config config/production.yaml
```

### Expected Improvements

With improved logging, you should now see:
- Skip rate percentages
- Reason summaries (which fields are missing)
- Only warnings for significant skip rates (>5% or >100 records)
- Debug-level logs for normal market closure periods

---

## Next Steps

1. **Restart Data Collection**: Restart the service to see improved logging
2. **Monitor Logs**: Watch for new warning messages with skip rate and reasons
3. **Identify Patterns**: Determine if high skip rates correlate with:
   - Specific symbols
   - Market closure periods
   - API errors
4. **Adjust Configuration**: Based on findings, adjust error thresholds or handling

---

## Related Files

- `src/dgas/data/models.py`: OHLC validation logic
- `src/dgas/data/client.py`: EODHD API client
- `src/dgas/data/bar_aggregator.py`: Bar aggregation logic
- `src/dgas/data/collection_service.py`: Data collection service
- `scripts/diagnose_ohlc_validation.py`: Diagnostic tool

---

**Status**: ✅ Improved logging implemented  
**Next Action**: Restart data collection service and monitor new logs
