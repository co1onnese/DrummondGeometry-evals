#!/usr/bin/env python3
"""
Monitor backfill progress and check for data gaps.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, ensure_market_symbol

def monitor_progress(target_date: str = "2025-11-10", interval: str = "30m"):
    """Monitor backfill progress."""
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
    
    up_to_date = 0
    stale = 0
    no_data = 0
    
    latest_dates = []
    
    for symbol in symbols:
        try:
            with get_connection() as conn:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                latest_ts = get_latest_timestamp(conn, symbol_id, interval)
                
                if latest_ts:
                    latest_date = latest_ts.date()
                    latest_dates.append(latest_date)
                    if latest_date >= target_dt:
                        up_to_date += 1
                    else:
                        stale += 1
                else:
                    no_data += 1
        except:
            no_data += 1
    
    if latest_dates:
        max_date = max(latest_dates)
        min_date = min(latest_dates)
    else:
        max_date = None
        min_date = None
    
    print(f"\n{'='*70}")
    print(f"BACKFILL PROGRESS MONITOR")
    print(f"{'='*70}")
    print(f"Target date: {target_date}")
    print(f"Interval: {interval}")
    print(f"Total symbols: {len(symbols)}")
    print(f"\nStatus:")
    print(f"  ✓ Up to date (>= {target_date}): {up_to_date} ({up_to_date/len(symbols)*100:.1f}%)")
    print(f"  ⚠ Stale (< {target_date}): {stale} ({stale/len(symbols)*100:.1f}%)")
    print(f"  ✗ No data: {no_data} ({no_data/len(symbols)*100:.1f}%)")
    
    if latest_dates:
        print(f"\nDate range in database:")
        print(f"  Latest: {max_date}")
        print(f"  Earliest: {min_date}")
        days_behind = (target_dt - max_date).days if max_date < target_dt else 0
        print(f"  Days behind target: {days_behind}")
    
    return {
        "total": len(symbols),
        "up_to_date": up_to_date,
        "stale": stale,
        "no_data": no_data,
        "max_date": max_date,
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Monitor backfill progress")
    parser.add_argument("--target-date", default="2025-11-10", help="Target date")
    parser.add_argument("--interval", default="30m", help="Data interval")
    
    args = parser.parse_args()
    
    summary = monitor_progress(target_date=args.target_date, interval=args.interval)
    
    # Exit with error if not complete
    if summary["stale"] > 0 or summary["no_data"] > 0:
        sys.exit(1)
    sys.exit(0)
