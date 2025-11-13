#!/usr/bin/env python3
"""
Backfill Nov 1-10 using live data for recent dates and historical for gaps.
Uses Live OHLCV for same-day data and Intraday Historical for yesterday's data.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import backfill_intraday, incremental_update_intraday
from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, ensure_market_symbol
from dgas.settings import get_settings

def get_all_active_symbols():
    """Get all active symbols from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]

def backfill_nov1_to_nov10(
    interval: str = "30m",
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
):
    """Backfill Nov 1-10 using live data for recent and historical for gaps."""
    
    symbols = get_all_active_symbols()
    print(f"Backfilling Nov 1-10 for {len(symbols)} symbols")
    print(f"Using: Live OHLCV for recent data, Historical Intraday for past dates")
    print("=" * 70)
    
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    target_date = "2025-11-10"
    start_date = "2025-11-01"
    
    total_fetched = 0
    total_stored = 0
    successful = 0
    failed_symbols = []
    skipped_symbols = []
    
    total_batches = (len(symbols) + batch_size - 1) // batch_size
    
    for batch_start in range(0, len(symbols), batch_size):
        batch_end = min(batch_start + batch_size, len(symbols))
        batch = symbols[batch_start:batch_end]
        batch_num = (batch_start // batch_size) + 1
        
        print(f"\n[Batch {batch_num}/{total_batches}] Processing {len(batch)} symbols...")
        batch_start_time = time.time()
        batch_stored = 0
        
        for symbol in batch:
            try:
                # Check current state
                with get_connection() as conn:
                    symbol_id = ensure_market_symbol(conn, symbol, "US")
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                # Determine what we need
                if latest_ts:
                    latest_date = latest_ts.date()
                    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
                    
                    if latest_date >= target_dt:
                        skipped_symbols.append((symbol, latest_date))
                        continue
                    
                    # Start from day after latest
                    start = (latest_date + timedelta(days=1)).isoformat()
                else:
                    # No data - start from Nov 1
                    start = start_date
                
                # Use backfill_intraday which handles live + historical automatically
                summary = backfill_intraday(
                    symbol=symbol,
                    exchange="US",
                    start_date=start,
                    end_date=target_date,
                    interval=interval,
                    client=api,
                    use_live_for_today=True,  # Use live for recent dates
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                batch_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars stored")
                    successful += 1
                elif summary.fetched > 0:
                    print(f"  ○ {symbol}: {summary.fetched} fetched, 0 stored (duplicates)")
                else:
                    print(f"  ○ {symbol}: No data available")
                    
            except Exception as e:
                error_msg = str(e)[:100]
                print(f"  ✗ {symbol}: ERROR - {error_msg}")
                failed_symbols.append((symbol, error_msg))
        
        batch_elapsed = time.time() - batch_start_time
        print(f"  Batch {batch_num} completed in {batch_elapsed:.1f}s ({batch_stored} bars stored)")
        
        if batch_end < len(symbols):
            print(f"  Waiting {delay_between_batches}s before next batch...")
            time.sleep(delay_between_batches)
    
    api.close()
    
    # Summary
    print("\n" + "=" * 70)
    print("BACKFILL SUMMARY")
    print("=" * 70)
    print(f"Date range: {start_date} to {target_date}")
    print(f"Interval: {interval}")
    print(f"Symbols processed: {len(symbols)}")
    print(f"Successful: {successful}")
    print(f"Skipped (already up to date): {len(skipped_symbols)}")
    print(f"Failed: {len(failed_symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    
    if skipped_symbols:
        print(f"\nSkipped ({len(skipped_symbols)}):")
        for symbol, date in skipped_symbols[:5]:
            print(f"  - {symbol}: {date}")
        if len(skipped_symbols) > 5:
            print(f"  ... and {len(skipped_symbols) - 5} more")
    
    if failed_symbols:
        print(f"\nFailed ({len(failed_symbols)}):")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error[:80]}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill Nov 1-10 with live data")
    parser.add_argument("--interval", default="30m", help="Data interval")
    parser.add_argument("--batch-size", type=int, default=50, help="Symbols per batch")
    parser.add_argument("--delay", type=float, default=45.0, help="Delay between batches")
    
    args = parser.parse_args()
    
    backfill_nov1_to_nov10(
        interval=args.interval,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
    )
