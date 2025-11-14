#!/usr/bin/env python3
"""Check data collection status and diagnose issues."""

from dgas.db import get_connection
from datetime import datetime, timezone, timedelta

with get_connection() as conn:
    with conn.cursor() as cur:
        # Check recent collection runs
        cur.execute("""
            SELECT run_timestamp, interval_type, symbols_requested, 
                   symbols_updated, bars_stored, execution_time_ms, status, error_count
            FROM data_collection_runs 
            ORDER BY run_timestamp DESC 
            LIMIT 10
        """)
        rows = cur.fetchall()
        
        print("Recent Collection Runs:")
        print("=" * 100)
        for r in rows:
            print(f"{r[0]} | {r[1]} | {r[2]} symbols | {r[3]} updated | {r[4]} bars | {r[5]}ms | {r[6]} | {r[7]} errors")
        
        # Check data freshness
        print("\n\nData Freshness Check (sample symbols):")
        print("=" * 100)
        cur.execute("""
            SELECT s.symbol, MAX(md.timestamp) as latest_timestamp
            FROM market_symbols s
            LEFT JOIN market_data md ON s.symbol_id = md.symbol_id AND md.interval_type = '30m'
            WHERE s.is_active = true
            GROUP BY s.symbol
            ORDER BY latest_timestamp ASC NULLS FIRST
            LIMIT 20
        """)
        rows = cur.fetchall()
        now = datetime.now(timezone.utc)
        for r in rows:
            symbol, latest = r
            if latest:
                # Handle timezone-aware and naive datetimes
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                age = (now - latest).total_seconds() / 3600.0
                print(f"{symbol}: {latest} ({age:.1f} hours ago)")
            else:
                print(f"{symbol}: No data")
