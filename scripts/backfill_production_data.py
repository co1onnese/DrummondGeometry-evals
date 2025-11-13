#!/usr/bin/env python3
"""
Production data backfill script for DGAS.
Backfills both 30m and 1h interval data for all symbols through Nov 7, 2025.
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.ingestion import backfill_intraday
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings

def backfill_all_symbols(
    symbols_file: str,
    interval: str,
    start_date: str,
    end_date: str,
    batch_size: int = 50,
    delay_between_batches: float = 45.0,
):
    """
    Backfill data for all symbols in batches.

    Args:
        symbols_file: Path to file with symbol list
        interval: Data interval (30m or 1h)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        batch_size: Number of symbols per batch
        delay_between_batches: Seconds to wait between batches
    """
    # Load symbols - file has all symbols space-separated on one line
    with open(symbols_file) as f:
        content = f.read().strip()
        # Split by whitespace and filter out empty strings
        symbols = [s.strip().replace('.US', '') for s in content.split() if s.strip()]

    print(f"Backfilling {interval} data for {len(symbols)} symbols")
    print(f"Date range: {start_date} to {end_date}")
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

        # Rate limiting: wait between batches
        if batch_end < len(symbols):
            print(f"Waiting {delay_between_batches}s before next batch...")
            time.sleep(delay_between_batches)

    api.close()

    # Print summary
    print("\n" + "=" * 70)
    print("BACKFILL SUMMARY")
    print("=" * 70)
    print(f"Symbols processed: {len(symbols)}")
    print(f"Total bars fetched: {total_fetched:,}")
    print(f"Total bars stored: {total_stored:,}")
    print(f"Failed symbols: {len(failed_symbols)}")

    if failed_symbols:
        print("\nFailed symbols:")
        for symbol, error in failed_symbols[:10]:  # Show first 10
            print(f"  - {symbol}: {error[:80]}")
        if len(failed_symbols) > 10:
            print(f"  ... and {len(failed_symbols) - 10} more")

    return total_stored, failed_symbols


if __name__ == "__main__":
    # Use the production symbols file
    symbols_file = "/opt/DrummondGeometry-evals/data/full_symbols.txt"

    # Check if we should run 30m or 1h backfill
    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        print("Usage: python backfill_production_data.py [30m|1h|both]")
        sys.exit(1)

    if mode == "30m":
        # Backfill Nov 6 and Nov 7 for 30m data (Nov 7 might not be available yet)
        print("Backfilling 30m data for Nov 6-7...")
        print("Note: If Nov 7 data is not available from API, it will be skipped")
        backfill_all_symbols(
            symbols_file=symbols_file,
            interval="30m",
            start_date="2025-11-06",  # Start from Nov 6
            end_date="2025-11-07",     # Try through Nov 7
            batch_size=50,
            delay_between_batches=45.0,
        )
    elif mode == "1h":
        # Backfill entire date range for 1h data
        print("Backfilling 1h data for entire date range...")
        backfill_all_symbols(
            symbols_file=symbols_file,
            interval="1h",
            start_date="2024-01-01",
            end_date="2025-11-07",
            batch_size=30,  # Smaller batches for 1h (more data per symbol)
            delay_between_batches=50.0,
        )
    elif mode == "both":
        # Do both
        print("Backfilling both 30m and 1h data...")
        print("\n### STEP 1: 30m data for Nov 7 ###\n")
        backfill_all_symbols(
            symbols_file=symbols_file,
            interval="30m",
            start_date="2025-11-07",
            end_date="2025-11-07",
            batch_size=50,
            delay_between_batches=45.0,
        )

        print("\n\n### STEP 2: 1h data for entire range ###\n")
        backfill_all_symbols(
            symbols_file=symbols_file,
            interval="1h",
            start_date="2024-01-01",
            end_date="2025-11-07",
            batch_size=30,
            delay_between_batches=50.0,
        )
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: python backfill_production_data.py [30m|1h|both]")
        sys.exit(1)
