#!/usr/bin/env python3
"""
Test EODHD API with different symbol formats to identify the issue.

Tests:
1. Symbol without .US suffix (current approach)
2. Symbol with .US suffix (EODHD standard format)
3. Check API response for empty data
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings


def test_symbol_formats(symbols: list[str]) -> None:
    """Test different symbol formats with EODHD API."""
    print("="*80)
    print("TESTING EODHD API SYMBOL FORMATS")
    print("="*80)
    print()
    
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)
    
    # Test date range: Nov 1-13, 2025
    start_date = "2025-11-01"
    end_date = "2025-11-13"
    
    print(f"Testing date range: {start_date} to {end_date}")
    print(f"Testing {len(symbols)} symbols\n")
    
    results = {
        "without_suffix": {"success": [], "empty": [], "error": []},
        "with_suffix": {"success": [], "empty": [], "error": []},
    }
    
    for symbol in symbols[:10]:  # Test first 10 symbols
        print(f"\nTesting {symbol}:")
        
        # Test 1: Without .US suffix (current approach)
        try:
            bars = client.fetch_intraday(
                symbol=symbol,
                start=start_date,
                end=end_date,
                interval="30m"
            )
            if bars:
                print(f"  ✓ Without .US: {len(bars)} bars")
                results["without_suffix"]["success"].append(symbol)
            else:
                print(f"  ○ Without .US: Empty response")
                results["without_suffix"]["empty"].append(symbol)
        except Exception as e:
            print(f"  ✗ Without .US: Error - {str(e)[:100]}")
            results["without_suffix"]["error"].append((symbol, str(e)))
        
        # Test 2: With .US suffix (EODHD standard)
        try:
            symbol_with_suffix = f"{symbol}.US"
            bars = client.fetch_intraday(
                symbol=symbol_with_suffix,
                start=start_date,
                end=end_date,
                interval="30m"
            )
            if bars:
                print(f"  ✓ With .US: {len(bars)} bars")
                results["with_suffix"]["success"].append(symbol)
            else:
                print(f"  ○ With .US: Empty response")
                results["with_suffix"]["empty"].append(symbol)
        except Exception as e:
            print(f"  ✗ With .US: Error - {str(e)[:100]}")
            results["with_suffix"]["error"].append((symbol, str(e)))
    
    client.close()
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    print("\nWithout .US suffix:")
    print(f"  Success: {len(results['without_suffix']['success'])}")
    print(f"  Empty: {len(results['without_suffix']['empty'])}")
    print(f"  Error: {len(results['without_suffix']['error'])}")
    
    print("\nWith .US suffix:")
    print(f"  Success: {len(results['with_suffix']['success'])}")
    print(f"  Empty: {len(results['with_suffix']['empty'])}")
    print(f"  Error: {len(results['with_suffix']['error'])}")
    
    # Check if date is in the future
    today = datetime.now(timezone.utc).date()
    test_start = datetime.strptime(start_date, "%Y-%m-%d").date()
    if test_start > today:
        print(f"\n⚠ WARNING: Test date range ({start_date}) is in the FUTURE!")
        print(f"   Today is {today}")
        print(f"   EODHD API may not have data for future dates.")
        print(f"   This could explain why many symbols return empty data.")


if __name__ == "__main__":
    # Test with a few symbols that are failing
    test_symbols = ["ABT", "ACN", "ADBE", "ADI", "ADM", "ADP", "ADSK", "AEE", "AEP", "AES"]
    
    test_symbol_formats(test_symbols)
