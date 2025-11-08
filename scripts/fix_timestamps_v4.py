#!/usr/bin/env python3
"""Fix timestamp timezone - Final version.

Store timestamps as UTC with explicit +00:00 timezone.
"""

from dgas.db import get_connection


def fix_timestamps():
    """Convert all market_data timestamps to UTC with +00:00 timezone."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            print("Fixing timestamp timezone (v4 - explicit UTC)...")

            # Get count
            cur.execute("SELECT COUNT(*) FROM market_data")
            total_rows = cur.fetchone()[0]
            print(f"Total rows to update: {total_rows:,}")

            # Delete all current data
            print("Clearing market_data table...")
            cur.execute("DELETE FROM market_data")

            # Re-insert with explicit UTC timezone
            # The key is to ensure PostgreSQL treats these as UTC timestamps
            print("Re-inserting with explicit UTC timezone...")
            cur.execute("""
                INSERT INTO market_data (symbol_id, timestamp, interval_type, open_price, high_price, low_price, close_price, volume)
                SELECT
                    symbol_id,
                    -- Force the timestamp to be in UTC timezone
                    (timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'UTC')::timestamptz,
                    interval_type,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    volume
                FROM market_data_backup
            """)
            conn.commit()

            print(f"✓ Re-inserted {cur.rowcount:,} rows")

            # Verify
            cur.execute("""
                SELECT timestamp
                FROM market_data md
                JOIN market_symbols s ON s.symbol_id = md.symbol_id
                WHERE s.symbol = 'AAPL' AND md.interval_type = '30m'
                ORDER BY md.timestamp
                LIMIT 3
            """)

            print("\nSample timestamps after v4 conversion:")
            for row in cur.fetchall():
                ts = row[0]
                print(f"  {ts}")
                if '+00:00' in str(ts):
                    print("    ✓ UTC timestamp with +00:00")
                else:
                    print(f"    ✗ NOT UTC (+00:00)")


if __name__ == "__main__":
    fix_timestamps()
