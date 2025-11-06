"""Database utilities."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import psycopg

from ..settings import get_settings


@contextmanager
def get_connection() -> Iterator[psycopg.Connection]:
    """Yield a psycopg connection using configured database URL."""

    settings = get_settings()
    conninfo = settings.database_url
    if "+psycopg" in conninfo:
        conninfo = conninfo.replace("+psycopg", "", 1)
    conn = psycopg.connect(conninfo)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


try:
    from .persistence import DrummondPersistence
    __all__ = ["get_connection", "DrummondPersistence"]
except ImportError:
    # psycopg2 not available, DrummondPersistence will be unavailable
    __all__ = ["get_connection"]
