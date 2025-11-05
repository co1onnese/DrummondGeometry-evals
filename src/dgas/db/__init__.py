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
    conn = psycopg.connect(settings.database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


__all__ = ["get_connection"]
