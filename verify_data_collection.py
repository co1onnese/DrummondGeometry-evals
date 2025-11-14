#!/usr/bin/env python3
"""Verify data collection is working properly."""

from dgas.db import get_connection
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.data.ingestion import incremental_update_intraday
from dgas.settings import get_settings
from datetime import datetime, timezone, timedelta

print("=== Data Collection Verification ===\n")

# Check recent collection runs
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT run_timestamp, symbols_updated, bars_stored, status 
            FROM data_collection_runs 
            ORDER BY run_timestamp DESC 
            LIMIT 5
        """)
        rows = cur.fetchall()
        print("Recent Collection Runs:")
        for r in rows:
            print(f"  {r[0]}: {r[1]} updated, {r[2]} bars, {r[3]}")
        
        # Check data freshness for a few symbols
        print("\nData Freshness (sample symbols):")
        cur.execute("""
            SELECT s.symbol, MAX(md.timestamp) as latest
            FROM market_symbols s
            LEFT JOIN market_data md ON s.symbol_id = md.symbol_id AND md.interval_type = '30m'
            WHERE s.is_active = true AND s.symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA')
            GROUP BY s.symbol
            ORDER BY s.symbol
        """)
        rows = cur.fetchall()
        now = datetime.now(timezone.utc)
        for r in rows:
            symbol, latest = r
            if latest:
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age_hours = (now - latest).total_seconds() / 3600.0
                print(f"  {symbol}: {latest} ({age_hours:.1f} hours ago)")
            else:
                print(f"  {symbol}: No data")

# Test incremental update
print("\n=== Testing Incremental Update ===")
settings = get_settings()
client = EODHDClient(EODHDConfig.from_settings(settings))

try:
    summary = incremental_update_intraday(
        'AAPL',
        exchange='US',
        interval='30m',
        buffer_days=2,
        client=client,
        use_live_data=True,
    )
    print(f"AAPL test: fetched={summary.fetched}, stored={summary.stored}")
    if summary.quality.notes:
        print(f"  Notes: {summary.quality.notes}")
except Exception as e:
    print(f"AAPL test failed: {e}")

client.close()
