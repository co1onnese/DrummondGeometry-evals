#!/usr/bin/env python3
"""
Register all symbols from full_symbols.txt and collect data for them.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import ensure_market_symbol
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import backfill_intraday, incremental_update_intraday
from dgas.data.repository import get_latest_timestamp
from dgas.settings import get_settings
from datetime import datetime, timedelta, timezone

def load_symbols_from_file(filepath: str) -> list[str]:
    """Load symbols from file.
    
    Handles both formats:
    - One symbol per line
    - All symbols on one line separated by spaces
    """
    with open(filepath, 'r') as f:
        content = f.read().strip()
    
    # If file has newlines, treat as one per line
    if '\n' in content:
        symbols = [line.strip().upper() for line in content.split('\n') if line.strip()]
    else:
        # Otherwise, split by spaces
        symbols = [s.strip().upper() for s in content.split() if s.strip()]
    
    return symbols

def register_symbols(symbols: list[str], exchange: str = "US"):
    """Register all symbols in database."""
    print(f"Registering {len(symbols)} symbols...")
    registered = 0
    skipped = 0
    
    with get_connection() as conn:
        for i, symbol in enumerate(symbols):
            try:
                ensure_market_symbol(conn, symbol, exchange)
                registered += 1
                if (i + 1) % 50 == 0:
                    print(f"  Progress: {i + 1}/{len(symbols)} registered")
            except Exception as e:
                print(f"  ✗ Failed to register {symbol}: {e}")
                skipped += 1
    
    print(f"\nRegistration complete:")
    print(f"  ✓ Registered: {registered}")
    print(f"  ✗ Skipped: {skipped}")
    return registered

def collect_data_for_symbols(
    symbols: list[str],
    interval: str = "30m",
    exchange: str = "US",
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
    days_back: int = 90,
):
    """Collect data for all symbols."""
    print(f"\nCollecting data for {len(symbols)} symbols...")
    print(f"Interval: {interval}, Days back: {days_back}")
    print("=" * 70)
    
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    today = datetime.now(timezone.utc).date()
    start_date = (today - timedelta(days=days_back)).isoformat()
    end_date = today.isoformat()
    
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
                # Check if symbol has recent data
                with get_connection() as conn:
                    symbol_id = ensure_market_symbol(conn, symbol, exchange)
                    latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                # Format symbol for API (add .US suffix if not present)
                api_symbol = symbol if '.' in symbol else f"{symbol}.US"
                
                # Always use backfill_intraday - it handles both new and existing symbols
                # and automatically uses live data for recent dates
                if latest_ts:
                    latest_date = latest_ts.date()
                    # Start from day after latest
                    start = (latest_date + timedelta(days=1)).isoformat()
                else:
                    # No data - start from days_back
                    start = start_date
                
                summary = backfill_intraday(
                    symbol=api_symbol,  # Use formatted symbol
                    exchange=exchange,
                    start_date=start,
                    end_date=end_date,
                    interval=interval,
                    client=api,
                    use_live_for_today=True,  # Use live data for today
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                batch_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars stored")
                    successful += 1
                elif summary.fetched > 0:
                    print(f"  ○ {symbol}: {summary.fetched} fetched, 0 stored (duplicates)")
                    skipped_symbols.append(symbol)
                else:
                    print(f"  ○ {symbol}: No data available")
                    skipped_symbols.append(symbol)
                    
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
    print("DATA COLLECTION SUMMARY")
    print("=" * 70)
    print(f"Symbols processed: {len(symbols)}")
    print(f"Successful: {successful}")
    print(f"Skipped (no data/duplicates): {len(skipped_symbols)}")
    print(f"Failed: {len(failed_symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    
    if skipped_symbols:
        print(f"\nSkipped ({len(skipped_symbols)}):")
        for symbol in skipped_symbols[:10]:
            print(f"  - {symbol}")
        if len(skipped_symbols) > 10:
            print(f"  ... and {len(skipped_symbols) - 10} more")
    
    if failed_symbols:
        print(f"\nFailed ({len(failed_symbols)}):")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error[:80]}")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Register and collect data for symbols from full_symbols.txt")
    parser.add_argument("--file", default="data/full_symbols.txt", help="Symbol file path")
    parser.add_argument("--interval", default="30m", help="Data interval")
    parser.add_argument("--exchange", default="US", help="Exchange code")
    parser.add_argument("--batch-size", type=int, default=50, help="Symbols per batch")
    parser.add_argument("--delay", type=float, default=45.0, help="Delay between batches (seconds)")
    parser.add_argument("--days-back", type=int, default=90, help="Days of historical data to fetch")
    parser.add_argument("--register-only", action="store_true", help="Only register symbols, don't collect data")
    parser.add_argument("--collect-only", action="store_true", help="Only collect data, don't register")
    
    args = parser.parse_args()
    
    # Load symbols
    symbols = load_symbols_from_file(args.file)
    print(f"Loaded {len(symbols)} symbols from {args.file}")
    
    # Register symbols
    if not args.collect_only:
        register_symbols(symbols, exchange=args.exchange)
    
    # Collect data
    if not args.register_only:
        collect_data_for_symbols(
            symbols,
            interval=args.interval,
            exchange=args.exchange,
            batch_size=args.batch_size,
            delay_between_batches=args.delay,
            days_back=args.days_back,
        )
