#!/usr/bin/env python3
"""
Diagnose EODHD API issue by testing a few symbols directly.

This will help us understand:
1. What URL is actually being called
2. What the API response is
3. Whether the .US suffix is working
4. What the actual error/empty response looks like
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
import requests
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


def test_symbol_direct(symbol: str, start: str, end: str, interval: str = "30m") -> dict:
    """Test API call directly and return full details."""
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    
    # Test with .US suffix (what we're now doing)
    api_symbol = f"{symbol}.US"
    url = f"https://eodhd.com/api/intraday/{api_symbol}"
    
    # Convert dates to timestamps (Unix seconds)
    # EODHD API expects timestamps in UTC
    from datetime import datetime, timezone
    start_dt = datetime.strptime(start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    # End date should be end of day
    end_dt = datetime.strptime(end, "%Y-%m-%d").replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
    
    # Debug: print what dates we're requesting
    print(f"    Requesting: {start_dt} to {end_dt} (timestamps: {int(start_dt.timestamp())} to {int(end_dt.timestamp())})")
    
    params = {
        "api_token": config.api_token,
        "fmt": "json",
        "interval": interval,
        "from": int(start_dt.timestamp()),
        "to": int(end_dt.timestamp()),
    }
    
    result = {
        "symbol": symbol,
        "api_symbol": api_symbol,
        "url": url,
        "params": params,
        "status_code": None,
        "response_type": None,
        "response_length": None,
        "error": None,
        "sample_data": None,
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        result["status_code"] = response.status_code
        
        if response.status_code == 200:
            try:
                data = response.json()
                result["response_type"] = type(data).__name__
                
                if isinstance(data, list):
                    result["response_length"] = len(data)
                    if len(data) > 0:
                        result["sample_data"] = data[0]
                else:
                    result["sample_data"] = str(data)[:200]
            except json.JSONDecodeError:
                result["error"] = f"Not JSON: {response.text[:200]}"
        else:
            result["error"] = response.text[:500]
            
    except Exception as e:
        result["error"] = str(e)
    
    return result


def main():
    """Test symbols and show results."""
    print("="*80)
    print("EODHD API DIAGNOSIS")
    print("="*80)
    print()
    
    # Test a mix of symbols
    test_symbols = [
        "AAPL",  # Should work
        "ABT",   # Failing
        "ACGL",  # Working (according to backfill output)
        "ACN",   # Failing
    ]
    
    # Also test with a recent date range that definitely has data
    print("\n" + "="*80)
    print("TESTING WITH RECENT DATE RANGE (Oct 1-31, 2025)")
    print("="*80)
    recent_start = "2025-10-01"
    recent_end = "2025-10-31"
    
    for symbol in ["AAPL", "ABT"]:
        print(f"\nTesting {symbol} with recent dates...")
        result = test_symbol_direct(symbol, recent_start, recent_end, "30m")
        print(f"  Status: {result['status_code']}, Length: {result['response_length']}")
        if result['response_length'] and result['response_length'] > 0:
            print(f"  ✓ {symbol} has data for Oct 2025")
        else:
            print(f"  ✗ {symbol} has no data for Oct 2025")
    
    print("\n" + "="*80)
    print("TESTING WITH NOV 1-13, 2025")
    print("="*80)
    
    start = "2025-11-01"
    end = "2025-11-13"
    
    results = []
    for symbol in test_symbols:
        print(f"Testing {symbol}...")
        result = test_symbol_direct(symbol, start, end, "30m")
        results.append(result)
    
    # Print results
    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    
    for r in results:
        print(f"\n{symbol}:")
        print(f"  API Symbol: {r['api_symbol']}")
        print(f"  URL: {r['url']}")
        print(f"  Status: {r['status_code']}")
        print(f"  Response Type: {r['response_type']}")
        print(f"  Response Length: {r['response_length']}")
        if r['error']:
            print(f"  Error: {r['error']}")
        if r['sample_data']:
            print(f"  Sample: {json.dumps(r['sample_data'], indent=2, default=str)[:300]}")
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    working = [r for r in results if r['response_length'] and r['response_length'] > 0]
    empty = [r for r in results if r['response_length'] == 0]
    errors = [r for r in results if r['error']]
    
    print(f"Working: {len(working)}")
    print(f"Empty responses: {len(empty)}")
    print(f"Errors: {len(errors)}")
    
    if empty:
        print("\n⚠ Symbols with empty responses:")
        for r in empty:
            print(f"  - {r['symbol']}: Status {r['status_code']}, empty array")
            print(f"    URL: {r['url']}")
            print(f"    Params: from={r['params']['from']}, to={r['params']['to']}")


if __name__ == "__main__":
    main()
