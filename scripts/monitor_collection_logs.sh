#!/bin/bash
# Monitor data collection logs for 30 minutes to debug hangs and failures

MONITOR_DURATION=1800  # 30 minutes in seconds
LOG_FILE="/tmp/data_collection_monitor.log"
SCREEN_SESSION="data-collection"

echo "=== Data Collection Log Monitor ==="
echo "Monitoring for $((MONITOR_DURATION / 60)) minutes"
echo "Started at: $(date)"
echo ""

# Function to capture current state
capture_state() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo ""
    echo "=== [$timestamp] State Snapshot ==="
    
    # Check if service is running
    if screen -list | grep -q "$SCREEN_SESSION"; then
        echo "✓ Service is running"
    else
        echo "✗ Service is NOT running"
    fi
    
    # Get recent collection runs
    echo ""
    echo "Recent Collection Runs:"
    cd /opt/DrummondGeometry-evals
    uv run python -c "
from dgas.db import get_connection
from datetime import datetime, timezone
conn = get_connection().__enter__()
cur = conn.cursor()
cur.execute('''
    SELECT run_timestamp, status, symbols_requested, symbols_updated, 
           bars_fetched, bars_stored, execution_time_ms
    FROM data_collection_runs
    ORDER BY run_timestamp DESC
    LIMIT 3
''')
for row in cur.fetchall():
    ts = row[0]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
    print(f'  {ts.strftime(\"%H:%M:%S\")} ({age:.1f} min ago) | {row[1]} | {row[3]}/{row[2]} updated | {row[5]} bars stored | {row[6]/1000:.1f}s')
" 2>/dev/null || echo "  Error querying database"
    
    # Get screen session output
    echo ""
    echo "Recent Screen Output (last 20 lines):"
    screen -S "$SCREEN_SESSION" -X hardcopy /tmp/dc_snapshot.txt 2>/dev/null
    if [ -f /tmp/dc_snapshot.txt ]; then
        strings /tmp/dc_snapshot.txt | tail -20 | sed 's/^/  /'
    fi
    
    echo ""
}

# Initial state
capture_state > "$LOG_FILE"

# Monitor loop - check every 30 seconds
INTERVAL=30
ELAPSED=0
CHECK_COUNT=0

while [ $ELAPSED -lt $MONITOR_DURATION ]; do
    sleep $INTERVAL
    ELAPSED=$((ELAPSED + INTERVAL))
    CHECK_COUNT=$((CHECK_COUNT + 1))
    
    echo "[$CHECK_COUNT] Checking at $((ELAPSED / 60)) minutes..."
    
    # Capture state every check
    {
        echo ""
        echo "=== Check #$CHECK_COUNT at $((ELAPSED / 60)) minutes ==="
        capture_state
    } >> "$LOG_FILE"
    
    # Also check for specific patterns in real-time
    screen -S "$SCREEN_SESSION" -X hardcopy /tmp/dc_check.txt 2>/dev/null
    if [ -f /tmp/dc_check.txt ]; then
        # Look for important events
        if strings /tmp/dc_check.txt | grep -q "Collection cycle timed out"; then
            echo "⚠️  TIMEOUT DETECTED!" | tee -a "$LOG_FILE"
        fi
        if strings /tmp/dc_check.txt | grep -q "Collection cycle completed"; then
            echo "✓ Cycle completed!" | tee -a "$LOG_FILE"
        fi
        if strings /tmp/dc_check.txt | grep -q "Processing symbol"; then
            LAST_SYMBOL=$(strings /tmp/dc_check.txt | grep "Processing symbol" | tail -1)
            echo "  Last symbol: $LAST_SYMBOL" | tee -a "$LOG_FILE"
        fi
        if strings /tmp/dc_check.txt | grep -q "Batch.*complete"; then
            LAST_BATCH=$(strings /tmp/dc_check.txt | grep "Batch.*complete" | tail -1)
            echo "  $LAST_BATCH" | tee -a "$LOG_FILE"
        fi
        if strings /tc_check.txt 2>/dev/null | grep -q "error\|Error\|ERROR"; then
            ERRORS=$(strings /tmp/dc_check.txt | grep -i error | tail -3)
            echo "  Errors detected:" | tee -a "$LOG_FILE"
            echo "$ERRORS" | sed 's/^/    /' | tee -a "$LOG_FILE"
        fi
    fi
done

echo ""
echo "=== Monitoring Complete ==="
echo "Full log saved to: $LOG_FILE"
echo ""

# Generate summary
echo "=== Summary ==="
echo "Total monitoring time: $((MONITOR_DURATION / 60)) minutes"
echo "Checks performed: $CHECK_COUNT"
echo ""
echo "Recent collection runs:"
cd /opt/DrummondGeometry-evals
uv run python -c "
from dgas.db import get_connection
from datetime import datetime, timezone
conn = get_connection().__enter__()
cur = conn.cursor()
cur.execute('''
    SELECT run_timestamp, status, symbols_requested, symbols_updated, 
           bars_fetched, bars_stored, execution_time_ms
    FROM data_collection_runs
    WHERE run_timestamp > NOW() - INTERVAL '35 minutes'
    ORDER BY run_timestamp DESC
''')
runs = cur.fetchall()
if runs:
    for row in runs:
        ts = row[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        print(f'  {ts.strftime(\"%H:%M:%S\")} ({age:.1f} min ago) | {row[1]} | {row[3]}/{row[2]} updated | {row[5]} bars | {row[6]/1000:.1f}s')
else:
    print('  No runs in last 35 minutes')
" 2>/dev/null

echo ""
echo "Key events from log:"
grep -E "(TIMEOUT|completed|error|Error|Processing symbol|Batch.*complete)" "$LOG_FILE" | tail -20
