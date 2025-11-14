#!/usr/bin/env python3
"""
Test EODHD API directly to debug why many symbols return no data.

Tests:
1. Direct API call with .US suffix
2. Check response status and content
3. Test with a few failing symbols
"""

import sys
import json
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings
import requests


def test_api_direct(symbol: str, start: str, end: str, interval: str = "30m") -> None:
    """Test API call directly and show full response."""
    settings = get_settings()
    config = EODHDConfig.from_settings(settings)
    
    # Build URL manually to see what we're calling
    api_symbol = f"{symbol}.US"
    url = f"https://eodhd.com/api/intraday/{api_symbol}"
    
    params = {
        "api_token": config.api_token,
        "fmt": "json",
        "interval": interval,
        "from": start,
        "to": end,
    }
    
    print(f"\nTesting {symbol}:")
    print(f"  URL: {url}")
    print(f"  Params: {params}")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        print(f"  Status Code: {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                if isinstance(data, list):
                    print(f"  Response: List with {len(data)} items")
                    if len(data) > 0:
                        print(f"  First item keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'N/A'}")
                        print(f"  Sample item: {json.dumps(data[0] if data else {}, indent=2)[:200]}")
                    else:
                        print(f"  Response: Empty array []")
                        # Check if there's an error message in the response
                        print(f"  Full response text: {response.text[:500]}")
                else:
                    print(f"  Response: {type(data)} - {str(data)[:200]}")
            except json.JSONDecodeError:
                print(f"  Response is not JSON: {response.text[:500]}")
        else:
            print(f"  Error Response: {response.text[:500]}")
            
    except Exception as e:
        print(f"  Exception: {e}")


def main():
    """Test a few symbols that are failing."""
    print("="*80)
    print("EODHD API DIRECT TEST")
    print("="*80)
    
    # Test symbols that are failing
    test_symbols = ["AAPL", "ABT", "ACN", "ADBE"]
    
    # Test date range: Nov 1-13, 2025
    start = "2025-11-01"
    end = "2025-11-13"
    
    for symbol in test_symbols:
        test_api_direct(symbol, start, end, "30m")
    
    print("\n" + "="*80)
    print("Also test with symbol that works (ACGL):")
    test_api_direct("ACGL", start, end, "30m")


if __name__ == "__main__":
    main()
