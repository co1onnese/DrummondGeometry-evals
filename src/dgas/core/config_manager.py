"""Configuration manager for performance optimization."""

from __future__ import annotations

import os
import psutil
from typing import Optional

# Load environment variables if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed, skip


class ServerConfig:
    """Configuration for server resources."""

    def __init__(
        self,
        num_cpus: int,
        db_pool_size: int,
        batch_io_size: int,
        memory_limit_mb: int,
    ):
        self.num_cpus = num_cpus
        self.db_pool_size = db_pool_size
        self.batch_io_size = batch_io_size
        self.memory_limit_mb = memory_limit_mb

    def __repr__(self):
        return (
            f"ServerConfig(num_cpus={self.num_cpus}, "
            f"db_pool_size={self.db_pool_size}, "
            f"batch_io_size={self.batch_io_size}, "
            f"memory_limit_mb={self.memory_limit_mb})"
        )


def get_optimal_config() -> ServerConfig:
    """Auto-detect optimal configuration based on system resources."""
    # Get NUM_CPUS from environment
    num_cpus_env = os.getenv('NUM_CPUS', 'auto').strip().lower()

    if num_cpus_env == 'auto' or not num_cpus_env.isdigit():
        # Auto-detect CPU count
        num_cpus = psutil.cpu_count()
    else:
        # Use environment variable
        num_cpus = min(int(num_cpus_env), psutil.cpu_count())

    # Auto-detect memory
    memory_gb = psutil.virtual_memory().total / (1024**3)

    # Determine configuration based on resources
    if num_cpus >= 12 and memory_gb >= 20:
        # Large server configuration
        num_workers = max(2, num_cpus - 2)  # Leave 2 CPUs for OS/DB
        db_pool_size = min(20, num_workers)
        batch_io_size = 20
        memory_limit_mb = 2048  # 2GB per worker
    elif num_cpus >= 4 and memory_gb >= 8:
        # Medium server configuration
        num_workers = max(1, num_cpus - 1)
        db_pool_size = min(10, num_workers)
        batch_io_size = 15
        memory_limit_mb = 1024  # 1GB per worker
    else:
        # Small server configuration
        num_workers = max(1, min(2, num_cpus - 1))
        db_pool_size = 5
        batch_io_size = 10
        memory_limit_mb = 512  # 512MB per worker

    return ServerConfig(
        num_cpus=num_workers,  # This is the number of workers
        db_pool_size=db_pool_size,
        batch_io_size=batch_io_size,
        memory_limit_mb=memory_limit_mb,
    )


# Global configuration instance
CONFIG: Optional[ServerConfig] = None


def get_config() -> ServerConfig:
    """Get or create the global configuration."""
    global CONFIG
    if CONFIG is None:
        CONFIG = get_optimal_config()
    return CONFIG
