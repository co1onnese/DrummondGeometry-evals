"""Parallel batch processor for running multiple backtest batches concurrently."""

from __future__ import annotations

import time
import concurrent.futures
from typing import List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class BatchResult:
    """Result of processing a batch."""

    batch_num: int
    success: bool
    elapsed_seconds: float
    error_msg: Optional[str] = None
    symbols: Optional[List[str]] = None


class ParallelBatchProcessor:
    """Process multiple backtest batches in parallel."""

    def __init__(self, max_workers: int):
        """Initialize with maximum number of worker processes.

        Args:
            max_workers: Maximum number of parallel workers (should match NUM_CPUS)
        """
        self.max_workers = max_workers
        self._start_time = None
        self._completed_batches = 0
        self._total_batches = 0

    def process_batches(
        self,
        batches: List[Tuple[int, List[str]]],
        batch_processor_func,
    ) -> List[BatchResult]:
        """Process batches in parallel.

        Args:
            batches: List of (batch_num, symbols) tuples
            batch_processor_func: Function to process a single batch

        Returns:
            List of BatchResult objects in completion order
        """
        self._start_time = time.time()
        self._completed_batches = 0
        self._total_batches = len(batches)

        results: List[BatchResult] = []
        pending_futures = []

        # Use ProcessPoolExecutor for true multi-core parallelism
        with concurrent.futures.ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all batches
            for batch_num, symbols in batches:
                future = executor.submit(batch_processor_func, batch_num, symbols, self._total_batches)
                pending_futures.append((future, batch_num))

            # Process completed batches as they finish
            for future, batch_num in pending_futures:
                try:
                    result = future.result()
                    results.append(result)
                    self._completed_batches += 1
                    self._log_progress(batch_num, result.success, result.elapsed_seconds)
                except Exception as e:
                    # Handle worker exceptions
                    result = BatchResult(
                        batch_num=batch_num,
                        success=False,
                        elapsed_seconds=0.0,
                        error_msg=f"Worker exception: {str(e)}",
                    )
                    results.append(result)
                    self._completed_batches += 1
                    self._log_progress(batch_num, False, 0.0, error=str(e))

        return results

    def _log_progress(
        self,
        batch_num: int,
        success: bool,
        elapsed_seconds: float,
        error: Optional[Exception] = None,
    ):
        """Log batch completion progress."""
        self._start_time = self._start_time or time.time()
        current_time = time.time()
        elapsed_total = current_time - self._start_time

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Calculate ETA
        if self._completed_batches > 0:
            avg_time_per_batch = elapsed_total / self._completed_batches
            remaining_batches = self._total_batches - self._completed_batches
            eta_seconds = avg_time_per_batch * remaining_batches
            eta_minutes = eta_seconds / 60
            eta_str = f", ETA: {eta_minutes:.1f} min"
        else:
            eta_str = ""

        status = "✓" if success else "✗"
        error_str = f" - {error}" if error else ""

        print(
            f"[{timestamp}] Batch {batch_num}/{self._total_batches}: {status} "
            f"Complete in {elapsed_seconds:.1f}s "
            f"({self._completed_batches}/{self._total_batches} done{eta_str}){error_str}"
        )


def run_backtest_batch_subprocess(
    batch_num: int,
    symbols: List[str],
    total_batches: int,
) -> BatchResult:
    """Run a single batch of backtests using subprocess.

    This is the worker function that runs in a separate process.
    It uses subprocess to call the dgas CLI command.

    Args:
        batch_num: Batch number (1-indexed)
        symbols: List of symbols to process
        total_batches: Total number of batches

    Returns:
        BatchResult with success status and timing
    """
    from pathlib import Path
    import subprocess

    start_time = time.time()

    # Build command
    symbols_str = " ".join(symbols)
    log_file = Path(f"/tmp/parallel_batch_{batch_num:03d}.log")

    cmd = [
        "dgas",
        "backtest",
        *symbols,
        "--interval", "30m",
        "--htf", "1d",
        "--start", "2025-05-01",
        "--end", "2025-05-31",
        "--initial-capital", "100000",
        "--commission-rate", "0.0",
        "--slippage-bps", "1",
        "--strategy", "multi_timeframe",
        "--strategy-param", "max_risk_fraction=0.02",
        "--output-format", "summary",
    ]

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    symbols_display = ", ".join(symbols[:5]) + ("..." if len(symbols) > 5 else "")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        elapsed = time.time() - start_time
        success = result.returncode == 0

        # Write log file
        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - {len(symbols)} symbols\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.2f} seconds\n")
            f.write(f"Symbols: {symbols_str}\n\n")
            f.write("STDOUT:\n")
            f.write(result.stdout)
            f.write("\n\nSTDERR:\n")
            f.write(result.stderr)

        return BatchResult(
            batch_num=batch_num,
            success=success,
            elapsed_seconds=elapsed,
            error_msg=result.stderr if not success else None,
            symbols=symbols,
        )

    except subprocess.TimeoutExpired:
        elapsed = time.time() - start_time
        error_msg = f"Batch {batch_num} timed out after {elapsed:.1f}s"

        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - TIMEOUT\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.2f} seconds\n")
            f.write(f"Error: {error_msg}\n")

        return BatchResult(
            batch_num=batch_num,
            success=False,
            elapsed_seconds=elapsed,
            error_msg=error_msg,
            symbols=symbols,
        )

    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = f"Batch {batch_num} failed: {str(e)}"

        with log_file.open("w") as f:
            f.write(f"Batch {batch_num} - EXCEPTION\n")
            f.write(f"Start Time: {timestamp}\n")
            f.write(f"Elapsed Time: {elapsed:.2f} seconds\n")
            f.write(f"Error: {error_msg}\n")

        return BatchResult(
            batch_num=batch_num,
            success=False,
            elapsed_seconds=elapsed,
            error_msg=error_msg,
            symbols=symbols,
        )
