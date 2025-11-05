"""Simple migration runner for local PostgreSQL deployments."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import psycopg

from . import get_connection


MIGRATIONS_PACKAGE_PATH = Path(__file__).resolve().parent.parent / "migrations"


def list_migration_files() -> Iterable[Path]:
    """Return migration SQL files ordered by name."""

    if not MIGRATIONS_PACKAGE_PATH.exists():
        return []
    return sorted(MIGRATIONS_PACKAGE_PATH.glob("*.sql"))


def _ensure_migrations_table(cur: psycopg.Cursor) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )


def _get_applied_versions(cur: psycopg.Cursor) -> set[str]:
    cur.execute("SELECT version FROM schema_migrations;")
    return {row[0] for row in cur.fetchall()}


def _apply_migration(cur: psycopg.Cursor, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    cur.execute(sql)
    cur.execute(
        "INSERT INTO schema_migrations (version) VALUES (%s);",
        (path.name,),
    )


def apply_all() -> None:
    """Apply all pending migrations in order."""

    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_migrations_table(cur)
            applied = _get_applied_versions(cur)

            for migration in list_migration_files():
                if migration.name in applied:
                    continue
                _apply_migration(cur, migration)


def main() -> None:
    apply_all()


if __name__ == "__main__":  # pragma: no cover
    main()
