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
from dgas.settings import get_settings


def get_symbols_with_missing_data(
    interval: str = "30m",
    hours_back: int = 48,
    min_missing_bars: int = 1,
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
            cur.execute(
                "SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol"
            )
            all_symbols = [row[0] for row in cur.fetchall()]

            print(
                f"Checking {len(all_symbols)} symbols for missing {interval} data in past {hours_back} hours..."
            )

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

        print(
            f"\n[Batch {batch_num}/{total_batches}] Processing symbols {batch_start+1}-{batch_end}..."
        )
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
                    print(
                        f"  ✓ {symbol}: {summary.stored} bars stored (fetched: {summary.fetched})"
                    )
                    successful_symbols.append(symbol)
                elif summary.fetched == 0:
                    print(f"  ○ {symbol}: no new data available")
                else:
                    print(
                        f"  ○ {symbol}: {summary.fetched} fetched, 0 stored (duplicates)"
                    )

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
        choices=["1m", "5m", "15m", "30m", "1h"],
    )
    parser.add_argument(
        "--hours-back",
        type=int,
        default=48,
        help="Hours to look back for missing data (default: 48)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Symbols per batch (default: 50)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=45.0,
        help="Delay between batches in seconds (default: 45.0)",
    )

    args = parser.parse_args()

    backfill_past_48h(
        interval=args.interval,
        batch_size=args.batch_size,
        delay_between_batches=args.delay,
        hours_back=args.hours_back,
    )
