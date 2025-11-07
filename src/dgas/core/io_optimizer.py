"""I/O optimization utilities for batch processing."""

from __future__ import annotations

import os
import gc
import threading
from typing import List, Dict, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from .config_manager import get_config


class BatchIOWriter:
    """Batch database writes for improved performance."""

    def __init__(self, batch_size: int = 20):
        """Initialize batch I/O writer.

        Args:
            batch_size: Number of results to batch before writing
        """
        self.batch_size = batch_size
        self._buffer: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self._total_written = 0
        self._total_batches = 0

    def add_result(self, result: Dict[str, Any]):
        """Add a result to the batch buffer.

        Args:
            result: Dictionary of result data
        """
        with self._lock:
            self._buffer.append(result)

            # Write batch if buffer is full
            if len(self._buffer) >= self.batch_size:
                self._flush_batch()

    def _flush_batch(self):
        """Flush the current batch to database."""
        if not self._buffer:
            return

        try:
            from dgas.db import get_connection

            batch = self._buffer.copy()
            self._buffer.clear()

            with get_connection() as conn:
                for result in batch:
                    conn.execute(
                        """
                        INSERT INTO backtest_results (... columns ...)
                        VALUES (... values ...)
                        ON CONFLICT DO NOTHING
                        """,
                        # ... parameters ...
                    )
                conn.commit()

            self._total_written += len(batch)
            self._total_batches += 1

        except Exception as e:
            # If batch write fails, we could fall back to individual writes
            # For now, just log the error
            print(f"Warning: Batch write failed: {e}")

    def flush_all(self):
        """Flush all remaining results in buffer."""
        with self._lock:
            if self._buffer:
                self._flush_batch()

    def get_stats(self) -> Dict[str, int]:
        """Get I/O statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "total_written": self._total_written,
            "total_batches": self._total_batches,
            "buffer_size": len(self._buffer),
        }


class MemoryMonitor:
    """Monitor and manage memory usage."""

    def __init__(self, memory_limit_mb: int = 1024):
        """Initialize memory monitor.

        Args:
            memory_limit_mb: Memory limit per worker in MB
        """
        self.memory_limit_mb = memory_limit_mb
        self._start_memory = 0
        self._peak_memory = 0
        self._gc_threshold = 700  # Trigger GC at 70% of limit

    def start_monitoring(self):
        """Start memory monitoring."""
        import psutil
        process = psutil.Process(os.getpid())
        self._start_memory = process.memory_info().rss / 1024 / 1024  # MB
        self._peak_memory = self._start_memory

    def check_memory(self, force_gc: bool = False):
        """Check current memory usage and trigger GC if needed.

        Args:
            force_gc: Force garbage collection regardless of threshold
        """
        import psutil
        process = psutil.Process(os.getpid())
        current_memory = process.memory_info().rss / 1024 / 1024  # MB

        self._peak_memory = max(self._peak_memory, current_memory)

        # Trigger GC if memory usage is high or forced
        if force_gc or current_memory > self._gc_threshold:
            gc.collect()

        # Warn if approaching limit
        if current_memory > self.memory_limit_mb * 0.9:
            print(
                f"Warning: Memory usage ({current_memory:.1f}MB) "
                f"approaching limit ({self.memory_limit_mb}MB)"
            )

    def get_stats(self) -> Dict[str, float]:
        """Get memory statistics.

        Returns:
            Dictionary with memory stats
        """
        return {
            "start_mb": self._start_memory,
            "current_mb": self._peak_memory,
            "limit_mb": self.memory_limit_mb,
            "usage_percent": (self._peak_memory / self.memory_limit_mb) * 100,
        }


class ParallelFileWriter:
    """Write results to files in parallel."""

    def __init__(self, max_workers: int = 4):
        """Initialize parallel file writer.

        Args:
            max_workers: Maximum number of parallel file writers
        """
        self.max_workers = max_workers
        self._written_count = 0
        self._lock = threading.Lock()

    def write_results(self, results: List[Dict[str, Any]], output_dir: str = "/tmp"):
        """Write results to files in parallel.

        Args:
            results: List of result dictionaries
            output_dir: Directory to write files
        """
        os.makedirs(output_dir, exist_ok=True)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for result in results:
                future = executor.submit(self._write_single_result, result, output_dir)
                futures.append(future)

            # Wait for all writes to complete
            for future in futures:
                try:
                    future.result()
                    with self._lock:
                        self._written_count += 1
                except Exception as e:
                    print(f"Warning: Failed to write result: {e}")

    def _write_single_result(self, result: Dict[str, Any], output_dir: str):
        """Write a single result to file.

        Args:
            result: Result dictionary
            output_dir: Output directory
        """
        symbol = result.get("symbol", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{output_dir}/result_{symbol}_{timestamp}.json"

        import json

        with open(filename, "w") as f:
            json.dump(result, f, indent=2, default=str)


def optimize_database_queries():
    """Apply database query optimizations.

    This function should be called once at startup to ensure
    the database is configured for optimal performance.
    """
    try:
        from dgas.db import get_connection

        with get_connection() as conn:
            # Set some PostgreSQL optimization parameters
            # These are session-level and safe to set

            # Increase work_mem for better sorting performance
            conn.execute("SET work_mem = '256MB'")

            # Increase random_page_cost for SSD storage
            conn.execute("SET random_page_cost = 1.1")

            # Enable parallel query execution
            conn.execute("SET max_parallel_workers_per_gather = 4")

            # Commit the settings
            conn.commit()

            print("Database optimization parameters applied")

    except Exception as e:
        print(f"Warning: Could not apply database optimizations: {e}")


def create_database_indexes():
    """Create indexes for better query performance."""
    try:
        from dgas.db import get_connection

        with get_connection() as conn:
            # Create index on backtest_results for faster queries
            conn.execute(
                """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_backtest_results_created_at
                ON backtest_results (created_at)
                """
            )

            # Create index on symbol for faster lookups
            conn.execute(
                """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_backtest_results_symbol
                ON backtest_results (symbol)
                """
            )

            # Create index on strategy for filtering
            conn.execute(
                """
                CREATE INDEX CONCURRENTLY IF NOT EXISTS
                idx_backtest_results_strategy
                ON backtest_results (strategy)
                """
            )

            conn.commit()
            print("Database indexes created successfully")

    except Exception as e:
        print(f"Warning: Could not create indexes: {e}")


def get_optimal_batch_size(symbol_count: int, num_workers: int) -> int:
    """Calculate optimal batch size based on system resources.

    Args:
        symbol_count: Total number of symbols to process
        num_workers: Number of parallel workers

    Returns:
        Optimal batch size
    """
    # Target: Each worker should handle 2-3 batches
    target_batches_per_worker = 2.5
    total_target_batches = num_workers * target_batches_per_worker

    # Calculate batch size
    batch_size = max(1, int(symbol_count / total_target_batches))

    # Clamp to reasonable bounds
    batch_size = min(20, max(5, batch_size))

    return batch_size
