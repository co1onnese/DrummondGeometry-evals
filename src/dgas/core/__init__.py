"""Core performance optimization modules."""

from .config_manager import ServerConfig, get_config, get_optimal_config
from .parallel_processor import ParallelBatchProcessor, BatchResult, run_backtest_batch_subprocess
from .connection_pool import DatabaseConnectionPool, get_connection_pool
from .io_optimizer import (
    BatchIOWriter,
    MemoryMonitor,
    ParallelFileWriter,
    optimize_database_queries,
    create_database_indexes,
    get_optimal_batch_size,
)

__all__ = [
    "ServerConfig",
    "get_config",
    "get_optimal_config",
    "ParallelBatchProcessor",
    "BatchResult",
    "run_backtest_batch_subprocess",
    "DatabaseConnectionPool",
    "get_connection_pool",
    "BatchIOWriter",
    "MemoryMonitor",
    "ParallelFileWriter",
    "optimize_database_queries",
    "create_database_indexes",
    "get_optimal_batch_size",
]
