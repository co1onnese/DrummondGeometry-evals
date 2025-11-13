#!/usr/bin/env python3
"""
Backfill initial data for symbols that don't have any data yet.
This is needed before the data collection service can do incremental updates.
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

def get_symbols_needing_backfill(interval: str = "5m", limit: int = None) -> list[str]:
    """Get symbols that don't have any data for the given interval."""
    symbols_needing_backfill = []
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all active symbols
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            all_symbols = [row[0] for row in cur.fetchall()]
            
            print(f"Checking {len(all_symbols)} symbols for existing {interval} data...")
            
            for symbol in all_symbols:
                try:
                    symbol_id = ensure_market_symbol(conn, symbol, "US")
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                    
                    if latest_ts is None:
                        symbols_needing_backfill.append(symbol)
                except Exception as e:
                    print(f"  Warning: Error checking {symbol}: {e}")
                    # Include it anyway - better to try than skip
                    symbols_needing_backfill.append(symbol)
    
    if limit:
        symbols_needing_backfill = symbols_needing_backfill[:limit]
    
    return symbols_needing_backfill

def backfill_symbols(
    symbols: list[str],
    interval: str = "5m",
    days_back: int = 90,  # Backfill last 90 days
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
):
    """Backfill data for symbols that need initial data."""
    
    if not symbols:
        print("No symbols need backfilling!")
        return
    
    # Calculate date range
    end_date = datetime.now(timezone.utc).date()
    start_date = (end_date - timedelta(days=days_back))
    
    print(f"\n{'='*70}")
    print(f"Backfilling {interval} data for {len(symbols)} symbols")
    print(f"Date range: {start_date.isoformat()} to {end_date.isoformat()}")
    print(f"Batch size: {batch_size}, Delay: {delay_between_batches}s")
    print(f"{'='*70}\n")
    
    # Initialize API client
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    total_fetched = 0
    total_stored = 0
    successful = 0
    failed_symbols = []
    
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
                summary = backfill_intraday(
                    symbol=symbol,
                    exchange="US",
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                    interval=interval,
                    client=api,
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                batch_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars stored")
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
        
        # Rate limiting: wait between batches
        if batch_end < len(symbols):
            print(f"  Waiting {delay_between_batches}s before next batch...")
            time.sleep(delay_between_batches)
    
    api.close()
    
    # Summary
    print(f"\n{'='*70}")
    print("BACKFILL SUMMARY")
    print(f"{'='*70}")
    print(f"Total symbols processed: {len(symbols)}")
    print(f"Successful: {successful}")
    print(f"Failed: {len(failed_symbols)}")
    print(f"Total bars fetched: {total_fetched}")
    print(f"Total bars stored: {total_stored}")
    
    if failed_symbols:
        print(f"\nFailed symbols ({len(failed_symbols)}):")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Backfill initial data for symbols without data")
    parser.add_argument(
        "--interval",
        default="5m",
        help="Data interval (default: 5m)",
        choices=["1m", "5m", "15m", "30m", "1h"]
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=90,
        help="Number of days to backfill (default: 90)"
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
        "--limit",
        type=int,
        help="Limit number of symbols to backfill (for testing)"
    )
    
    args = parser.parse_args()
    
    print("Finding symbols that need initial backfill...")
    symbols = get_symbols_needing_backfill(interval=args.interval, limit=args.limit)
    
    if not symbols:
        print("✓ All symbols already have data!")
        sys.exit(0)
    
    print(f"Found {len(symbols)} symbols needing backfill")
    
    backfill_symbols(
        symbols=symbols,
        interval=args.interval,
        days_back=args.days_back,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
    )
