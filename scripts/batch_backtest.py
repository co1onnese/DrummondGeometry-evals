#!/usr/bin/env python3
"""Optimized batch processing script for full universe backtesting.

This script processes all 517 symbols in batches using parallel processing
to achieve 5-8× speedup on multi-core servers.

Performance optimizations:
- Multi-core parallel batch processing
- Database connection pooling
- Batch I/O operations
- Memory management
"""

from __future__ import annotations

import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Tuple
import signal
import gc

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.core.config_manager import get_config
from dgas.core.parallel_processor import (
    ParallelBatchProcessor,
    run_backtest_batch_subprocess,
    BatchResult,
)
from dgas.core.io_optimizer import (
    MemoryMonitor,
    optimize_database_queries,
    create_database_indexes,
)


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


def create_batches(symbols: List[str], batch_size: int = 10) -> List[Tuple[int, List[str]]]:
    """Split symbols into batches with numbers.

    Returns:
        List of (batch_num, symbols) tuples
    """
    batches = []
    for i in range(0, len(symbols), batch_size):
        batch_num = i // batch_size + 1
        batch_symbols = symbols[i : i + batch_size]
        batches.append((batch_num, batch_symbols))
    return batches


def main():
    """Main execution function with optimized parallel processing."""
    parser = argparse.ArgumentParser(
        description="Optimized batch backtest processor with parallel processing"
    )
    parser.add_argument(
        "--mode",
        choices=["parallel", "legacy"],
        default="parallel",
        help="Processing mode: parallel (default) or legacy (sequential)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="Number of symbols per batch (default: 10)",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Number of parallel workers (default: auto-detect from NUM_CPUS)",
    )
    args = parser.parse_args()

    # Apply database optimizations
    print("Applying database optimizations...")
    optimize_database_queries()
    create_database_indexes()

    # Get configuration
    config = get_config()
    num_workers = args.num_workers or config.num_cpus

    print("=" * 80)
    print("OPTIMIZED BATCH BACKTEST PROCESSOR")
    print("=" * 80)
    print()
    print(f"Configuration:")
    print(f"  NUM_CPUS: {num_workers} workers")
    print(f"  DB Pool Size: {config.db_pool_size}")
    print(f"  Batch I/O Size: {config.batch_io_size}")
    print(f"  Memory Limit: {config.memory_limit_mb} MB")
    print()

    # Memory monitoring
    memory_monitor = MemoryMonitor(memory_limit_mb=config.memory_limit_mb)
    memory_monitor.start_monitoring()

    # Get all symbols
    print("Fetching symbols from database...")
    symbols = get_all_symbols()
    print(f"Found {len(symbols)} symbols\n")

    # Create batches
    batches = create_batches(symbols, args.batch_size)
    total_batches = len(batches)

    print(f"Processing {len(symbols)} symbols in {total_batches} batches")
    print(f"Date Range: 2025-05-01 to 2025-05-31 (1 month)")
    print(f"Timeframe: 30m with 1d HTF")
    print(f"Mode: {args.mode.upper()}")
    print()

    # Setup signal handler for graceful shutdown
    shutdown_requested = False

    def signal_handler(sig, frame):
        nonlocal shutdown_requested
        shutdown_requested = True
        print("\nShutdown requested. Waiting for current batches to complete...")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Track results
    start_time = time.time()
    successful_batches = 0
    failed_batches = 0
    failed_batch_details = []

    if args.mode == "legacy":
        # Legacy sequential mode
        print("Running in LEGACY sequential mode...\n")

        for i, (batch_num, batch_symbols) in enumerate(batches, 1):
            if shutdown_requested:
                break

            result = run_backtest_batch_subprocess(batch_num, batch_symbols, total_batches)

            if result.success:
                successful_batches += 1
            else:
                failed_batches += 1
                failed_batch_details.append((batch_num, batch_symbols, result.error_msg))

            memory_monitor.check_memory(force_gc=(i % 10 == 0))  # GC every 10 batches

            # Brief pause between batches
            if not shutdown_requested:
                time.sleep(0.5)

    else:
        # Parallel mode (default)
        print(f"Running in PARALLEL mode with {num_workers} workers...\n")

        # Initialize parallel processor
        processor = ParallelBatchProcessor(max_workers=num_workers)

        # Process batches in parallel
        results: List[BatchResult] = processor.process_batches(
            batches, run_backtest_batch_subprocess
        )

        # Count results
        for result in results:
            if result.success:
                successful_batches += 1
            else:
                failed_batches += 1
                failed_batch_details.append(
                    (result.batch_num, result.symbols or [], result.error_msg)
                )

        # Memory stats
        memory_stats = memory_monitor.get_stats()
        print(f"\nMemory Usage: {memory_stats['current_mb']:.1f}MB "
              f"(peak: {memory_stats['current_mb']:.1f}MB, "
              f"limit: {memory_stats['limit_mb']:.1f}MB)")

    # Final summary
    elapsed_total = time.time() - start_time

    print()
    print("=" * 80)
    print("BATCH PROCESSING COMPLETE")
    print("=" * 80)
    print(f"Total Time: {elapsed_total:.1f} seconds ({elapsed_total/60:.1f} minutes)")
    print(f"Successful Batches: {successful_batches}/{total_batches}")
    print(f"Failed Batches: {failed_batches}/{total_batches}")

    if total_batches > 0:
        avg_time_per_batch = elapsed_total / total_batches
        print(f"Average Time per Batch: {avg_time_per_batch:.1f} seconds")

        if args.mode == "parallel":
            speedup_estimate = 27.9 / (elapsed_total / 60)  # Compare to baseline
            print(f"Estimated Speedup: {speedup_estimate:.1f}×")

    print()

    if failed_batches > 0:
        print("FAILED BATCHES:")
        for batch_num, batch, error in failed_batch_details[:10]:  # Show first 10
            symbols_str = ", ".join(batch[:5]) + ("..." if len(batch) > 5 else "")
            print(f"  Batch {batch_num}: {symbols_str}")
            if error:
                print(f"    Error: {error[:150]}")
        if len(failed_batch_details) > 10:
            print(f"  ... and {len(failed_batch_details) - 10} more")
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

    # Final memory cleanup
    gc.collect()

    # Exit code based on success rate
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
