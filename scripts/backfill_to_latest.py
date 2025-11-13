#!/usr/bin/env python3
"""
Backfill data to the latest available date from the API.

This script checks what the latest available data is from the API
and backfills from the last date in the database to that date.
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
from dgas.data.repository import get_latest_timestamp, get_symbol_id
from dgas.settings import get_settings

def get_latest_api_date(symbol: str = "AAPL", interval: str = "30m") -> datetime | None:
    """Get the latest available date from the API for a test symbol."""
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)
    
    try:
        # Fetch latest data without date range
        bars = client.fetch_intraday(symbol, interval=interval, limit=10)
        if bars:
            latest = max(bar.timestamp for bar in bars)
            return latest
    except Exception as e:
        print(f"Error fetching latest API date: {e}")
    finally:
        client.close()
    
    return None

def get_latest_db_date(symbol: str = "AAPL", interval: str = "30m") -> datetime | None:
    """Get the latest date in database for a test symbol."""
    with get_connection() as conn:
        symbol_id = get_symbol_id(conn, symbol)
        if symbol_id:
            return get_latest_timestamp(conn, symbol_id, interval)
    return None

def backfill_to_latest(
    symbols_file: str,
    interval: str = "30m",
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
):
    """Backfill data from latest DB date to latest API date."""
    
    # Load symbols
    with open(symbols_file) as f:
        content = f.read().strip()
        symbols = [s.strip().replace('.US', '') for s in content.split() if s.strip()]
    
    print(f"Loaded {len(symbols)} symbols from {symbols_file}")
    
    # Check latest dates
    print("\nChecking latest available dates...")
    latest_api = get_latest_api_date(interval=interval)
    latest_db = get_latest_db_date(interval=interval)
    
    if latest_api is None:
        print("❌ Could not determine latest API date")
        return
    
    print(f"Latest API date: {latest_api.date()}")
    if latest_db:
        print(f"Latest DB date: {latest_db.date()}")
        if latest_db.date() >= latest_api.date():
            print("✓ Database is already up to date!")
            return
        start_date = (latest_db.date() + timedelta(days=1)).isoformat()
    else:
        print("No data in database, starting from API start date")
        # Start from a reasonable date (e.g., 1 year ago or API start)
        start_date = (latest_api.date() - timedelta(days=365)).isoformat()
    
    end_date = latest_api.date().isoformat()
    
    print(f"\nBackfilling from {start_date} to {end_date}")
    print(f"Batch size: {batch_size}, Delay: {delay_between_batches}s")
    print("=" * 70)
    
    # Initialize API client
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    api = EODHDClient(config)
    
    total_fetched = 0
    total_stored = 0
    failed_symbols = []
    
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
                summary = backfill_intraday(
                    symbol=symbol,
                    exchange="US",
                    start_date=start_date,
                    end_date=end_date,
                    interval=interval,
                    client=api,
                )
                
                total_fetched += summary.fetched
                total_stored += summary.stored
                
                if summary.stored > 0:
                    print(f"  ✓ {symbol}: {summary.stored} bars")
                elif summary.fetched == 0:
                    print(f"  ○ {symbol}: no data available")
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
    print(f"Date range: {start_date} to {end_date}")
    print(f"Symbols processed: {len(symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    print(f"Failed symbols: {len(failed_symbols)}")
    
    if failed_symbols:
        print("\nFailed symbols:")
        for symbol, error in failed_symbols[:10]:
            print(f"  - {symbol}: {error[:80]}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")

if __name__ == "__main__":
    import time
    
    symbols_file = "/tmp/symbols_list.txt"
    if not Path(symbols_file).exists():
        # Try the default location
        symbols_file = "/opt/DrummondGeometry-evals/data/full_symbols.txt"
    
    backfill_to_latest(
        symbols_file=symbols_file,
        interval="30m",
        batch_size=50,
        delay_between_batches=45.0,
    )
