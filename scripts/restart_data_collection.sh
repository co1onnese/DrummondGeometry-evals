#!/bin/bash
# Restart data collection service to clear stuck cycles

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_DIR"

echo "=== Restarting Data Collection Service ==="
echo

# Check if service is running
if screen -list | grep -q "data-collection"; then
    echo "Stopping existing data collection service..."
    screen -S data-collection -X quit || true
    sleep 2
fi

# Remove PID file if it exists
if [ -f .dgas_data_collection.pid ]; then
    echo "Removing stale PID file..."
    rm -f .dgas_data_collection.pid
fi

# Wait a moment for cleanup
sleep 2

# Start new service
echo "Starting data collection service..."
screen -dmS data-collection bash -c "cd $PROJECT_DIR && /root/.local/bin/uv run dgas data-collection start 2>&1 | tee /tmp/data_collection_startup.log"

sleep 3

# Check if it started
if screen -list | grep -q "data-collection"; then
    echo "✓ Service started successfully"
    echo
    echo "To view logs: screen -r data-collection"
    echo "To check status: uv run python -m dgas data-collection status"
else
    echo "✗ Failed to start service"
    echo "Check logs: cat /tmp/data_collection_startup.log"
    exit 1
fi
