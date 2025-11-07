#!/usr/bin/env python3
"""Test version of batch processing - process first 20 symbols only."""

from __future__ import annotations

import sys
import time
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection


def get_first_n_symbols(n: int = 20) -> list[str]:
    """Fetch first N symbols from database."""
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
        all_symbols = [row[0] for row in cursor.fetchall()]
        return all_symbols[:n]


def run_test():
    """Run test with first 20 symbols."""
    print("TEST BATCH PROCESSOR - 20 symbols\n")

    symbols = get_first_n_symbols(20)
    print(f"Symbols: {', '.join(symbols[:10])}...")
    print()

    # Create 2 batches of 10 each
    batch1 = symbols[:10]
    batch2 = symbols[10:20]

    all_symbols = " ".join(symbols)
    log_file = Path("/tmp/test_batch.log")

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

    start_time = time.time()
    print(f"Starting test at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("Processing 20 symbols in 2 batches...\n")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout
        )

        elapsed = time.time() - start_time

        # Write output to log file
        with log_file.open("w") as f:
            f.write(f"Test Batch - 20 symbols\n")
            f.write(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Elapsed Time: {elapsed:.2f} seconds\n")
            f.write(f"\nSTDOUT:\n")
            f.write(result.stdout)
            f.write(f"\n\nSTDERR:\n")
            f.write(result.stderr)

        if result.returncode == 0:
            print(f"✓ TEST COMPLETE in {elapsed:.1f}s ({elapsed/20:.1f}s per symbol)")
            print(result.stdout)
            return 0
        else:
            print(f"✗ TEST FAILED in {elapsed:.1f}s")
            print(f"Error: {result.stderr[:200]}")
            return 1

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        print(f"✗ TEST TIMED OUT after {elapsed:.1f}s")
        return 1


if __name__ == "__main__":
    sys.exit(run_test())
