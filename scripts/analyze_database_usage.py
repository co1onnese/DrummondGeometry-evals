#!/usr/bin/env python3
"""Analyze database usage to identify tables used by production code vs unused tables."""

import os
import re
from pathlib import Path
from collections import defaultdict

# Tables to check
TABLES = [
    'market_data', 'market_symbols', 'exchanges', 'trading_days',
    'backtest_results', 'backtest_trades', 'backfill_status',
    'generated_signals', 'trading_signals', 'multi_timeframe_analysis',
    'drummond_lines', 'envelope_bands', 'pattern_events', 'pldot_calculations',
    'confluence_zones', 'market_data_metadata', 'market_holidays',
    'market_state', 'market_states_v2', 'prediction_runs', 'prediction_metrics',
    'scheduler_state', 'schema_migrations'
]

# Files to analyze (production code only)
SEARCH_DIRS = [
    '/opt/DrummondGeometry-evals/src/dgas',
]

# SQL patterns that indicate table usage
SQL_PATTERNS = [
    r'FROM\s+(\w+)',
    r'JOIN\s+(\w+)',
    r'INSERT\s+INTO\s+(\w+)',
    r'UPDATE\s+(\w+)',
    r'DELETE\s+FROM\s+(\w+)',
]


def find_table_references():
    """Find all table references in production code."""
    references = defaultdict(set)

    for search_dir in SEARCH_DIRS:
        for root, dirs, files in os.walk(search_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)

                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            content = f.read()

                        # Find SQL table references
                        for pattern in SQL_PATTERNS:
                            matches = re.findall(pattern, content, re.IGNORECASE)
                            for match in matches:
                                table = match.lower()
                                if table in TABLES:
                                    references[table].add(filepath)
                    except Exception as e:
                        print(f'Error reading {filepath}: {e}')

    return references


def analyze_usage():
    """Analyze which tables are used vs unused."""
    print('=' * 80)
    print('DATABASE USAGE ANALYSIS')
    print('=' * 80)
    print()

    # Find table references
    references = find_table_references()

    # Get row counts from database
    from dgas.db import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Get row counts
            cur.execute('''
                SELECT relname as table_name, n_live_tup as live_rows
                FROM pg_stat_user_tables
                ORDER BY relname
            ''')

            row_counts = {row[0]: row[1] for row in cur.fetchall()}

    # Analyze each table
    print(f'{"Table":<35} {"Used":>8} {"Rows":>12} {"Status":<20} {"Files":<20}')
    print('-' * 100)

    used_tables = set()
    unused_tables = set()
    empty_tables = set()
    migration_tables = set()

    for table in sorted(TABLES):
        is_used = table in references
        row_count = row_counts.get(table, 0)

        if table == 'schema_migrations':
            status = 'Required (migration tracking)'
            files = f'{len(references.get(table, set()))} files'
            migration_tables.add(table)
        elif not is_used and row_count == 0:
            status = 'UNUSED - Empty'
            files = '-'
            unused_tables.add(table)
        elif not is_used:
            status = 'UNUSED - Has Data'
            files = f'{row_count} rows'
            unused_tables.add(table)
        elif row_count == 0:
            status = 'Used by Code - Empty'
            files = f'{len(references.get(table, set()))} files'
            empty_tables.add(table)
        else:
            status = 'Active'
            files = f'{len(references.get(table, set()))} files'
            used_tables.add(table)

        print(f'{table:<35} {"Yes" if is_used else "No":>8} {row_count:>12,} {status:<20} {files}')

    # Summary
    print()
    print('=' * 80)
    print('SUMMARY')
    print('=' * 80)
    print(f'Active Tables (used & has data): {len(used_tables)}')
    print(f'  {", ".join(sorted(used_tables))}')
    print()
    print(f'Used but Empty: {len(empty_tables)}')
    if empty_tables:
        print(f'  {", ".join(sorted(empty_tables))}')
    print()
    print(f'UNUSED Empty Tables (can be dropped): {len(unused_tables)}')
    if unused_tables:
        print(f'  {", ".join(sorted(unused_tables))}')
    print()
    print(f'Required (migration tracking): {len(migration_tables)}')
    print(f'  {", ".join(sorted(migration_tables))}')
    print()

    return {
        'used': used_tables,
        'empty': empty_tables,
        'unused': unused_tables,
        'migration': migration_tables,
        'references': references
    }


if __name__ == '__main__':
    analysis = analyze_usage()
