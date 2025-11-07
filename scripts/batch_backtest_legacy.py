#!/usr/bin/env python3
"""Batch processing script for full universe backtesting.

This script processes all 517 symbols in batches to avoid performance
degradation issues when processing large numbers of symbols at once.
"""

from __future__ import annotations

import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection


def get_all_symbols() -> List[str]:
    """Fetch all symbols with 30m data from database."""
    with get_connection() as conn:
        cursor = conn.execute(
            """
            SELECT DISTINCT ms.symbol
            FROM market_symbols ms
            JOIN market_data md ON ms.symbol_id = md.symbol_id
            WHERE md.interval_type = '30m'
            AND ms.is_active = TRUE
            ORDER BY ms.symbol
            """
        )
        return [row[0] for row in cursor.fetchall()]


def create_batches(symbols: List[str], batch_size: int = 10) -> List[List[str]]:
    """Split symbols into batches."""
    batches = []
    for i in range(0, len(symbols), batch_size):
        batches.append(symbols[i : i + batch_size])
    return batches


def run_backtest_batch(symbols: List[str], batch_num: int, total_batches: int) -> tuple[bool, str]:
    """Run backtest for a batch of symbols."""
    symbols_str = " ".join(symbols)
    log_file = Path(f"/tmp/batch_{batch_num:03d}.log")

    cmd = [
        "dgas",
        "backtest",
        *symbols,
        "--interval", "30m",
        "--htf", "1d",
        "--start", "2025-05-01",
        "--end", "2025-11-06",
        "--initial-capital", "100000",
        "--commission-rate", "0.0",
        "--slippage-bps", "1",
        "--strategy", "multi_timeframe",
        "--strategy-param", "max_risk_fraction=0.02",
        "--output-format", "summary",
    ]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] Batch {batch_num}/{total_batches}: {len(symbols)} symbols - Starting...")

    start_time = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout per batch
        )

        elapsed = time.time() - start_time
        success = result.returncode == 0

        # Write output to log file
        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - {len(symbols)} symbols\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.2f} seconds\n")
            f.write(f"Symbols: {symbols_str}\n\n")
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\n\nSTDERR:\n")
            f.write(result.stderr)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if success:
            print(f"[{timestamp}] Batch {batch_num}/{total_batches}: ✓ Complete in {elapsed:.1f}s")
        else:
            print(f"[{timestamp}] Batch {batch_num}/{total_batches}: ✗ FAILED in {elapsed:.1f}s")
            print(f"  Error: {result.stderr[:200]}")

        return success, result.stderr

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_msg = f"Batch {batch_num} timed out after {elapsed:.1f}s"

        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - TIMEOUT\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.1f} seconds\n")
            f.write(f"Error: {error_msg}\n")

        print(f"[{timestamp}] Batch {batch_num}/{total_batches}: ✗ TIMEOUT after {elapsed:.1f}s")
        return False, error_msg

    except Exception as e:
        elapsed = time.time() - start_time
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_msg = f"Batch {batch_num} failed with exception: {str(e)}"

        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - EXCEPTION\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.1f} seconds\n")
            f.write(f"Error: {error_msg}\n")

        print(f"[{timestamp}] Batch {batch_num}/{total_batches}: ✗ EXCEPTION - {str(e)}")
        return False, error_msg


def main():
    """Main execution function."""
    print("=" * 80)
    print("BATCH BACKTEST PROCESSOR")
    print("=" * 80)
    print()

    # Get all symbols
    print("Fetching symbols from database...")
    symbols = get_all_symbols()
    print(f"Found {len(symbols)} symbols\n")

    # Create batches
    batch_size = 10
    batches = create_batches(symbols, batch_size)
    total_batches = len(batches)

    print(f"Processing {len(symbols)} symbols in {total_batches} batches of {batch_size}")
    print(f"Date Range: 2025-05-01 to 2025-11-06 (6 months)")
    print(f"Timeframe: 30m with 1d HTF")
    print()

    # Track results
    start_time = time.time()
    successful_batches = 0
    failed_batches = 0
    failed_batch_details = []

    # Process each batch
    for i, batch in enumerate(batches, 1):
        success, error_msg = run_backtest_batch(batch, i, total_batches)

        if success:
            successful_batches += 1
        else:
            failed_batches += 1
            failed_batch_details.append((i, batch, error_msg))

        # Brief pause between batches
        time.sleep(1)

    # Final summary
    elapsed_total = time.time() - start_time

    print()
    print("=" * 80)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Total Time: {elapsed_total:.1f} seconds ({elapsed_total/60:.1f} minutes)")
    print(f"Successful Batches: {successful_batches}/{total_batches}")
    print(f"Failed Batches: {failed_batches}/{total_batches}")
    print()

    if failed_batches > 0:
        print("FAILED BATCHES:")
        for batch_num, batch, error in failed_batch_details:
            print(f"  Batch {batch_num}: {', '.join(batch)}")
            print(f"    Error: {error[:100]}")
        print()

    # Check results in database
    with get_connection() as conn:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM backtest_results WHERE created_at >= NOW() - INTERVAL '%s seconds'",
            (elapsed_total,),
        )
        results_count = cursor.fetchone()[0]

    print(f"Backtest results in database: {results_count}/{len(symbols)} symbols")
    print()

    if results_count >= len(symbols) * 0.95:
        print("✓ SUCCESS: >=95% of symbols completed")
        return 0
    elif results_count >= len(symbols) * 0.85:
        print("⚠ WARNING: 85-95% completion rate")
        return 1
    else:
        print("✗ FAILURE: <85% completion rate")
        return 2


if __name__ == "__main__":
    sys.exit(main())
