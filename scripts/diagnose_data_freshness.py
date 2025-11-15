#!/usr/bin/env python3
"""Diagnose why data collection is not producing fresh data."""

import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, get_symbol_id
from dgas.data.ingestion import incremental_update_intraday
from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings

def main():
    settings = get_settings()
    
    print("=== Data Freshness Diagnosis ===\n")
    
    # Check recent collection runs
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT run_timestamp, status, symbols_updated, bars_fetched, bars_stored, execution_time_ms
            FROM data_collection_runs
            ORDER BY run_timestamp DESC
            LIMIT 5
        """)
        runs = cur.fetchall()
        
        print("=== Recent Collection Runs ===")
        now = datetime.now(timezone.utc)
        for r in runs:
            ts = r[0]
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_min = (now - ts).total_seconds() / 60
            print(f"{ts.strftime('%Y-%m-%d %H:%M:%S UTC')} ({age_min:.1f}m ago)")
            print(f"  Status: {r[1]}, Updated: {r[2]}, Fetched: {r[3]}, Stored: {r[4]}, Time: {r[5]/1000:.1f}s\n")
    
    # Check data freshness for a sample symbol
    test_symbol = "AAPL"
    with get_connection() as conn:
        symbol_id = get_symbol_id(conn, test_symbol)
        if symbol_id:
            latest_ts = get_latest_timestamp(conn, symbol_id, "30m")
            if latest_ts:
                if latest_ts.tzinfo is None:
                    latest_ts = latest_ts.replace(tzinfo=timezone.utc)
                age_hours = (datetime.now(timezone.utc) - latest_ts).total_seconds() / 3600
                print(f"=== Sample Symbol: {test_symbol} ===")
                print(f"Latest data: {latest_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} ({age_hours:.1f}h ago)\n")
            else:
                print(f"=== Sample Symbol: {test_symbol} ===")
                print("No data found\n")
    
    # Try to fetch fresh data for test symbol
    print(f"=== Testing Fresh Data Fetch for {test_symbol} ===")
    try:
        config = EODHDConfig.from_settings(settings)
        client = EODHDClient(config)
        
        # Try incremental update
        summary = incremental_update_intraday(
            test_symbol,
            exchange="US",
            interval="30m",
            buffer_days=2,
            client=client,
            use_live_data=True,
        )
        
        print(f"Fetched: {summary.fetched} bars")
        print(f"Stored: {summary.stored} bars")
        print(f"Quality: {summary.quality}")
        
        if summary.fetched > 0:
            print(f"\nFetched bars timestamp range:")
            if hasattr(summary, 'start') and summary.start:
                print(f"  Start: {summary.start}")
            if hasattr(summary, 'end') and summary.end:
                print(f"  End: {summary.end}")
        
        client.close()
        
        # Check if data was updated
        with get_connection() as conn:
            symbol_id = get_symbol_id(conn, test_symbol)
            if symbol_id:
                new_latest_ts = get_latest_timestamp(conn, symbol_id, "30m")
                if new_latest_ts:
                    if new_latest_ts.tzinfo is None:
                        new_latest_ts = new_latest_ts.replace(tzinfo=timezone.utc)
                    age_min = (datetime.now(timezone.utc) - new_latest_ts).total_seconds() / 60
                    print(f"\nNew latest data: {new_latest_ts.strftime('%Y-%m-%d %H:%M:%S UTC')} ({age_min:.1f}m ago)")
                    if new_latest_ts > latest_ts:
                        print("✅ Data was updated!")
                    else:
                        print("⚠️  Data timestamp did not change")
        
    except Exception as e:
        print(f"❌ Error fetching data: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
