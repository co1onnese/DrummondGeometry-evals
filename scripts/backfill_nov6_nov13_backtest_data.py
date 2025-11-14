#!/usr/bin/env python3
"""
Backfill data for Nov 6-13 backtest.

Backfills both 30m and 1d intervals for all active symbols:
- 30m: Nov 1-13 (lookback + trading period)
- 1d: Oct 1 - Nov 13 (HTF lookback + trading period)
"""

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import backfill_intraday, backfill_eod
from dgas.db import get_connection
from dgas.settings import get_settings


def get_all_active_symbols() -> list[str]:
    """Get all active symbols from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]


def backfill_interval(
    symbols: list[str],
    interval: str,
    start_date: str,
    end_date: str,
    batch_size: int = 50,
    delay_between_batches: float = 5.0,
) -> dict:
    """Backfill data for a specific interval.
    
    Args:
        symbols: List of symbols to backfill
        interval: Data interval ("30m" or "1d")
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        batch_size: Symbols per batch
        delay_between_batches: Delay between batches in seconds
        
    Returns:
        Dictionary with backfill statistics
    """
    print(f"\n{'='*80}")
    print(f"BACKFILLING {interval.upper()} DATA")
    print(f"{'='*80}")
    print(f"Date range: {start_date} to {end_date}")
    print(f"Symbols: {len(symbols)}")
    print(f"Batch size: {batch_size}, Delay: {delay_between_batches}s")
    print()
    
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
        
        print(f"[Batch {batch_num}/{total_batches}] Processing {len(batch)} symbols...")
        batch_start_time = time.time()
        batch_stored = 0
        
        for symbol in batch:
            try:
                if interval == "1d":
                    # Use EOD backfill for daily data
                    summary = backfill_eod(
                        symbol=symbol,
                        exchange="US",
                        start_date=start_date,
                        end_date=end_date,
                        client=api,
                    )
                else:
                    # Use intraday backfill for 30m data
                    summary = backfill_intraday(
                        symbol=symbol,
                        exchange="US",
                        start_date=start_date,
                        end_date=end_date,
                        interval=interval,
                        client=api,
                        use_live_for_today=False,  # Use historical data only
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
                    print(f"  ○ {symbol}: No data available from API")
                    skipped_symbols.append(symbol)
                    
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
    
    return {
        "interval": interval,
        "total_symbols": len(symbols),
        "successful": successful,
        "skipped": len(skipped_symbols),
        "failed": len(failed_symbols),
        "total_fetched": total_fetched,
        "total_stored": total_stored,
        "failed_symbols": failed_symbols,
        "skipped_symbols": skipped_symbols,
    }


def print_summary(stats_30m: dict, stats_1d: dict) -> None:
    """Print backfill summary."""
    print("\n" + "="*80)
    print("BACKFILL SUMMARY")
    print("="*80)
    
    print(f"\n30m Interval:")
    print(f"  Symbols processed: {stats_30m['total_symbols']}")
    print(f"  Successful: {stats_30m['successful']}")
    print(f"  Skipped: {stats_30m['skipped']}")
    print(f"  Failed: {stats_30m['failed']}")
    print(f"  Total bars fetched: {stats_30m['total_fetched']:,}")
    print(f"  Total bars stored: {stats_30m['total_stored']:,}")
    
    print(f"\n1d Interval:")
    print(f"  Symbols processed: {stats_1d['total_symbols']}")
    print(f"  Successful: {stats_1d['successful']}")
    print(f"  Skipped: {stats_1d['skipped']}")
    print(f"  Failed: {stats_1d['failed']}")
    print(f"  Total bars fetched: {stats_1d['total_fetched']:,}")
    print(f"  Total bars stored: {stats_1d['total_stored']:,}")
    
    # Show failed symbols
    if stats_30m['failed_symbols']:
        print(f"\n30m Failed symbols ({len(stats_30m['failed_symbols'])}):")
        for symbol, error in stats_30m['failed_symbols'][:10]:
            print(f"  - {symbol}: {error[:80]}")
        if len(stats_30m['failed_symbols']) > 10:
            print(f"  ... and {len(stats_30m['failed_symbols']) - 10} more")
    
    if stats_1d['failed_symbols']:
        print(f"\n1d Failed symbols ({len(stats_1d['failed_symbols'])}):")
        for symbol, error in stats_1d['failed_symbols'][:10]:
            print(f"  - {symbol}: {error[:80]}")
        if len(stats_1d['failed_symbols']) > 10:
            print(f"  ... and {len(stats_1d['failed_symbols']) - 10} more")
    
    print("="*80)


def main() -> int:
    """Main execution function."""
    print("="*80)
    print("BACKFILL DATA FOR NOV 6-13 BACKTEST")
    print("="*80)
    print()
    print("This script will backfill:")
    print("  - 30m data: Nov 1-13 (lookback + trading period)")
    print("  - 1d data: Oct 1 - Nov 13 (HTF lookback + trading period)")
    print()
    
    # Load all active symbols
    symbols = get_all_active_symbols()
    print(f"Loaded {len(symbols)} active symbols from database")
    
    if not symbols:
        print("\n✗ ERROR: No active symbols found in database")
        return 1
    
    # Backfill 30m data (Nov 1-13)
    stats_30m = backfill_interval(
        symbols=symbols,
        interval="30m",
        start_date="2025-11-01",
        end_date="2025-11-13",
        batch_size=50,
        delay_between_batches=5.0,
    )
    
    # Backfill 1d data (Oct 1 - Nov 13)
    stats_1d = backfill_interval(
        symbols=symbols,
        interval="1d",
        start_date="2025-10-01",
        end_date="2025-11-13",
        batch_size=50,
        delay_between_batches=5.0,
    )
    
    # Print summary
    print_summary(stats_30m, stats_1d)
    
    # Return error code if there were failures
    if stats_30m['failed'] > 0 or stats_1d['failed'] > 0:
        print("\n⚠ Some symbols failed to backfill. Check errors above.")
        return 1
    else:
        print("\n✓ Backfill completed successfully!")
        return 0


if __name__ == "__main__":
    import os
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⚠ Backfill interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n✗ FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)
