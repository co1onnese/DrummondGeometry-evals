#!/usr/bin/env python3
"""
Check for data gaps in the database up to November 10, 2025.
Reports symbols with missing data or gaps.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from collections import defaultdict

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import get_latest_timestamp, ensure_market_symbol

def check_data_gaps(interval: str = "30m", target_date: str = "2025-11-10"):
    """Check for data gaps up to target date."""
    
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    now = datetime.now(timezone.utc)
    
    print(f"Checking data gaps for {interval} interval up to {target_date}")
    print("=" * 70)
    
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            symbols = [row[0] for row in cur.fetchall()]
    
    print(f"Checking {len(symbols)} symbols...\n")
    
    no_data = []
    gaps = []
    up_to_date = []
    stale = []
    
    # Expected interval in minutes
    interval_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
    }.get(interval, 30)
    
    # Check each symbol (use fresh connection for each to avoid connection issues)
    for i, symbol in enumerate(symbols, 1):
        if i % 50 == 0:
            print(f"  Progress: {i}/{len(symbols)} symbols checked...")
        
        try:
            with get_connection() as conn:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                latest_ts = get_latest_timestamp(conn, symbol_id, interval)
            
                if latest_ts is None:
                    no_data.append(symbol)
                else:
                    latest_date = latest_ts.date()
                    age_days = (now.date() - latest_date).days
                    
                    if latest_date >= target_dt:
                        up_to_date.append((symbol, latest_date))
                    elif latest_date < target_dt:
                        days_behind = (target_dt - latest_date).days
                        stale.append((symbol, latest_date, days_behind))
        except Exception as e:
            gaps.append((symbol, f"Error: {e}"))
    
    # Print report
    print("\n" + "=" * 70)
    print("DATA GAP REPORT")
    print("=" * 70)
    print(f"Target date: {target_date}")
    print(f"Interval: {interval}")
    print(f"\nSummary:")
    print(f"  ✓ Up to date (>= {target_date}): {len(up_to_date)}")
    print(f"  ⚠ Stale (< {target_date}): {len(stale)}")
    print(f"  ✗ No data: {len(no_data)}")
    print(f"  ❌ Errors: {len(gaps)}")
    
    if up_to_date:
        print(f"\n✓ Up to date symbols ({len(up_to_date)}):")
        for symbol, date in up_to_date[:10]:
            print(f"  - {symbol}: {date}")
        if len(up_to_date) > 10:
            print(f"  ... and {len(up_to_date) - 10} more")
    
    if stale:
        print(f"\n⚠ Stale symbols (need backfill, {len(stale)}):")
        # Sort by days behind
        stale_sorted = sorted(stale, key=lambda x: x[2], reverse=True)
        for symbol, date, days_behind in stale_sorted[:20]:
            print(f"  - {symbol}: Latest = {date} ({days_behind} days behind target)")
        if len(stale) > 20:
            print(f"  ... and {len(stale) - 20} more")
    
    if no_data:
        print(f"\n✗ Symbols with no data ({len(no_data)}):")
        for symbol in no_data[:20]:
            print(f"  - {symbol}")
        if len(no_data) > 20:
            print(f"  ... and {len(no_data) - 20} more")
    
    if gaps:
        print(f"\n❌ Symbols with errors ({len(gaps)}):")
        for symbol, error in gaps[:10]:
            print(f"  - {symbol}: {error}")
        if len(gaps) > 10:
            print(f"  ... and {len(gaps) - 10} more")
    
    # Return summary
    return {
        "total": len(symbols),
        "up_to_date": len(up_to_date),
        "stale": len(stale),
        "no_data": len(no_data),
        "errors": len(gaps),
    }

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check for data gaps")
    parser.add_argument(
        "--interval",
        default="30m",
        help="Data interval (default: 30m)",
        choices=["1m", "5m", "15m", "30m", "1h"]
    )
    parser.add_argument(
        "--target-date",
        default="2025-11-10",
        help="Target date to check up to (default: 2025-11-10)"
    )
    
    args = parser.parse_args()
    
    summary = check_data_gaps(interval=args.interval, target_date=args.target_date)
    
    # Exit with error code if there are gaps
    if summary["stale"] > 0 or summary["no_data"] > 0:
        sys.exit(1)
    else:
        sys.exit(0)
