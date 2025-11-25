#!/usr/bin/env python3
"""
Simple EODHD API test without dependencies.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

def load_env():
    """Load .env file manually"""
    env = {}
    with open('/opt/DrummondGeometry-evals/.env', 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                env[key] = value.strip('"').strip("'")
    return env

def test_eodhd_api():
    """Test EODHD API with direct HTTP calls."""
    
    print("=" * 60)
    print("SIMPLE EODHD API TEST")
    print("=" * 60)
    
    # Load API token
    env = load_env()
    api_token = env.get('EODHD_API_TOKEN')
    
    if not api_token:
        print("❌ No EODHD_API_TOKEN found in .env")
        return False
    
    print(f"\n✓ API Token loaded: {api_token[:10]}...")
    
    # Test API with AAPL - use correct dates (we're in 2024, not 2025)
    symbol = "AAPL.US"
    # Use dates from a week ago to ensure data is available
    end_date = datetime(2024, 11, 15).date()  # Nov 15, 2024
    start_date = datetime(2024, 11, 11).date()  # Nov 11, 2024
    
    # Convert dates to Unix timestamps (EODHD API requires timestamps)
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
    
    # Build URL for intraday data
    base_url = "https://eodhd.com/api/intraday"
    url = f"{base_url}/{symbol}?api_token={api_token}&interval=5m&from={start_ts}&to={end_ts}&fmt=json"
    
    print(f"\nTesting API with {symbol} from {start_date} to {end_date}...")
    print(f"URL: {base_url}/{symbol}?...&interval=5m")
    
    try:
        # Make request
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            
        if isinstance(data, list) and len(data) > 0:
            print(f"\n✅ SUCCESS! Received {len(data)} bars")
            print(f"First bar: {data[0]['datetime']} - Close: {data[0]['close']}")
            print(f"Last bar:  {data[-1]['datetime']} - Close: {data[-1]['close']}")
            return True
        else:
            print(f"⚠ Unexpected response format: {data}")
            return False
            
    except urllib.error.HTTPError as e:
        print(f"\n❌ HTTP Error {e.code}: {e.reason}")
        if e.code == 401:
            print("Invalid API token")
        elif e.code == 429:
            print("Rate limit exceeded")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return False

if __name__ == "__main__":
    success = test_eodhd_api()
    if success:
        print("\n✅ API is working! Ready to proceed with backfill.")
    else:
        print("\n❌ API test failed. Please check credentials.")