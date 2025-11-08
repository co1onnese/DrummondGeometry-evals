#!/usr/bin/env python3
"""Verify database cleanup was successful."""

from dgas.db import get_connection


def verify_cleanup():
    """Verify the database is in a clean state."""
    print("=" * 80)
    print("DATABASE CLEANUP VERIFICATION")
    print("=" * 80)
    print()

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get all remaining tables
            cur.execute('''
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            ''')

            remaining_tables = [row[0] for row in cur.fetchall()]

            # Get row counts
            cur.execute('''
                SELECT relname as table_name, n_live_tup as live_rows
                FROM pg_stat_user_tables
                ORDER BY relname
            ''')

            row_counts = {row[0]: row[1] for row in cur.fetchall()}

    # Expected tables after cleanup
    expected_tables = {
        'backtest_results',
        'backtest_trades',
        'confluence_zones',
        'exchanges',
        'generated_signals',
        'market_data',
        'market_holidays',
        'market_states_v2',
        'market_symbols',
        'multi_timeframe_analysis',
        'pattern_events',
        'pldot_calculations',  # Check if still exists
        'prediction_metrics',
        'prediction_runs',
        'scheduler_state',
        'schema_migrations',
        'trading_days',
        'backfill_status',  # Check if still exists
        'drummond_lines',  # Check if still exists
        'envelope_bands',  # Check if still exists
        'market_data_metadata',  # Check if still exists
        'market_state',  # Check if still exists
        'trading_signals',  # Check if still exists
    }

    # Tables that should be dropped
    dropped_tables = {
        'backfill_status',
        'drummond_lines',
        'envelope_bands',
        'market_data_metadata',
        'market_state',
        'pldot_calculations',
        'trading_signals',
    }

    # Tables that should remain
    active_tables = {
        'market_data',
        'market_symbols',
        'exchanges',
        'trading_days',
        'backtest_results',
        'backtest_trades',
        'generated_signals',
        'prediction_runs',
        'prediction_metrics',
        'scheduler_state',
        'schema_migrations',
        'confluence_zones',
        'market_holidays',
        'market_states_v2',
        'multi_timeframe_analysis',
        'pattern_events',
    }

    print("REMAINING TABLES:")
    print("-" * 80)
    for table in remaining_tables:
        rows = row_counts.get(table, 0)
        status = "✅ ACTIVE" if table in active_tables else ("❌ UNEXPECTED" if table not in dropped_tables else "⚠️  SHOULD BE DROPPED")
        print(f"  {table:<35} {rows:>10,} rows  {status}")

    print()
    print("=" * 80)
    print("VERIFICATION RESULTS")
    print("=" * 80)

    # Check for unexpected tables
    unexpected = set(remaining_tables) - expected_tables
    if unexpected:
        print(f"❌ UNEXPECTED TABLES: {', '.join(unexpected)}")
    else:
        print("✅ No unexpected tables")

    # Check if dropped tables still exist
    still_exists = set(remaining_tables) & dropped_tables
    if still_exists:
        print(f"⚠️  TABLES NOT DROPPED: {', '.join(still_exists)}")
        print("   Run cleanup_database.py to remove them")
    else:
        print("✅ All unused tables successfully removed")

    # Check active tables
    missing_active = active_tables - set(remaining_tables)
    if missing_active:
        print(f"❌ MISSING ACTIVE TABLES: {', '.join(missing_active)}")
    else:
        print("✅ All active tables present")

    # Summary
    print()
    print("SUMMARY:")
    print(f"  Total tables remaining: {len(remaining_tables)}")
    print(f"  Expected after cleanup: {len(expected_tables)}")
    print(f"  Active tables with data: {sum(1 for t in remaining_tables if row_counts.get(t, 0) > 0 and t in active_tables)}")
    print(f"  Empty tables (retained): {sum(1 for t in remaining_tables if row_counts.get(t, 0) == 0)}")
    print()

    # Final verdict
    if not unexpected and not still_exists and not missing_active:
        print("✅ DATABASE CLEANUP VERIFICATION: PASSED")
        return 0
    else:
        print("❌ DATABASE CLEANUP VERIFICATION: FAILED")
        return 1


if __name__ == '__main__':
    import sys
    sys.exit(verify_cleanup())
