#!/usr/bin/env python3
"""
Backfill data from current database state to November 10, 2025.
Uses database symbols and handles gaps intelligently.
"""

import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import backfill_intraday
from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, ensure_market_symbol
from dgas.settings import get_settings

def get_all_active_symbols():
    """Get all active symbols from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]

def backfill_to_nov10(
    interval: str = "30m",
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
    target_date: str = "2025-11-10",
):
    """Backfill data from latest DB date to target date (Nov 10)."""
    
    # Get symbols from database
    symbols = get_all_active_symbols()
    print(f"Loaded {len(symbols)} active symbols from database")
    
    # Check latest dates for a sample
    print("\nChecking current data state...")
    with get_connection() as conn:
        sample_symbols = symbols[:5]
        for symbol in sample_symbols:
            try:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                latest = get_latest_timestamp(conn, symbol_id, interval)
                if latest:
                    print(f"  {symbol}: Latest data = {latest.date()}")
                else:
                    print(f"  {symbol}: No data")
            except Exception as e:
                print(f"  {symbol}: Error - {e}")
    
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    print(f"\nTarget date: {target_date}")
    print(f"Batch size: {batch_size}, Delay: {delay_between_batches}s")
    print("=" * 70)
    
    # Initialize API client
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    total_fetched = 0
    total_stored = 0
    successful = 0
    failed_symbols = []
    skipped_symbols = []
    
    # Process in batches
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
                # Determine start date for this symbol
                with get_connection() as conn:
                    symbol_id = ensure_market_symbol(conn, symbol, "US")
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                if latest_ts:
                    # Start from day after latest data
                    start_date = (latest_ts.date() + timedelta(days=1)).isoformat()
                    # Don't backfill if already at or past target
                    if latest_ts.date() >= target_dt:
                        skipped_symbols.append((symbol, latest_ts.date()))
                        continue
                else:
                    # No existing data - start from 90 days before target
                    start_date = (target_dt - timedelta(days=90)).isoformat()
                
                # Backfill to target date (uses live data for today, historical for past)
                summary = backfill_intraday(
                    symbol=symbol,
                    exchange="US",
                    start_date=start_date,
                    end_date=target_date,
                    interval=interval,
                    client=api,
                    use_live_for_today=True,  # Use live OHLCV for today's data
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                batch_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars stored (from {start_date})")
                    successful += 1
                elif summary.fetched > 0:
                    print(f"  ○ {symbol}: {summary.fetched} fetched, 0 stored (duplicates or no new data)")
                else:
                    print(f"  ○ {symbol}: No data available from API")
                    
            except Exception as e:
                error_msg = str(e)[:100]
                print(f"  ✗ {symbol}: ERROR - {error_msg}")
                failed_symbols.append((symbol, error_msg))
        
        batch_elapsed = time.time() - batch_start_time
        print(f"  Batch {batch_num} completed in {batch_elapsed:.1f}s ({batch_stored} bars stored)")
        
        # Rate limiting
        if batch_end < len(symbols):
            print(f"  Waiting {delay_between_batches}s before next batch...")
            time.sleep(delay_between_batches)
    
    api.close()
    
    # Print summary
    print("\n" + "=" * 70)
    print("BACKFILL SUMMARY")
    print("=" * 70)
    print(f"Target date: {target_date}")
    print(f"Interval: {interval}")
    print(f"Symbols processed: {len(symbols)}")
    print(f"Successful: {successful}")
    print(f"Skipped (already up to date): {len(skipped_symbols)}")
    print(f"Failed: {len(failed_symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    
    if skipped_symbols:
        print(f"\nSkipped symbols (already at target date): {len(skipped_symbols)}")
        for symbol, date in skipped_symbols[:5]:
            print(f"  - {symbol}: {date}")
        if len(skipped_symbols) > 5:
            print(f"  ... and {len(skipped_symbols) - 5} more")
    
    if failed_symbols:
        print(f"\nFailed symbols ({len(failed_symbols)}):")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error[:80]}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill data to November 10, 2025")
    parser.add_argument(
        "--interval",
        default="30m",
        help="Data interval (default: 30m)",
        choices=["1m", "5m", "15m", "30m", "1h"]
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
    parser.add_argument(
        "--target-date",
        default="2025-11-10",
        help="Target date to backfill to (default: 2025-11-10)"
    )
    
    args = parser.parse_args()
    
    backfill_to_nov10(
        interval=args.interval,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        target_date=args.target_date,
    )
