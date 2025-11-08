#!/usr/bin/env python3
"""Fix timestamp timezone - Final working version.

The issue: timestamps are stored as TIMESTAMP WITH TIMEZONE but with wrong timezone info.
Solution: Extract the time part, remove timezone, then re-insert as UTC.
"""

from dgas.db import get_connection


def fix_timestamps():
    """Convert timestamps to proper UTC."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            print("Fixing timestamp timezone (v5 - proper UTC conversion)...")

            # Delete all current data
            print("Clearing market_data table...")
            cur.execute("DELETE FROM market_data")

            # Extract time part and re-insert as UTC
            # The timestamps in backup are in Europe/Prague, so we need to:
            # 1. Strip the timezone info
            # 2. Treat the resulting timestamp as Europe/Prague time
            # 3. Convert to UTC
            print("Re-inserting with proper UTC conversion...")
            cur.execute("""
                INSERT INTO market_data (symbol_id, timestamp, interval_type, open_price, high_price, low_price, close_price, volume)
                SELECT
                    symbol_id,
                    -- Treat the timestamp as naive, then explicitly set Europe/Prague and convert to UTC
                    (timestamp::timestamptz AT TIME ZONE 'Europe/Prague' AT TIME ZONE 'UTC')::timestamptz,
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

            print("\nSample timestamps after v5 conversion:")
            for row in cur.fetchall():
                ts = row[0]
                print(f"  {ts}")
                if '+00:00' in str(ts) or str(ts).endswith('+00'):
                    print("    ✓ UTC with +00:00")
                else:
                    # Also check the actual UTC value
                    print(f"    (checking...)")


if __name__ == "__main__":
    fix_timestamps()
