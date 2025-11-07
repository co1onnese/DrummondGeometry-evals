#!/usr/bin/env python3
"""
Bulk historical data backfill for index constituents.
Backfills 30m and Daily data for specified symbols with progress tracking.
"""

import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import backfill_intraday, backfill_eod, IngestionSummary
from dgas.db import get_connection
from dgas.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_symbols_to_backfill(
    index_filter: Optional[str] = None,
    limit: Optional[int] = None
) -> List[tuple[str, str]]:
    """
    Get list of symbols to backfill from database.

    Args:
        index_filter: Filter by index membership (SP500, NASDAQ100, or None for all)
        limit: Maximum number of symbols to return

    Returns:
        List of (symbol, index_membership) tuples
    """
    logger.info(f"Fetching symbols from database (index={index_filter}, limit={limit})...")

    with get_connection() as conn:
        if index_filter:
            query = """
                SELECT symbol, index_membership
                FROM market_symbols
                WHERE %s = ANY(index_membership) AND is_active = TRUE
                ORDER BY symbol
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor = conn.execute(query, (index_filter,))
        else:
            query = """
                SELECT symbol, index_membership
                FROM market_symbols
                WHERE is_active = TRUE
                ORDER BY symbol
            """
            if limit:
                query += f" LIMIT {limit}"
            cursor = conn.execute(query)

        symbols = [(row[0], row[1]) for row in cursor.fetchall()]

    logger.info(f"Found {len(symbols)} symbols to backfill")
    return symbols


def update_backfill_status(
    symbol: str,
    interval: str,
    status: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    bars_fetched: int = 0,
    bars_stored: int = 0,
    quality_score: Optional[float] = None,
    error_message: Optional[str] = None
) -> None:
    """
    Update backfill status in database.

    Args:
        symbol: Stock symbol
        interval: Data interval
        status: Status (pending, in_progress, completed, failed)
        start_date: Start date of backfill
        end_date: End date of backfill
        bars_fetched: Number of bars fetched from API
        bars_stored: Number of bars stored in database
        quality_score: Data quality score (0.0-1.0)
        error_message: Error message if failed
    """
    with get_connection() as conn:
        query = """
            INSERT INTO backfill_status (
                symbol, interval, status, start_date, end_date,
                bars_fetched, bars_stored, quality_score, error_message,
                last_attempt, completed_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(),
                    CASE WHEN %s = 'completed' THEN NOW() ELSE NULL END, NOW())
            ON CONFLICT (symbol, interval) DO UPDATE SET
                status = EXCLUDED.status,
                start_date = EXCLUDED.start_date,
                end_date = EXCLUDED.end_date,
                bars_fetched = EXCLUDED.bars_fetched,
                bars_stored = EXCLUDED.bars_stored,
                quality_score = EXCLUDED.quality_score,
                error_message = EXCLUDED.error_message,
                last_attempt = EXCLUDED.last_attempt,
                completed_at = EXCLUDED.completed_at,
                updated_at = EXCLUDED.updated_at
        """
        conn.execute(
            query,
            (symbol, interval, status, start_date, end_date,
             bars_fetched, bars_stored, quality_score, error_message, status)
        )


def calculate_quality_score(summary: IngestionSummary) -> float:
    """
    Calculate quality score from ingestion summary.

    Args:
        summary: Ingestion summary

    Returns:
        Quality score from 0.0 to 1.0
    """
    if summary.fetched == 0:
        return 0.0

    # Base score on data stored vs fetched
    storage_ratio = summary.stored / summary.fetched if summary.fetched > 0 else 0

    # Penalize for duplicates and gaps
    quality = summary.quality
    duplicate_penalty = (quality.duplicate_count / summary.fetched) if summary.fetched > 0 else 0
    gap_penalty = (quality.gap_count / summary.fetched) if summary.fetched > 0 else 0

    score = storage_ratio * (1.0 - duplicate_penalty - gap_penalty)
    return max(0.0, min(1.0, score))


def backfill_symbol(
    symbol: str,
    interval: str,
    start_date: str,
    end_date: str,
    client: EODHDClient
) -> tuple[bool, Optional[str]]:
    """
    Backfill data for a single symbol and interval.

    Args:
        symbol: Stock symbol
        interval: Data interval (30m, 1d, etc.)
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        client: EODHD client

    Returns:
        Tuple of (success, error_message)
    """
    logger.info(f"Backfilling {symbol} {interval} from {start_date} to {end_date}...")

    # Mark as in progress
    update_backfill_status(symbol, interval, "in_progress", start_date, end_date)

    try:
        # Route to appropriate backfill function based on interval
        is_daily = interval.lower() in ["1d", "daily", "1day", "d"]

        if is_daily:
            # Use EOD endpoint for daily data
            summary = backfill_eod(
                symbol,
                exchange="US",
                start_date=start_date,
                end_date=end_date,
                client=client
            )
        else:
            # Use intraday endpoint for intraday data
            summary = backfill_intraday(
                symbol,
                exchange="US",
                start_date=start_date,
                end_date=end_date,
                interval=interval,
                client=client
            )

        # Calculate quality score
        quality_score = calculate_quality_score(summary)

        # Update status
        if summary.stored > 0:
            update_backfill_status(
                symbol, interval, "completed",
                start_date, end_date,
                summary.fetched, summary.stored,
                quality_score, None
            )
            logger.info(f"✓ {symbol} {interval}: {summary.stored} bars stored (quality: {quality_score:.2f})")
            return True, None
        else:
            error_msg = "No data stored"
            update_backfill_status(
                symbol, interval, "failed",
                start_date, end_date,
                summary.fetched, 0,
                0.0, error_msg
            )
            logger.warning(f"✗ {symbol} {interval}: {error_msg}")
            return False, error_msg

    except Exception as e:
        error_msg = str(e)
        update_backfill_status(
            symbol, interval, "failed",
            start_date, end_date,
            0, 0, 0.0, error_msg
        )
        logger.error(f"✗ {symbol} {interval}: {error_msg}")
        return False, error_msg


def backfill_batch(
    symbols: List[tuple[str, str]],
    intervals: List[str],
    start_date: str,
    end_date: str,
    batch_size: int = 10,
    sleep_between_batches: float = 1.0
) -> dict:
    """
    Backfill data for multiple symbols in batches.

    Args:
        symbols: List of (symbol, index_membership) tuples
        intervals: List of intervals to backfill
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        batch_size: Number of symbols per batch
        sleep_between_batches: Sleep time between batches (seconds)

    Returns:
        Dictionary with summary statistics
    """
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)

    total_symbols = len(symbols)
    total_tasks = total_symbols * len(intervals)

    completed = 0
    failed = 0
    start_time = time.time()

    try:
        for idx, (symbol, indices) in enumerate(symbols, 1):
            logger.info(f"\n[{idx}/{total_symbols}] Processing {symbol} [{', '.join(indices)}]")

            for interval in intervals:
                success, error = backfill_symbol(symbol, interval, start_date, end_date, client)

                if success:
                    completed += 1
                else:
                    failed += 1

                # Progress update
                total_done = (idx - 1) * len(intervals) + intervals.index(interval) + 1
                progress_pct = (total_done / total_tasks) * 100
                logger.info(f"Progress: {total_done}/{total_tasks} ({progress_pct:.1f}%)")

            # Batch sleep
            if idx % batch_size == 0 and idx < total_symbols:
                logger.info(f"Batch complete. Sleeping {sleep_between_batches}s...")
                time.sleep(sleep_between_batches)

    finally:
        client.close()

    elapsed = time.time() - start_time
    elapsed_minutes = elapsed / 60

    stats = {
        "total_symbols": total_symbols,
        "total_tasks": total_tasks,
        "completed": completed,
        "failed": failed,
        "elapsed_seconds": elapsed,
        "elapsed_minutes": elapsed_minutes,
        "tasks_per_minute": total_tasks / elapsed_minutes if elapsed_minutes > 0 else 0
    }

    return stats


def print_summary(stats: dict) -> None:
    """Print backfill summary."""
    logger.info("\n" + "=" * 60)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total symbols:   {stats['total_symbols']}")
    logger.info(f"Total tasks:     {stats['total_tasks']}")
    logger.info(f"Completed:       {stats['completed']}")
    logger.info(f"Failed:          {stats['failed']}")
    logger.info(f"Success rate:    {(stats['completed']/stats['total_tasks']*100):.1f}%")
    logger.info(f"Elapsed time:    {stats['elapsed_minutes']:.1f} minutes")
    logger.info(f"Tasks/minute:    {stats['tasks_per_minute']:.1f}")
    logger.info("=" * 60)


def main():
    """Main execution function."""
    import argparse

    parser = argparse.ArgumentParser(description="Backfill historical data for index constituents")
    parser.add_argument(
        "--symbols", nargs="+",
        help="Specific symbols to backfill (default: all from database)"
    )
    parser.add_argument(
        "--index", choices=["SP500", "NASDAQ100"],
        help="Filter symbols by index membership"
    )
    parser.add_argument(
        "--limit", type=int,
        help="Limit number of symbols to backfill (for testing)"
    )
    parser.add_argument(
        "--intervals", nargs="+", default=["30m", "1d"],
        help="Intervals to backfill (default: 30m 1d)"
    )
    parser.add_argument(
        "--start-date", default="2024-01-01",
        help="Start date (YYYY-MM-DD, default: 2024-01-01)"
    )
    parser.add_argument(
        "--end-date",
        help="End date (YYYY-MM-DD, default: today)"
    )
    parser.add_argument(
        "--batch-size", type=int, default=10,
        help="Batch size (default: 10)"
    )

    args = parser.parse_args()

    # Default end date to today
    if not args.end_date:
        args.end_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    logger.info("Starting backfill process...")
    logger.info(f"Date range: {args.start_date} to {args.end_date}")
    logger.info(f"Intervals: {', '.join(args.intervals)}")

    # Get symbols to backfill
    if args.symbols:
        # Use specific symbols provided
        symbols = [(sym, []) for sym in args.symbols]
        logger.info(f"Using {len(symbols)} symbols from command line")
    else:
        # Get from database
        symbols = get_symbols_to_backfill(args.index, args.limit)

    if not symbols:
        logger.error("No symbols to backfill")
        return 1

    # Run backfill
    stats = backfill_batch(
        symbols,
        args.intervals,
        args.start_date,
        args.end_date,
        args.batch_size
    )

    # Print summary
    print_summary(stats)

    # Return error code if there were failures
    return 1 if stats["failed"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
