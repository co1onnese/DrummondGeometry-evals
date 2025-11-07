"""Database connection pool for optimized resource usage."""

from __future__ import annotations

import os
import queue
import threading
from typing import Optional
from contextlib import contextmanager

try:
    import psycopg2
    from psycopg2 import pool as pg_pool
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

# Get database connection parameters from environment
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_NAME = os.getenv('DB_NAME', 'drummond_geometry')
DB_USER = os.getenv('DB_USER', 'postgres')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')


class DatabaseConnectionPool:
    """Simple connection pool using queue."""

    def __init__(self, pool_size: int = 10):
        """Initialize connection pool.

        Args:
            pool_size: Maximum number of connections in pool
        """
        self.pool_size = pool_size
        self._connection_queue = queue.Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._initialized = False

    def initialize(self):
        """Initialize the connection pool with connections."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            # Create initial connections
            for _ in range(min(self.pool_size, 5)):
                conn = self._create_connection()
                if conn:
                    self._connection_queue.put(conn)

            self._initialized = True

    def _create_connection(self):
        """Create a new database connection."""
        try:
            import psycopg2
            return psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD,
            )
        except Exception as e:
            print(f"Warning: Could not create database connection: {e}")
            return None

    @contextmanager
    def get_connection(self, timeout: float = 30.0):
        """Get a connection from the pool.

        Args:
            timeout: Timeout in seconds to wait for a connection

        Yields:
            Database connection
        """
        conn = None
        try:
            # Try to get from pool
            try:
                conn = self._connection_queue.get(timeout=timeout)
            except queue.Empty:
                # Pool exhausted, create new connection
                conn = self._create_connection()
                if conn is None:
                    raise RuntimeError("Could not create database connection")

            yield conn

        finally:
            if conn:
                try:
                    # Return to pool
                    if not self._connection_queue.full():
                        self._connection_queue.put(conn)
                except Exception:
                    # Connection broken, discard
                    pass

    def close_all(self):
        """Close all connections in the pool."""
        while not self._connection_queue.empty():
            try:
                conn = self._connection_queue.get_nowait()
                conn.close()
            except Exception:
                pass


# Global connection pool instance
_CONNECTION_POOL: Optional[DatabaseConnectionPool] = None


def get_connection_pool(pool_size: Optional[int] = None) -> DatabaseConnectionPool:
    """Get or create the global connection pool.

    Args:
        pool_size: Optional pool size override

    Returns:
        DatabaseConnectionPool instance
    """
    global _CONNECTION_POOL

    if _CONNECTION_POOL is None:
        # Get pool size from environment or use default
        if pool_size is None:
            from .config_manager import get_config
            config = get_config()
            pool_size = config.db_pool_size

        _CONNECTION_POOL = DatabaseConnectionPool(pool_size=pool_size)
        _CONNECTION_POOL.initialize()

    return _CONNECTION_POOL


def close_connection_pool():
    """Close the global connection pool."""
    global _CONNECTION_POOL
    if _CONNECTION_POOL:
        _CONNECTION_POOL.close_all()
        _CONNECTION_POOL = None


# Context manager for backward compatibility
@contextmanager
def get_pooled_connection(timeout: float = 30.0):
    """Get a connection from the pool.

    This provides backward compatibility with the existing get_connection function.

    Args:
        timeout: Timeout in seconds

    Yields:
        Database connection
    """
    pool = get_connection_pool()
    with pool.get_connection(timeout=timeout) as conn:
        yield conn
