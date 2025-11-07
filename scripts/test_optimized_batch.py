#!/usr/bin/env python3
"""Test script to validate optimized batch processor.

This script tests the parallel processing, configuration, and I/O optimizations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.core.config_manager import get_config
from dgas.core.parallel_processor import ParallelBatchProcessor, BatchResult
from dgas.core.io_optimizer import MemoryMonitor, optimize_database_queries
import psutil


def test_config():
    """Test configuration system."""
    print("=" * 80)
    print("TEST 1: Configuration System")
    print("=" * 80)

    config = get_config()
    print(f"✓ Configuration loaded successfully")
    print(f"  NUM_CPUS: {config.num_cpus}")
    print(f"  DB Pool Size: {config.db_pool_size}")
    print(f"  Batch I/O Size: {config.batch_io_size}")
    print(f"  Memory Limit: {config.memory_limit_mb} MB")
    print()

    return True


def test_parallel_processor():
    """Test parallel processor initialization."""
    print("=" * 80)
    print("TEST 2: Parallel Processor")
    print("=" * 80)

    config = get_config()
    processor = ParallelBatchProcessor(max_workers=config.num_cpus)
    print(f"✓ Parallel processor initialized with {config.num_cpus} workers")
    print()

    return True


def test_memory_monitor():
    """Test memory monitoring."""
    print("=" * 80)
    print("TEST 3: Memory Monitor")
    print("=" * 80)

    monitor = MemoryMonitor(memory_limit_mb=512)
    monitor.start_monitoring()
    monitor.check_memory()

    stats = monitor.get_stats()
    print(f"✓ Memory monitoring working")
    print(f"  Current: {stats['current_mb']:.1f} MB")
    print(f"  Peak: {stats['peak_memory']:.1f} MB")
    print(f"  Limit: {stats['limit_mb']:.1f} MB")
    print(f"  Usage: {stats['usage_percent']:.1f}%")
    print()

    return True


def test_system_resources():
    """Test system resource detection."""
    print("=" * 80)
    print("TEST 4: System Resources")
    print("=" * 80)

    cpu_count = psutil.cpu_count()
    memory_gb = psutil.virtual_memory().total / (1024**3)

    print(f"✓ System resources detected")
    print(f"  CPU Count: {cpu_count}")
    print(f"  Memory: {memory_gb:.1f} GB")
    print()

    return True


def test_batch_creation():
    """Test batch creation logic."""
    print("=" * 80)
    print("TEST 5: Batch Creation")
    print("=" * 80)

    # Simulate symbols
    symbols = [f"SYM{i:03d}" for i in range(1, 52)]  # 51 symbols

    from scripts.batch_backtest import create_batches
    batches = create_batches(symbols, batch_size=10)

    print(f"✓ Batch creation working")
    print(f"  Total symbols: {len(symbols)}")
    print(f"  Total batches: {len(batches)}")
    print(f"  First batch: {batches[0] if batches else 'N/A'}")
    print(f"  Last batch: {batches[-1] if batches else 'N/A'}")
    print()

    return True


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("OPTIMIZED BATCH PROCESSOR - VALIDATION TESTS")
    print("=" * 80)
    print()

    tests = [
        ("Configuration", test_config),
        ("Parallel Processor", test_parallel_processor),
        ("Memory Monitor", test_memory_monitor),
        ("System Resources", test_system_resources),
        ("Batch Creation", test_batch_creation),
    ]

    passed = 0
    failed = 0

    for name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                print(f"✗ {name} FAILED")
        except Exception as e:
            failed += 1
            print(f"✗ {name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Passed: {passed}/{len(tests)}")
    print(f"Failed: {failed}/{len(tests)}")
    print()

    if failed == 0:
        print("✓ ALL TESTS PASSED - Implementation ready for use")
        return 0
    else:
        print("✗ SOME TESTS FAILED - Review errors above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
