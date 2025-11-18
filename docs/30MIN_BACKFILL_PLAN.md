# 30-Minute Data Backfill Plan (Past 48 Hours)

## Problem Statement

The data quality report shows missing 30-minute interval data over the past 48 hours. This plan outlines the strategy to identify and backfill the missing data.

## Objectives

1. Identify all symbols with missing 30min data in the past 48 hours
2. Backfill missing data efficiently while respecting API rate limits
3. Verify data completeness after backfill
4. Minimize impact on ongoing data collection service

## Analysis Phase

### Step 1: Generate Data Quality Report
```bash
# Generate detailed report to identify gaps
/root/.local/bin/uv run dgas report data-quality --interval 30min --output /tmp/data_quality_report.md

# Or get JSON format for programmatic analysis
/root/.local/bin/uv run dgas report data-quality --interval 30min --format json > /tmp/data_quality.json
```

### Step 2: Identify Affected Symbols
The data quality report shows `estimated_missing_bars` per symbol. We need to:
- Filter symbols where `estimated_missing_bars > 0` for the past 48 hours
- Calculate the actual date range that needs backfilling (last 48 hours from now)
- Account for market hours (data may not exist for non-trading hours)

### Step 3: Determine Backfill Strategy
- **Recent data (today/yesterday)**: Use `incremental_update_intraday()` with `use_live_data=True` (faster, more up-to-date)
- **Historical data (2+ days ago)**: Use `backfill_intraday()` with historical endpoint
- **Gap filling**: Use `backfill_intraday()` for specific date ranges where gaps are detected

## Implementation Plan

### Option A: Smart Incremental Update (Recommended)
**Best for**: Symbols that have some data but are missing recent bars

**Approach**:
1. Use `incremental_update_intraday()` which automatically:
   - Fetches recent data (today/yesterday) via live endpoint
   - Fetches historical data (2+ days ago) if needed
   - Filters out duplicates and older bars
   - Handles API rate limiting

**Advantages**:
- Leverages existing, tested code
- Automatically handles live vs historical endpoints
- Respects API delays (won't request data that isn't finalized)
- Efficient (only fetches what's needed)

**Script**: Create `scripts/backfill_30min_past_48h.py`

### Option B: Targeted Date Range Backfill
**Best for**: Known gaps in specific date ranges

**Approach**:
1. Calculate exact date range (48 hours ago to now)
2. Use `backfill_intraday()` for each symbol with:
   - `start_date`: 48 hours ago (or last known timestamp)
   - `end_date`: Today
   - `use_live_for_today=True`: Use live endpoint for today's data

**Advantages**:
- Precise control over date ranges
- Can backfill specific gaps
- Works well when you know exact missing periods

**Script**: Extend existing `scripts/backfill_to_latest.py`

### Option C: Hybrid Approach (Recommended for Production)
**Best for**: Comprehensive coverage with minimal API calls

**Approach**:
1. **Phase 1**: Run incremental update for all active symbols (catches most gaps)
2. **Phase 2**: Identify remaining gaps from data quality report
3. **Phase 3**: Targeted backfill for specific date ranges where gaps persist

## Detailed Implementation: Option A (Smart Incremental Update)

### Script: `scripts/backfill_30min_past_48h.py`

```python
#!/usr/bin/env python3
"""
Backfill missing 30-minute data for the past 48 hours.

This script:
1. Identifies symbols with missing data in the past 48 hours
2. Uses incremental_update_intraday() to efficiently backfill
3. Provides progress tracking and summary statistics
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import incremental_update_intraday
from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, ensure_market_symbol
from dgas.monitoring.report import generate_ingestion_report
from dgas.settings import get_settings

def get_symbols_with_missing_data(
    interval: str = "30m",
    hours_back: int = 48,
    min_missing_bars: int = 1
) -> list[tuple[str, datetime | None]]:
    """
    Identify symbols with missing data in the past N hours.
    
    Returns:
        List of (symbol, latest_timestamp) tuples for symbols needing backfill
    """
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    symbols_needing_backfill = []
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all active symbols
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            all_symbols = [row[0] for row in cur.fetchall()]
            
            print(f"Checking {len(all_symbols)} symbols for missing {interval} data in past {hours_back} hours...")
            
            for symbol in all_symbols:
                try:
                    symbol_id = ensure_market_symbol(conn, symbol, "US")
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                    
                    # Need backfill if:
                    # 1. No data exists
                    # 2. Latest data is older than cutoff_time
                    if latest_ts is None or latest_ts < cutoff_time:
                        symbols_needing_backfill.append((symbol, latest_ts))
                except Exception as e:
                    print(f"  Warning: Error checking {symbol}: {e}")
                    # Include it anyway - better to try than skip
                    symbols_needing_backfill.append((symbol, None))
    
    print(f"Found {len(symbols_needing_backfill)} symbols needing backfill")
    return symbols_needing_backfill

def backfill_past_48h(
    interval: str = "30m",
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
    hours_back: int = 48,
):
    """
    Backfill missing 30min data for the past 48 hours.
    
    Args:
        interval: Data interval (default: 30m)
        batch_size: Number of symbols to process per batch
        delay_between_batches: Delay in seconds between batches (for rate limiting)
        hours_back: Hours to look back for missing data (default: 48)
    """
    # Step 1: Identify symbols needing backfill
    symbols_to_backfill = get_symbols_with_missing_data(
        interval=interval,
        hours_back=hours_back,
    )
    
    if not symbols_to_backfill:
        print("✓ All symbols have recent data!")
        return
    
    symbols = [s[0] for s in symbols_to_backfill]
    print(f"\nBackfilling {len(symbols)} symbols...")
    print(f"Interval: {interval}")
    print(f"Batch size: {batch_size}, Delay: {delay_between_batches}s")
    print("=" * 70)
    
    # Initialize API client
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    total_fetched = 0
    total_stored = 0
    failed_symbols = []
    successful_symbols = []
    
    # Process in batches
    for batch_start in range(0, len(symbols), batch_size):
        batch_end = min(batch_start + batch_size, len(symbols))
        batch = symbols[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        total_batches = (len(symbols) + batch_size - 1) // batch_size
        
        print(f"\n[Batch {batch_num}/{total_batches}] Processing symbols {batch_start+1}-{batch_end}...")
        batch_start_time = time.time()
        
        for symbol in batch:
            try:
                # Use incremental_update_intraday which:
                # - Fetches recent data (today/yesterday) via live endpoint
                # - Fetches historical data (2+ days ago) if needed
                # - Automatically filters duplicates
                summary = incremental_update_intraday(
                    symbol=symbol,
                    exchange="US",
                    interval=interval,
                    buffer_days=2,  # Fetch 2 days of buffer for historical
                    client=api,
                    use_live_data=True,  # Use live endpoint for today's data
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars stored (fetched: {summary.fetched})")
                    successful_symbols.append(symbol)
                elif summary.fetched == 0:
                    print(f"  ○ {symbol}: no new data available")
                else:
                    print(f"  ○ {symbol}: {summary.fetched} fetched, 0 stored (duplicates)")
                    
            except Exception as e:
                print(f"  ✗ {symbol}: ERROR - {str(e)[:100]}")
                failed_symbols.append((symbol, str(e)))
        
        batch_elapsed = time.time() - batch_start_time
        print(f"[Batch {batch_num}] Completed in {batch_elapsed:.1f}s")
        
        # Rate limiting
        if batch_end < len(symbols):
            print(f"Waiting {delay_between_batches}s before next batch...")
            time.sleep(delay_between_batches)
    
    api.close()
    
    # Print summary
    print("\n" + "=" * 70)
    print("BACKFILL SUMMARY")
    print("=" * 70)
    print(f"Interval: {interval}")
    print(f"Time range: Past {hours_back} hours")
    print(f"Symbols processed: {len(symbols)}")
    print(f"Successful: {len(successful_symbols)}")
    print(f"Failed: {len(failed_symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    
    if failed_symbols:
        print("\nFailed symbols:")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error[:80]}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Backfill missing 30-minute data for the past 48 hours"
    )
    parser.add_argument(
        "--interval",
        default="30m",
        help="Data interval (default: 30m)",
        choices=["1m", "5m", "15m", "30m", "1h"]
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=48,
        help="Hours to look back for missing data (default: 48)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Symbols per batch (default: 50)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=45.0,
        help="Delay between batches in seconds (default: 45.0)"
    )
    
    args = parser.parse_args()
    
    backfill_past_48h(
        interval=args.interval,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        hours_back=args.hours_back,
    )
```

## Execution Steps

### 1. Pre-Backfill Verification
```bash
# Check current data quality
/root/.local/bin/uv run dgas report data-quality --interval 30min --format json > /tmp/before_backfill.json

# Count symbols with missing data
python3 -c "
import json
with open('/tmp/before_backfill.json') as f:
    data = json.load(f)
    missing = [s for s in data if s['estimated_missing_bars'] > 0]
    print(f'Symbols with missing bars: {len(missing)}')
    print(f'Total missing bars: {sum(s[\"estimated_missing_bars\"] for s in missing)}')
"
```

### 2. Run Backfill
```bash
# Run the backfill script
/root/.local/bin/uv run python scripts/backfill_30min_past_48h.py \
    --interval 30m \
    --hours-back 48 \
    --batch-size 50 \
    --delay 45.0
```

### 3. Post-Backfill Verification
```bash
# Check data quality after backfill
/root/.local/bin/uv run dgas report data-quality --interval 30min --format json > /tmp/after_backfill.json

# Compare results
python3 -c "
import json
with open('/tmp/before_backfill.json') as f:
    before = json.load(f)
with open('/tmp/after_backfill.json') as f:
    after = json.load(f)

before_missing = sum(s['estimated_missing_bars'] for s in before)
after_missing = sum(s['estimated_missing_bars'] for s in after)
improvement = before_missing - after_missing

print(f'Missing bars before: {before_missing}')
print(f'Missing bars after: {after_missing}')
print(f'Improvement: {improvement} bars ({improvement/before_missing*100:.1f}% reduction)')
"
```

## Rate Limiting Considerations

- **EODHD API Limits**: Typically 20 requests/minute for free tier, higher for paid
- **Batch Size**: 50 symbols per batch (adjust based on API tier)
- **Delay Between Batches**: 45 seconds (adjust based on API tier and batch size)
- **Estimated Time**: 
  - ~50 symbols per batch
  - ~2-3 seconds per symbol (with API calls)
  - ~2-3 minutes per batch
  - For 500 symbols: ~20-30 minutes total

## Monitoring During Execution

### Real-time Progress
The script outputs:
- Batch progress (Batch X/Y)
- Per-symbol results (✓ success, ○ no data, ✗ error)
- Batch completion time
- Running totals

### Check Data Collection Service Status
```bash
# Ensure data collection service is running (won't conflict)
/root/.local/bin/uv run dgas data-collection status

# If needed, pause during backfill (optional)
# /root/.local/bin/uv run dgas data-collection stop
```

## Troubleshooting

### Issue: Many symbols failing
**Solution**: 
- Reduce batch size (e.g., `--batch-size 25`)
- Increase delay between batches (e.g., `--delay 60.0`)
- Check API rate limits

### Issue: Still missing data after backfill
**Possible Causes**:
1. Data not available from API yet (within 2-3 hour delay window)
2. Market was closed (no data exists for non-trading hours)
3. Symbol delisted or suspended

**Solution**:
- Wait 2-3 hours after market close and retry
- Check if symbol is still active: `SELECT * FROM market_symbols WHERE symbol = 'SYMBOL'`
- Verify API has data: Test with `EODHDClient.fetch_intraday()` directly

### Issue: Duplicate data warnings
**Normal**: The script uses `bulk_upsert_market_data()` which handles duplicates automatically. Warnings are informational.

## Alternative: Use Existing Scripts

If you prefer to use existing infrastructure:

### Option 1: Use `backfill_to_latest.py`
```bash
# This backfills from last DB date to latest API date
/root/.local/bin/uv run python scripts/backfill_to_latest.py
```

### Option 2: Use Data Collection Service
```bash
# The data collection service uses incremental_update_intraday
# Just ensure it's running and it will catch up
/root/.local/bin/uv run dgas data-collection run-once
```

## Success Criteria

1. ✅ All active symbols have data within the past 48 hours
2. ✅ `estimated_missing_bars` is 0 or minimal for all symbols
3. ✅ Data quality report shows recent `last_timestamp` for all symbols
4. ✅ No API rate limit errors during execution

## Next Steps After Backfill

1. **Verify Data Quality**: Run data quality report and confirm gaps are filled
2. **Monitor Data Collection**: Ensure data collection service continues running
3. **Set Up Alerts**: Consider monitoring for future data gaps
4. **Document**: Update runbook with backfill procedures

## Notes

- The backfill script is **safe to run** alongside the data collection service
- `incremental_update_intraday()` automatically filters duplicates
- The script respects API rate limits with configurable delays
- Market hours are automatically handled (no data for non-trading hours is expected)
