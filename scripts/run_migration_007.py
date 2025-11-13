#!/usr/bin/env python3
"""Run migration 007: Data collection tracking."""

from pathlib import Path
from dgas.db import get_connection

def main():
    migration_file = Path(__file__).parent.parent / "src" / "dgas" / "migrations" / "007_data_collection_tracking.sql"
    
    print(f"Reading migration file: {migration_file}")
    sql = migration_file.read_text()
    
    print("Connecting to database...")
    with get_connection() as conn:
        with conn.cursor() as cur:
            print("Executing migration...")
            cur.execute(sql)
            conn.commit()
            print("✅ Migration applied successfully!")

if __name__ == "__main__":
    main()
