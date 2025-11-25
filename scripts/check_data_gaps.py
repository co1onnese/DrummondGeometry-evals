#!/usr/bin/env python3
"""
Script to check for data gaps in the market_data table.
Identifies missing data that the prediction engine may require.
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2
from psycopg2.extras import RealDictCursor

def load_env_file():
    """Manually load .env file"""
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"').strip("'")
                    os.environ[key] = value

# Load environment variables
load_env_file()

def get_db_connection():
    """Create database connection using credentials from .env"""
    db_url = os.getenv('DGAS_DATABASE_URL')
    if not db_url:
        raise ValueError("DGAS_DATABASE_URL not found in .env")
    
    # Convert SQLAlchemy format to psycopg2 format
    # postgresql+psycopg://user:pass@host:port/db -> postgresql://user:pass@host:port/db
    if db_url.startswith('postgresql+psycopg://'):
        db_url = db_url.replace('postgresql+psycopg://', 'postgresql://')
    
    return psycopg2.connect(db_url)

def get_active_symbols(conn) -> List[Dict]:
    """Get all active symbols from the database"""
    query = """
        SELECT symbol_id, symbol, exchange, is_active
        FROM market_symbols
        WHERE is_active = true
        ORDER BY symbol
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query)
        return cur.fetchall()

def check_symbol_data_gaps(conn, symbol_id: int, symbol: str, interval: str = '5m') -> Dict:
    """
    Check for data gaps for a specific symbol.
    Returns information about data coverage and gaps.
    """
    # Get data range and count
    query = """
        SELECT 
            COUNT(*) as bar_count,
            MIN(timestamp) as first_bar,
            MAX(timestamp) as last_bar,
            MAX(timestamp) - MIN(timestamp) as data_span
        FROM market_data
        WHERE symbol_id = %s AND interval_type = %s
    """
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, (symbol_id, interval))
        result = cur.fetchone()
        
        if not result or result['bar_count'] == 0:
            return {
                'symbol': symbol,
                'interval': interval,
                'status': 'NO_DATA',
                'bar_count': 0,
                'first_bar': None,
                'last_bar': None,
                'gaps': []
            }
        
        # Check for gaps (missing consecutive bars)
        gap_query = """
            WITH consecutive_bars AS (
                SELECT 
                    timestamp,
                    LAG(timestamp) OVER (ORDER BY timestamp) as prev_timestamp,
                    timestamp - LAG(timestamp) OVER (ORDER BY timestamp) as time_diff
                FROM market_data
                WHERE symbol_id = %s AND interval_type = %s
                ORDER BY timestamp
            )
            SELECT 
                prev_timestamp as gap_start,
                timestamp as gap_end,
                time_diff,
                EXTRACT(EPOCH FROM time_diff) / 60 as gap_minutes
            FROM consecutive_bars
            WHERE time_diff > INTERVAL '5 minutes'  -- For 5m bars, gap if >5 min
                AND EXTRACT(DOW FROM timestamp) BETWEEN 1 AND 5  -- Weekdays only
                AND EXTRACT(HOUR FROM timestamp AT TIME ZONE 'America/New_York') BETWEEN 4 AND 20  -- Extended hours
            ORDER BY prev_timestamp
            LIMIT 20  -- Show first 20 gaps
        """
        
        cur.execute(gap_query, (symbol_id, interval))
        gaps = cur.fetchall()
        
        # Calculate data freshness
        now = datetime.now(timezone.utc)
        last_bar_time = result['last_bar']
        if last_bar_time:
            hours_since_last = (now - last_bar_time).total_seconds() / 3600
        else:
            hours_since_last = None
        
        return {
            'symbol': symbol,
            'interval': interval,
            'status': 'OK' if len(gaps) == 0 else 'HAS_GAPS',
            'bar_count': result['bar_count'],
            'first_bar': result['first_bar'],
            'last_bar': result['last_bar'],
            'hours_since_last': hours_since_last,
            'gap_count': len(gaps),
            'gaps': gaps[:5]  # Show first 5 gaps for brevity
        }

def main():
    """Main function to check all symbols for data gaps"""
    print("=" * 80)
    print("DATA GAP ANALYSIS FOR PREDICTION ENGINE")
    print("=" * 80)
    print()
    
    conn = get_db_connection()
    
    try:
        # Get all active symbols
        symbols = get_active_symbols(conn)
        print(f"Found {len(symbols)} active symbols in database")
        print()
        
        # Categories for analysis
        no_data_symbols = []
        stale_symbols = []  # >24 hours old
        gap_symbols = []
        good_symbols = []
        
        # Check each symbol
        for sym in symbols:
            result = check_symbol_data_gaps(conn, sym['symbol_id'], sym['symbol'], '5m')
            
            if result['status'] == 'NO_DATA':
                no_data_symbols.append(result)
            elif result['hours_since_last'] and result['hours_since_last'] > 24:
                stale_symbols.append(result)
            elif result['gap_count'] > 0:
                gap_symbols.append(result)
            else:
                good_symbols.append(result)
        
        # Print summary
        print("SUMMARY")
        print("-" * 40)
        print(f"✓ Good symbols (no gaps, fresh data): {len(good_symbols)}")
        print(f"⚠ Symbols with gaps: {len(gap_symbols)}")
        print(f"⏰ Stale symbols (>24h old): {len(stale_symbols)}")
        print(f"✗ Symbols with no data: {len(no_data_symbols)}")
        print()
        
        # Show problematic symbols
        if no_data_symbols:
            print("SYMBOLS WITH NO DATA (need full backfill):")
            print("-" * 40)
            for sym in no_data_symbols[:10]:  # Show first 10
                print(f"  - {sym['symbol']}")
            if len(no_data_symbols) > 10:
                print(f"  ... and {len(no_data_symbols) - 10} more")
            print()
        
        if stale_symbols:
            print("STALE SYMBOLS (>24 hours old, need update):")
            print("-" * 40)
            for sym in sorted(stale_symbols, key=lambda x: x['hours_since_last'], reverse=True)[:10]:
                print(f"  - {sym['symbol']}: Last bar {sym['hours_since_last']:.1f} hours ago ({sym['last_bar']})")
            if len(stale_symbols) > 10:
                print(f"  ... and {len(stale_symbols) - 10} more")
            print()
        
        if gap_symbols:
            print("SYMBOLS WITH DATA GAPS:")
            print("-" * 40)
            for sym in sorted(gap_symbols, key=lambda x: x['gap_count'], reverse=True)[:10]:
                print(f"  - {sym['symbol']}: {sym['gap_count']} gaps, {sym['bar_count']} total bars")
                if sym['gaps']:
                    first_gap = sym['gaps'][0]
                    print(f"    First gap: {first_gap['gap_start']} to {first_gap['gap_end']} ({first_gap['gap_minutes']:.0f} min)")
            if len(gap_symbols) > 10:
                print(f"  ... and {len(gap_symbols) - 10} more")
            print()
        
        # Overall statistics
        print("OVERALL STATISTICS")
        print("-" * 40)
        
        # Get total bar count and date range
        stats_query = """
            SELECT 
                COUNT(*) as total_bars,
                COUNT(DISTINCT symbol_id) as symbols_with_data,
                MIN(timestamp) as earliest_bar,
                MAX(timestamp) as latest_bar
            FROM market_data
            WHERE interval_type = '5m'
        """
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(stats_query)
            stats = cur.fetchone()
        
        print(f"Total 5m bars in database: {stats['total_bars']:,}")
        print(f"Symbols with data: {stats['symbols_with_data']} / {len(symbols)}")
        print(f"Date range: {stats['earliest_bar']} to {stats['latest_bar']}")
        
        # Check if we need to run backfill
        if no_data_symbols or stale_symbols:
            print()
            print("RECOMMENDED ACTIONS:")
            print("-" * 40)
            if no_data_symbols:
                print(f"1. Run full backfill for {len(no_data_symbols)} symbols with no data")
            if stale_symbols:
                print(f"2. Run incremental update for {len(stale_symbols)} stale symbols")
            if gap_symbols:
                print(f"3. Run gap fill for {len(gap_symbols)} symbols with gaps")
            print()
            print("The prediction engine may not work correctly for symbols with missing data!")
        else:
            print()
            print("✓ All symbols have recent data. Prediction engine should work correctly.")
        
    finally:
        conn.close()

if __name__ == "__main__":
    main()