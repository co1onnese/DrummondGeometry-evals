#!/usr/bin/env python3
"""Check data freshness and collection status."""

from dgas.db import get_connection
from datetime import datetime, timezone, timedelta

with get_connection() as conn:
    with conn.cursor() as cur:
        # Check recent collection runs
        print("=== Recent Collection Runs ===")
        cur.execute("""
            SELECT run_timestamp, interval_type, symbols_requested, 
                   symbols_updated, bars_stored, execution_time_ms, status, error_count
            FROM data_collection_runs 
            ORDER BY run_timestamp DESC 
            LIMIT 10
        """)
        rows = cur.fetchall()
        for r in rows:
            print(f"{r[0]} | {r[1]} | {r[2]} symbols | {r[3]} updated | {r[4]} bars | {r[5]}ms | {r[6]} | {r[7]} errors")
        
        # Check data freshness for today and yesterday
        print("\n=== Data Freshness Check ===")
        now = datetime.now(timezone.utc)
        today = now.date()
        yesterday = today - timedelta(days=1)
        
        cur.execute("""
            SELECT s.symbol, MAX(md.timestamp) as latest_timestamp
            FROM market_symbols s
            LEFT JOIN market_data md ON s.symbol_id = md.symbol_id AND md.interval_type = '30m'
            WHERE s.is_active = true
            GROUP BY s.symbol
            ORDER BY latest_timestamp DESC NULLS LAST
            LIMIT 20
        """)
        rows = cur.fetchall()
        
        symbols_with_today = 0
        symbols_with_yesterday = 0
        symbols_stale = 0
        symbols_no_data = 0
        
        print(f"\nCurrent time: {now}")
        print(f"Today: {today}, Yesterday: {yesterday}\n")
        
        for r in rows:
            symbol, latest = r
            if latest:
                if latest.tzinfo is None:
                    latest = latest.replace(tzinfo=timezone.utc)
                latest_date = latest.date()
                age_hours = (now - latest).total_seconds() / 3600.0
                
                if latest_date == today:
                    symbols_with_today += 1
                    status = "✓ TODAY"
                elif latest_date == yesterday:
                    symbols_with_yesterday += 1
                    status = "✓ YESTERDAY"
                elif age_hours > 24:
                    symbols_stale += 1
                    status = f"✗ STALE ({age_hours:.1f}h)"
                else:
                    status = f"✓ RECENT ({age_hours:.1f}h)"
                
                print(f"{symbol}: {latest} ({status})")
            else:
                symbols_no_data += 1
                print(f"{symbol}: No data")
        
        # Summary
        print(f"\n=== Summary ===")
        print(f"Symbols with today's data: {symbols_with_today}")
        print(f"Symbols with yesterday's data: {symbols_with_yesterday}")
        print(f"Symbols with stale data (>24h): {symbols_stale}")
        print(f"Symbols with no data: {symbols_no_data}")
        
        # Check if we have data from today or yesterday
        cur.execute("""
            SELECT COUNT(DISTINCT s.symbol) as count
            FROM market_symbols s
            JOIN market_data md ON s.symbol_id = md.symbol_id AND md.interval_type = '30m'
            WHERE s.is_active = true 
            AND md.timestamp >= %s
        """, (datetime.combine(yesterday, datetime.min.time()).replace(tzinfo=timezone.utc),))
        row = cur.fetchone()
        recent_count = row[0] if row else 0
        
        cur.execute("SELECT COUNT(*) FROM market_symbols WHERE is_active = true")
        total_symbols = cur.fetchone()[0]
        
        print(f"\nSymbols with data from yesterday or today: {recent_count}/{total_symbols}")
        if recent_count < total_symbols * 0.9:
            print(f"⚠️  WARNING: Only {recent_count}/{total_symbols} symbols have recent data!")
