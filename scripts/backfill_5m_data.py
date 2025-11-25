#!/usr/bin/env python3
"""
Comprehensive backfill script for 5m data migration.
Fetches 5m data from EODHD API and stores in database.
"""

import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from typing import List, Dict, Tuple
import sys

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

def get_db_connection():
    """Create database connection"""
    import subprocess
    env = load_env()
    db_url = env.get('DGAS_DATABASE_URL', '')
    
    # Convert SQLAlchemy format to PostgreSQL format
    if db_url.startswith('postgresql+psycopg://'):
        db_url = db_url.replace('postgresql+psycopg://', 'postgresql://')
    
    return db_url

def fetch_5m_data(symbol: str, start_date: date, end_date: date, api_token: str) -> List[Dict]:
    """
    Fetch 5m data from EODHD API for a symbol.
    
    Returns list of bars with format:
    {'datetime': '2024-01-02 09:30:00', 'open': 100.0, 'high': 101.0, 'low': 99.0, 'close': 100.5, 'volume': 1000000}
    """
    symbol_with_exchange = f"{symbol}.US"
    
    # Convert dates to Unix timestamps (EODHD requires timestamps)
    start_ts = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    end_ts = int(datetime.combine(end_date, datetime.min.time()).timestamp())
    
    base_url = "https://eodhd.com/api/intraday"
    url = f"{base_url}/{symbol_with_exchange}?api_token={api_token}&interval=5m&from={start_ts}&to={end_ts}&fmt=json"
    
    try:
        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            
        if isinstance(data, list):
            return data
        else:
            print(f"  ⚠ Unexpected response for {symbol}: {data}")
            return []
            
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"  ⚠ Symbol {symbol} not found")
        elif e.code == 429:
            print(f"  ⚠ Rate limit hit, waiting 60 seconds...")
            time.sleep(60)
            return fetch_5m_data(symbol, start_date, end_date, api_token)  # Retry
        else:
            print(f"  ❌ HTTP Error {e.code} for {symbol}: {e.reason}")
        return []
    except Exception as e:
        print(f"  ❌ Error fetching {symbol}: {e}")
        return []

def store_5m_data(symbol: str, bars: List[Dict], db_url: str) -> int:
    """
    Store 5m bars in the database using psql.
    Returns number of bars stored.
    """
    if not bars:
        return 0
    
    import subprocess
    import tempfile
    
    # Get symbol_id from database
    query = f"SELECT symbol_id FROM market_symbols WHERE symbol = '{symbol}' LIMIT 1;"
    result = subprocess.run(
        ['psql', db_url, '-t', '-c', query],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"  ❌ Failed to get symbol_id for {symbol}")
        return 0
    
    symbol_id = result.stdout.strip()
    if not symbol_id:
        print(f"  ❌ Symbol {symbol} not found in database")
        return 0
    
    # Prepare INSERT statements
    inserts = []
    for bar in bars:
        # Parse datetime and convert to PostgreSQL format
        dt = bar['datetime']
        open_price = bar['open']
        high_price = bar['high']
        low_price = bar['low']
        close_price = bar['close']
        volume = bar.get('volume', 0)
        
        # Create INSERT statement with ON CONFLICT to handle duplicates
        insert = f"""
        INSERT INTO market_data (symbol_id, timestamp, interval_type, open_price, high_price, low_price, close_price, volume)
        VALUES ({symbol_id}, '{dt}', '5m', {open_price}, {high_price}, {low_price}, {close_price}, {volume})
        ON CONFLICT (symbol_id, timestamp, interval_type) DO NOTHING;
        """
        inserts.append(insert)
    
    # Write to temp file and execute
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write('\n'.join(inserts))
        temp_file = f.name
    
    # Execute SQL file
    result = subprocess.run(
        ['psql', db_url, '-f', temp_file],
        capture_output=True,
        text=True
    )
    
    # Clean up temp file
    import os
    os.unlink(temp_file)
    
    if result.returncode != 0:
        print(f"  ❌ Failed to insert data for {symbol}: {result.stderr}")
        return 0
    
    # Count successful inserts (lines with "INSERT")
    inserted = result.stdout.count('INSERT')
    return inserted

def get_all_symbols(db_url: str) -> List[str]:
    """Get all active symbols from database."""
    import subprocess
    
    query = "SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol;"
    result = subprocess.run(
        ['psql', db_url, '-t', '-c', query],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ Failed to get symbols: {result.stderr}")
        return []
    
    symbols = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    return symbols

def backfill_symbols(symbols: List[str], start_date: date, end_date: date, api_token: str, db_url: str) -> Dict:
    """
    Backfill 5m data for a list of symbols.
    Returns statistics about the backfill.
    """
    stats = {
        'total_symbols': len(symbols),
        'successful': 0,
        'failed': 0,
        'total_bars': 0,
        'api_calls': 0
    }
    
    print(f"\nStarting backfill for {len(symbols)} symbols")
    print(f"Date range: {start_date} to {end_date}")
    print("-" * 60)
    
    for i, symbol in enumerate(symbols, 1):
        print(f"\n[{i}/{len(symbols)}] Processing {symbol}...")
        
        # Fetch data
        bars = fetch_5m_data(symbol, start_date, end_date, api_token)
        stats['api_calls'] += 1
        
        if bars:
            print(f"  ✓ Fetched {len(bars)} bars")
            
            # Store data
            stored = store_5m_data(symbol, bars, db_url)
            
            if stored > 0:
                print(f"  ✓ Stored {stored} new bars")
                stats['successful'] += 1
                stats['total_bars'] += stored
            else:
                print(f"  ⚠ No new bars stored (may already exist)")
                stats['successful'] += 1  # Still count as successful if data exists
        else:
            print(f"  ❌ Failed to fetch data")
            stats['failed'] += 1
        
        # Rate limiting - wait between requests
        if i < len(symbols):
            time.sleep(0.5)  # 500ms between requests
        
        # Progress update every 10 symbols
        if i % 10 == 0:
            print(f"\n--- Progress: {i}/{len(symbols)} symbols processed ---")
            print(f"    Successful: {stats['successful']}, Failed: {stats['failed']}")
            print(f"    Total bars stored: {stats['total_bars']}")
    
    return stats

def main():
    """Main backfill function."""
    
    print("=" * 60)
    print("5M DATA BACKFILL SCRIPT")
    print("=" * 60)
    
    # Load configuration
    env = load_env()
    api_token = env.get('EODHD_API_TOKEN')
    
    if not api_token:
        print("❌ No EODHD_API_TOKEN found in .env")
        return 1
    
    db_url = get_db_connection()
    if not db_url:
        print("❌ No database URL found")
        return 1
    
    print(f"✓ API Token loaded: {api_token[:10]}...")
    print(f"✓ Database configured")
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--test':
            # Test mode - only process first 5 symbols
            print("\n🧪 TEST MODE - Processing first 5 symbols only")
            symbols = get_all_symbols(db_url)[:5]
            # Use shorter date range for testing
            end_date = datetime(2024, 11, 15).date()
            start_date = datetime(2024, 11, 1).date()  # 2 weeks of data
        elif sys.argv[1] == '--symbol':
            # Single symbol mode
            if len(sys.argv) < 3:
                print("❌ Please provide a symbol: --symbol AAPL")
                return 1
            symbols = [sys.argv[2]]
            end_date = datetime(2024, 11, 15).date()
            start_date = datetime(2024, 1, 2).date()  # Full year
        else:
            print(f"❌ Unknown argument: {sys.argv[1]}")
            print("Usage: python3 backfill_5m_data.py [--test | --symbol SYMBOL]")
            return 1
    else:
        # Full backfill mode
        print("\n⚠️  FULL BACKFILL MODE")
        print("This will backfill ALL 518 symbols from Jan 2024 to Nov 2024")
        print("Estimated time: 5-10 hours")
        print("Estimated API calls: 518+")
        
        response = input("\nProceed with full backfill? (yes/no): ")
        if response.lower() != 'yes':
            print("Backfill cancelled")
            return 0
        
        symbols = get_all_symbols(db_url)
        end_date = datetime(2024, 11, 15).date()  # Nov 15, 2024
        start_date = datetime(2024, 1, 2).date()   # Jan 2, 2024
    
    if not symbols:
        print("❌ No symbols found")
        return 1
    
    # Start backfill
    start_time = time.time()
    stats = backfill_symbols(symbols, start_date, end_date, api_token, db_url)
    elapsed = time.time() - start_time
    
    # Print summary
    print("\n" + "=" * 60)
    print("BACKFILL COMPLETE")
    print("=" * 60)
    print(f"Total symbols: {stats['total_symbols']}")
    print(f"Successful: {stats['successful']}")
    print(f"Failed: {stats['failed']}")
    print(f"Total bars stored: {stats['total_bars']:,}")
    print(f"API calls made: {stats['api_calls']}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    
    if stats['failed'] > 0:
        print(f"\n⚠️  {stats['failed']} symbols failed - may need retry")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())