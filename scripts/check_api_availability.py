#!/usr/bin/env python3
"""
Check when API has data available for a target date.
Useful for monitoring when backfill can proceed.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings

def check_api_availability(target_date: str = "2025-11-10", test_symbols: list = None):
    """Check if API has data available for target date."""
    
    if test_symbols is None:
        test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'TSLA', 'SPY']
    
    target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
    
    print(f"Checking API availability for {target_date}")
    print("=" * 70)
    
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)
    
    available_dates = []
    
    for symbol in test_symbols:
        try:
            # Try to fetch data for target date
            bars = client.fetch_intraday(
                symbol,
                start=target_date,
                end=target_date,
                interval='30m',
                limit=50
            )
            
            if bars:
                dates = [bar.timestamp.date() for bar in bars]
                unique_dates = sorted(set(dates))
                latest = max(unique_dates)
                available_dates.append((symbol, latest, len(bars)))
                print(f"  ✓ {symbol}: {len(bars)} bars, latest = {latest}")
            else:
                print(f"  ✗ {symbol}: No data for {target_date}")
        except Exception as e:
            print(f"  ✗ {symbol}: Error - {str(e)[:60]}")
    
    client.close()
    
    if available_dates:
        max_date = max(d[1] for d in available_dates)
        print(f"\n{'='*70}")
        print(f"API Availability Summary:")
        print(f"  Latest available date: {max_date}")
        print(f"  Target date: {target_date}")
        days_behind = (target_dt - max_date).days if max_date < target_dt else 0
        print(f"  Days behind target: {days_behind}")
        
        if max_date >= target_dt:
            print(f"\n✓ API has data for target date! Backfill can proceed.")
            return True
        else:
            print(f"\n⚠ API does not yet have data for target date.")
            print(f"  Wait {days_behind} more day(s) for API to publish data.")
            return False
    else:
        print(f"\n✗ No data available from API for any test symbols.")
        return False

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Check API data availability")
    parser.add_argument("--target-date", default="2025-11-10", help="Target date to check")
    
    args = parser.parse_args()
    
    is_available = check_api_availability(target_date=args.target_date)
    sys.exit(0 if is_available else 1)
