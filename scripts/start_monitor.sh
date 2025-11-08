#!/bin/bash
# Start the evaluation monitor in the background

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="$SCRIPT_DIR/monitor_evaluation.py"
MONITOR_LOG="/tmp/evaluation_monitor.log"
MONITOR_PID_FILE="/tmp/evaluation_monitor.pid"

# Check if monitor is already running
if [ -f "$MONITOR_PID_FILE" ]; then
    OLD_PID=$(cat "$MONITOR_PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        echo "Monitor is already running (PID: $OLD_PID)"
        echo "To stop it: kill $OLD_PID"
        exit 1
    else
        # Stale PID file
        rm "$MONITOR_PID_FILE"
    fi
fi

# Start monitor
echo "Starting evaluation monitor..."
echo "Monitor log: $MONITOR_LOG"
echo "PID file: $MONITOR_PID_FILE"

cd "$SCRIPT_DIR/.."
source .venv/bin/activate

python3 "$MONITOR_SCRIPT" > "$MONITOR_LOG" 2>&1 &
MONITOR_PID=$!

echo "$MONITOR_PID" > "$MONITOR_PID_FILE"
echo "Monitor started with PID: $MONITOR_PID"
echo ""
echo "To view monitor output:"
echo "  tail -f $MONITOR_LOG"
echo ""
echo "To stop monitor:"
echo "  kill $MONITOR_PID"
echo "  rm $MONITOR_PID_FILE"
