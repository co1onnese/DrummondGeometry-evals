#!/bin/bash
# Monitor data collection for 30 minutes
DURATION=1800
INTERVAL=30
LOG="/tmp/collection_monitor_$(date +%Y%m%d_%H%M%S).log"

echo "Monitoring data collection for 30 minutes..." | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "Log file: $LOG" | tee -a "$LOG"
echo ""

for i in $(seq 1 $((DURATION / INTERVAL))); do
    ELAPSED=$((i * INTERVAL))
    echo "" | tee -a "$LOG"
    echo "=== Check #$i at $((ELAPSED / 60)) minutes ===" | tee -a "$LOG"
    echo "Time: $(date)" | tee -a "$LOG"
    
    # Check service status
    if screen -list | grep -q data-collection; then
        echo "✓ Service running" | tee -a "$LOG"
    else
        echo "✗ Service NOT running" | tee -a "$LOG"
    fi
    
    # Get recent runs
    cd /opt/DrummondGeometry-evals
    echo "Recent runs:" | tee -a "$LOG"
    uv run python -c "
from dgas.db import get_connection
from datetime import datetime, timezone
try:
    conn = get_connection().__enter__()
    cur = conn.cursor()
    cur.execute('SELECT run_timestamp, status, symbols_updated, bars_stored, execution_time_ms FROM data_collection_runs ORDER BY run_timestamp DESC LIMIT 3')
    for r in cur.fetchall():
        ts = r[0]
        if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - ts).total_seconds() / 60
        print(f'  {ts.strftime(\"%H:%M:%S\")} ({age:.1f}m ago) | {r[1]} | {r[2]} updated | {r[3]} bars | {r[4]/1000:.1f}s')
except Exception as e:
    print(f'  Error: {e}')
" 2>&1 | tee -a "$LOG"
    
    # Get screen output
    screen -S data-collection -X hardcopy /tmp/dc_monitor.txt 2>/dev/null
    if [ -f /tmp/dc_monitor.txt ]; then
        echo "Recent log output:" | tee -a "$LOG"
        strings /tmp/dc_monitor.txt | tail -15 | grep -E "(Starting|Processing|Batch|complete|error|Error|timeout|API|symbol)" | head -10 | sed 's/^/  /' | tee -a "$LOG"
        
        # Check for specific events
        if strings /tmp/dc_monitor.txt | grep -qi "timeout\|timed out"; then
            echo "⚠️  TIMEOUT DETECTED!" | tee -a "$LOG"
        fi
        if strings /tmp/dc_monitor.txt | grep -qi "collection cycle completed"; then
            echo "✓ Cycle completed!" | tee -a "$LOG"
        fi
        LAST_SYMBOL=$(strings /tmp/dc_monitor.txt | grep "Processing symbol" | tail -1)
        if [ -n "$LAST_SYMBOL" ]; then
            echo "Last symbol processed: $LAST_SYMBOL" | tee -a "$LOG"
        fi
    fi
    
    sleep $INTERVAL
done

echo "" | tee -a "$LOG"
echo "=== Monitoring Complete ===" | tee -a "$LOG"
echo "Full log: $LOG" | tee -a "$LOG"
