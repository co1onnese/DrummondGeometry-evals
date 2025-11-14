#!/usr/bin/env python3
"""
Check data availability status for Nov 6-13 backtest.

Reports which symbols have complete data and which need backfilling.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dgas.db import get_connection
from dgas.data.repository import fetch_market_data, get_latest_timestamp, ensure_market_symbol


def get_all_active_symbols() -> list[str]:
    """Get all active symbols from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM market_symbols WHERE is_active = true ORDER BY symbol")
            return [row[0] for row in cur.fetchall()]


def check_data_status() -> None:
    """Check data status for Nov 6-13 backtest."""
    print("="*80)
    print("DATA STATUS CHECK FOR NOV 6-13 BACKTEST")
    print("="*80)
    print()
    
    # Date ranges needed
    trading_start = datetime(2025, 11, 6, tzinfo=timezone.utc)
    trading_end = datetime(2025, 11, 13, 23, 59, 59, tzinfo=timezone.utc)
    lookback_30m_start = datetime(2025, 11, 1, tzinfo=timezone.utc)
    lookback_1d_start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    
    symbols = get_all_active_symbols()
    print(f"Checking {len(symbols)} active symbols...\n")
    
    symbols_ready = []
    symbols_missing_30m_trading = []
    symbols_missing_30m_lookback = []
    symbols_missing_1d = []
    symbols_errors = []
    
    for idx, symbol in enumerate(symbols):
        if idx % 50 == 0:
            print(f"  Progress: {idx}/{len(symbols)} symbols checked...", end="\r", flush=True)
        
        try:
            with get_connection() as conn:
                symbol_id = ensure_market_symbol(conn, symbol, "US")
                
                # Check 30m trading period (Nov 6-13)
                bars_30m_trading = fetch_market_data(
                    conn, symbol, "30m", start=trading_start, end=trading_end
                )
                bars_in_range_30m = [
                    b for b in bars_30m_trading 
                    if trading_start <= b.timestamp <= trading_end
                ]
                has_30m_trading = len(bars_in_range_30m) >= 10
                
                # Check 30m lookback (Nov 1-5)
                bars_30m_lookback = fetch_market_data(
                    conn, symbol, "30m", start=lookback_30m_start, end=trading_start
                )
                has_30m_lookback = len(bars_30m_lookback) >= 5
                
                # Check 1d data (Oct 1 - Nov 13)
                bars_1d = fetch_market_data(
                    conn, symbol, "1d", start=lookback_1d_start, end=trading_end
                )
                has_1d = len(bars_1d) >= 10
                
                # Categorize symbol
                if has_30m_trading and has_30m_lookback and has_1d:
                    symbols_ready.append(symbol)
                else:
                    if not has_30m_trading:
                        symbols_missing_30m_trading.append(symbol)
                    if not has_30m_lookback:
                        symbols_missing_30m_lookback.append(symbol)
                    if not has_1d:
                        symbols_missing_1d.append(symbol)
                        
        except Exception as e:
            symbols_errors.append((symbol, str(e)[:100]))
    
    print(f"\n\n{'='*80}")
    print("DATA STATUS SUMMARY")
    print("="*80)
    print(f"\nTotal symbols checked: {len(symbols)}")
    print(f"✓ Symbols ready for backtest: {len(symbols_ready)}")
    print(f"✗ Symbols missing 30m trading data (Nov 6-13): {len(symbols_missing_30m_trading)}")
    print(f"✗ Symbols missing 30m lookback data (Nov 1-5): {len(symbols_missing_30m_lookback)}")
    print(f"✗ Symbols missing 1d data (Oct 1 - Nov 13): {len(symbols_missing_1d)}")
    print(f"✗ Symbols with errors: {len(symbols_errors)}")
    
    if symbols_ready:
        print(f"\n✓ Ready symbols ({len(symbols_ready)}):")
        for symbol in symbols_ready[:20]:
            print(f"  - {symbol}")
        if len(symbols_ready) > 20:
            print(f"  ... and {len(symbols_ready) - 20} more")
    
    if symbols_missing_30m_trading:
        print(f"\n✗ Missing 30m trading data ({len(symbols_missing_30m_trading)}):")
        for symbol in symbols_missing_30m_trading[:20]:
            print(f"  - {symbol}")
        if len(symbols_missing_30m_trading) > 20:
            print(f"  ... and {len(symbols_missing_30m_trading) - 20} more")
    
    if symbols_missing_1d:
        print(f"\n✗ Missing 1d data ({len(symbols_missing_1d)}):")
        for symbol in symbols_missing_1d[:20]:
            print(f"  - {symbol}")
        if len(symbols_missing_1d) > 20:
            print(f"  ... and {len(symbols_missing_1d) - 20} more")
    
    if symbols_errors:
        print(f"\n✗ Errors ({len(symbols_errors)}):")
        for symbol, error in symbols_errors[:10]:
            print(f"  - {symbol}: {error}")
        if len(symbols_errors) > 10:
            print(f"  ... and {len(symbols_errors) - 10} more")
    
    print(f"\n{'='*80}")
    
    # Recommendation
    if len(symbols_ready) < 10:
        print("\n⚠ RECOMMENDATION: Backfill data is REQUIRED")
        print("   You need at least 10 symbols with complete data for the backtest.")
        print("   Run: python scripts/backfill_nov6_nov13_backtest_data.py")
        return 1
    elif len(symbols_ready) < 100:
        print("\n⚠ RECOMMENDATION: Consider backfilling for more symbols")
        print("   Current ready symbols may be sufficient, but more would be better.")
        print("   Run: python scripts/backfill_nov6_nov13_backtest_data.py")
        return 0
    else:
        print("\n✓ RECOMMENDATION: Data looks good!")
        print("   You have enough symbols with complete data for the backtest.")
        return 0


if __name__ == "__main__":
    import os
    os.environ['PYTHONUNBUFFERED'] = '1'
    
    try:
        exit_code = check_data_status()
        sys.exit(exit_code)
    except Exception as e:
        print(f"\n\n✗ FATAL ERROR: {e}", file=sys.stderr, flush=True)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
        sys.exit(1)
