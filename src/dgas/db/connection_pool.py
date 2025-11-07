"""Database connection pooling for improved performance.

This module provides connection pooling to reduce the overhead of creating
new database connections for each query, improving prediction cycle performance.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

import psycopg
from psycopg_pool import AsyncConnectionPool, ConnectionPool

from ..settings import Settings, get_settings

logger = logging.getLogger(__name__)


class PooledConnectionManager:
    """
    Manages a pool of PostgreSQL connections for improved performance.

    Uses psycopg3's connection pool to reuse connections across queries,
    reducing connection overhead especially important for prediction cycles
    processing multiple symbols.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize connection pool manager.

        Args:
            settings: Application settings (uses default if None)
        """
        if settings is None:
            settings = get_settings()

        self.settings = settings
        self._pool: Optional[ConnectionPool] = None
        self._async_pool: Optional[AsyncConnectionPool] = None

    def initialize_pool(
        self,
        min_size: int = 5,
        max_size: int = 20,
        max_inactive_connection_lifetime: float = 300.0,
    ) -> None:
        """
        Initialize the connection pool.

        Args:
            min_size: Minimum number of connections in pool
            max_size: Maximum number of connections in pool
            max_inactive_connection_lifetime: Maximum lifetime of inactive connections (seconds)
        """
        if self._pool is not None:
            logger.warning("Connection pool already initialized")
            return

        conninfo = self.settings.database_url
        if "+psycopg" in conninfo:
            conninfo = conninfo.replace("+psycopg", "", 1)

        try:
            self._pool = ConnectionPool(
                conninfo=conninfo,
                min_size=min_size,
                max_size=max_size,
                max_inactive_connection_lifetime=max_inactive_connection_lifetime,
                kwargs={
                    "autocommit": False,
                    "row_factory": psycopg.rows.dict_row,
                },
            )

            # Open all connections in the pool
            self._pool.wait()

            logger.info(
                f"Connection pool initialized: {min_size}-{max_size} connections"
            )

        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise

    def get_pool(self) -> ConnectionPool:
        """
        Get the connection pool.

        Returns:
            The connection pool instance

        Raises:
            RuntimeError: If pool not initialized
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call initialize_pool() first."
            )
        return self._pool

    @contextmanager
    def get_connection(self) -> Generator[psycopg.Connection, None, None]:
        """
        Get a connection from the pool.

        Usage:
            with pool_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT * FROM market_symbols")
                    ...

        Yields:
            A database connection from the pool
        """
        if self._pool is None:
            raise RuntimeError(
                "Connection pool not initialized. Call initialize_pool() first."
            )

        with self._pool.connection() as conn:
            yield conn

    async def get_async_pool(self) -> AsyncConnectionPool:
        """
        Get the async connection pool.

        Returns:
            The async connection pool instance

        Raises:
            RuntimeError: If pool not initialized
        """
        if self._async_pool is None:
            raise RuntimeError("Async pool not initialized")
        return self._async_pool

    async def initialize_async_pool(
        self,
        min_size: int = 5,
        max_size: int = 20,
        max_inactive_connection_lifetime: float = 300.0,
    ) -> None:
        """
        Initialize the async connection pool.

        Args:
            min_size: Minimum number of connections in pool
            max_size: Maximum number of connections in pool
            max_inactive_connection_lifetime: Maximum lifetime of inactive connections
        """
        if self._async_pool is not None:
            logger.warning("Async connection pool already initialized")
            return

        conninfo = self.settings.database_url
        if "+psycopg" in conninfo:
            conninfo = conninfo.replace("+psycopg", "", 1)

        try:
            self._async_pool = AsyncConnectionPool(
                conninfo=conninfo,
                min_size=min_size,
                max_size=max_size,
                max_inactive_connection_lifetime=max_inactive_connection_lifetime,
            )

            await self._async_pool.wait()

            logger.info(
                f"Async connection pool initialized: {min_size}-{max_size} connections"
            )

        except Exception as e:
            logger.error(f"Failed to initialize async connection pool: {e}")
            raise

    def close_pool(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            self._pool.close()
            logger.info("Connection pool closed")
            self._pool = None

    async def close_async_pool(self) -> None:
        """Close the async connection pool."""
        if self._async_pool is not None:
            await self._async_pool.close()
            logger.info("Async connection pool closed")
            self._async_pool = None

    def get_stats(self) -> dict[str, int]:
        """
        Get connection pool statistics.

        Returns:
            Dictionary with pool statistics
        """
        if self._pool is None:
            return {"status": "not_initialized"}

        return {
            "pool_size": self._pool.get_pool_size(),
            "checked_in": self._pool.get_checked_out(),
            "checked_out": self._pool.get_checked_in(),
            "max_capacity": self._pool.get_maxsize(),
        }


# Global connection pool manager instance
_pool_manager: Optional[PooledConnectionManager] = None


def get_pool_manager() -> PooledConnectionManager:
    """
    Get the global connection pool manager instance.

    Returns:
        PooledConnectionManager instance
    """
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = PooledConnectionManager()
    return _pool_manager


@contextmanager
def get_db_connection() -> Generator[psycopg.Connection, None, None]:
    """
    Get a database connection from the pool.

    This is a convenience function that uses the global pool manager.

    Usage:
        from dgas.db.connection_pool import get_db_connection

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM market_symbols")
                ...

    Yields:
        A database connection from the pool
    """
    manager = get_pool_manager()
    with manager.get_connection() as conn:
        yield conn


__all__ = [
    "PooledConnectionManager",
    "get_pool_manager",
    "get_db_connection",
]
