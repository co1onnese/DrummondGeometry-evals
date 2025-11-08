#!/usr/bin/env python3
"""
Database Cleanup Script

This script removes unused tables and data from the database, keeping only
tables that are used by the current production code.

UNUSED TABLES TO DROP (7 tables):
1. backfill_status (1,036 rows) - UNUSED by current code
2. drummond_lines (0 rows)
3. envelope_bands (0 rows)
4. market_data_metadata (0 rows)
5. market_state (0 rows)
6. pldot_calculations (0 rows)
7. trading_signals (0 rows)

ACTIVE TABLES TO KEEP (16 tables):
- market_data (7,145,384 rows)
- market_symbols (518 rows)
- exchanges (1 row)
- trading_days (361 rows)
- backtest_results (1,968 rows)
- backtest_trades (16,633 rows)
- generated_signals (90 rows)
- prediction_runs (135 rows)
- prediction_metrics (60 rows)
- scheduler_state (1 row)
- schema_migrations (6 rows)
- confluence_zones (0 rows - used by code)
- market_holidays (0 rows - used by code)
- market_states_v2 (0 rows - used by code)
- multi_timeframe_analysis (0 rows - used by code)
- pattern_events (0 rows - used by code)
"""

from dgas.db import get_connection
import sys


def cleanup_database():
    """Drop unused tables from the database."""
    # Tables to drop (unused by production code)
    tables_to_drop = [
        'backfill_status',
        'drummond_lines',
        'envelope_bands',
        'market_data_metadata',
        'market_state',
        'pldot_calculations',
        'trading_signals',
    ]

    print("=" * 80)
    print("DATABASE CLEANUP")
    print("=" * 80)
    print()
    print("Tables to be DROPPED (unused by production code):")
    for table in tables_to_drop:
        print(f"  - {table}")
    print()

    # Confirm with user
    response = input("Proceed with cleanup? This will DROP the above tables. (yes/no): ")
    if response.lower() != 'yes':
        print("Cleanup cancelled.")
        return 1

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Drop each table
            for table in tables_to_drop:
                try:
                    cur.execute(f'DROP TABLE IF EXISTS {table} CASCADE')
                    print(f"✓ Dropped table: {table}")
                except Exception as e:
                    print(f"✗ Error dropping {table}: {e}")
                    return 1

            conn.commit()
            print()
            print("=" * 80)
            print("CLEANUP COMPLETE")
            print("=" * 80)
            print()
            print("Database now contains only tables used by production code.")
            print()
            return 0


if __name__ == '__main__':
    sys.exit(cleanup_database())
