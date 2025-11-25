#!/usr/bin/env python3
"""Diagnose OHLC validation issues with EODHD API responses.

This script fetches data from EODHD API and analyzes what records are being
skipped and why.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List

from dgas.data.client import EODHDClient, EODHDConfig
from dgas.settings import get_settings


def analyze_api_response(payload: List[Dict[str, Any]], symbol: str) -> None:
    """Analyze API response to understand why records are being skipped."""
    print(f"\n{'='*80}")
    print(f"Analyzing API response for {symbol}")
    print(f"{'='*80}\n")
    
    total_records = len(payload)
    print(f"Total records in API response: {total_records}")
    
    if total_records == 0:
        print("⚠️  Empty response from API")
        return
    
    # Analyze first few records
    print(f"\nFirst 5 records:")
    for i, rec in enumerate(payload[:5], 1):
        print(f"\n  Record {i}:")
        print(f"    Keys: {list(rec.keys())}")
        print(f"    Timestamp: {rec.get('timestamp')} ({type(rec.get('timestamp'))})")
        print(f"    Open: {rec.get('open')} ({type(rec.get('open'))})")
        print(f"    High: {rec.get('high')} ({type(rec.get('high'))})")
        print(f"    Low: {rec.get('low')} ({type(rec.get('low'))})")
        print(f"    Close: {rec.get('close')} ({type(rec.get('close'))})")
        print(f"    Volume: {rec.get('volume')} ({type(rec.get('volume'))})")
    
    # Count records with missing OHLC
    missing_ohlc = 0
    missing_open = 0
    missing_high = 0
    missing_low = 0
    missing_close = 0
    missing_timestamp = 0
    zero_volume = 0
    
    for rec in payload:
        if rec.get("open") is None:
            missing_open += 1
        if rec.get("high") is None:
            missing_high += 1
        if rec.get("low") is None:
            missing_low += 1
        if rec.get("close") is None:
            missing_close += 1
        if rec.get("timestamp") is None:
            missing_timestamp += 1
        if rec.get("volume") == 0 or rec.get("volume") is None:
            zero_volume += 1
        
        if (rec.get("open") is None or rec.get("high") is None or 
            rec.get("low") is None or rec.get("close") is None):
            missing_ohlc += 1
    
    print(f"\n{'='*80}")
    print("Missing Data Analysis:")
    print(f"{'='*80}")
    print(f"Records with missing Open: {missing_open} ({missing_open/total_records*100:.1f}%)")
    print(f"Records with missing High: {missing_high} ({missing_high/total_records*100:.1f}%)")
    print(f"Records with missing Low: {missing_low} ({missing_low/total_records*100:.1f}%)")
    print(f"Records with missing Close: {missing_close} ({missing_close/total_records*100:.1f}%)")
    print(f"Records with missing Timestamp: {missing_timestamp} ({missing_timestamp/total_records*100:.1f}%)")
    print(f"Records with zero/null Volume: {zero_volume} ({zero_volume/total_records*100:.1f}%)")
    print(f"\nRecords with ANY missing OHLC: {missing_ohlc} ({missing_ohlc/total_records*100:.1f}%)")
    
    # Show examples of records with missing data
    if missing_ohlc > 0:
        print(f"\n{'='*80}")
        print("Examples of records with missing OHLC data:")
        print(f"{'='*80}")
        count = 0
        for rec in payload:
            if (rec.get("open") is None or rec.get("high") is None or 
                rec.get("low") is None or rec.get("close") is None):
                print(f"\n  Record {count + 1}:")
                print(f"    {rec}")
                count += 1
                if count >= 5:
                    break
    
    # Try to parse records
    print(f"\n{'='*80}")
    print("Attempting to parse records with IntervalData.from_api_list:")
    print(f"{'='*80}")
    try:
        from dgas.data.models import IntervalData
        parsed = IntervalData.from_api_list(payload, "30m", symbol_override=symbol)
        print(f"✓ Successfully parsed {len(parsed)} records")
        if len(parsed) > 0:
            print(f"\nFirst parsed record:")
            print(f"  {parsed[0]}")
    except Exception as e:
        print(f"✗ Error parsing: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main diagnostic function."""
    if len(sys.argv) < 2:
        print("Usage: python diagnose_ohlc_validation.py <SYMBOL> [INTERVAL]")
        print("Example: python diagnose_ohlc_validation.py AAPL 30m")
        sys.exit(1)
    
    symbol = sys.argv[1].upper()
    interval = sys.argv[2] if len(sys.argv) > 2 else "30m"
    
    print(f"Diagnosing OHLC validation for {symbol} with interval {interval}")
    print(f"Timestamp: {datetime.now(timezone.utc)}")
    
    # Get settings
    settings = get_settings()
    if not settings.eodhd_api_token:
        print("❌ EODHD_API_TOKEN not configured")
        sys.exit(1)
    
    # Create client
    config = EODHDConfig.from_settings(settings)
    client = EODHDClient(config)
    
    try:
        # Fetch data
        print(f"\nFetching data from EODHD API...")
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=1)
        
        # Get raw API response
        params = {
            "api_token": config.api_token,
            "fmt": "json",
            "interval": "5m" if interval == "30m" else interval,
            "from": int(start_time.timestamp()),
            "to": int(end_time.timestamp()),
            "limit": 50000,
        }
        
        api_symbol = f"{symbol}.US" if not symbol.endswith(".US") else symbol
        url = f"{config.base_url}/intraday/{api_symbol}"
        
        import requests
        response = requests.get(url, params=params, timeout=30)
        
        print(f"HTTP Status: {response.status_code}")
        print(f"Response size: {len(response.text)} bytes")
        
        if response.status_code != 200:
            print(f"❌ API error: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            sys.exit(1)
        
        payload = response.json()
        
        if not isinstance(payload, list):
            print(f"❌ Unexpected response format: {type(payload)}")
            print(f"Response: {str(payload)[:500]}")
            sys.exit(1)
        
        # Analyze response
        analyze_api_response(payload, symbol)
        
        # Also try using the client method
        print(f"\n{'='*80}")
        print("Testing with EODHDClient.fetch_intraday:")
        print(f"{'='*80}")
        try:
            bars = client.fetch_intraday(symbol, interval=interval, exchange="US")
            print(f"✓ Client method returned {len(bars)} bars")
            if len(bars) > 0:
                print(f"\nFirst bar:")
                print(f"  {bars[0]}")
        except Exception as e:
            print(f"✗ Client method error: {e}")
            import traceback
            traceback.print_exc()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
