#!/bin/bash
# DGAS Production Scheduler Startup Script
# This script starts the scheduler in production mode

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="/var/log/dgas"

echo "════════════════════════════════════════════════════════════════════════════════"
echo "                        DGAS PRODUCTION SCHEDULER LAUNCHER"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Check if environment file exists
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    echo "❌ ERROR: .env file not found in $SCRIPT_DIR"
    exit 1
fi

# Check if scheduler is already running
if [[ -f "$SCRIPT_DIR/.dgas_scheduler.pid" ]]; then
    PID=$(cat "$SCRIPT_DIR/.dgas_scheduler.pid")
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  WARNING: Scheduler is already running (PID: $PID)"
        echo "   Use 'dgas scheduler stop' to stop it first"
        exit 1
    else
        echo "🧹 Cleaning up stale PID file"
        rm -f "$SCRIPT_DIR/.dgas_scheduler.pid"
    fi
fi

# Create log directory if it doesn't exist
mkdir -p "$LOG_DIR"

# Source environment
echo "📋 Loading environment..."
source "$SCRIPT_DIR/.env"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ ERROR: 'uv' command not found"
    echo "   Please ensure uv is installed and in PATH"
    exit 1
fi

echo "✅ Environment loaded"
echo ""

# Start the scheduler
echo "🚀 Starting DGAS scheduler..."
echo "   Log file: $LOG_DIR/scheduler.log"
echo "   Configuration: $SCRIPT_DIR/config/production.yaml"
echo ""

# Start in background
cd "$SCRIPT_DIR"
nohup /root/.local/bin/uv run dgas scheduler start --daemon > "$LOG_DIR/scheduler.log" 2>&1 &
SCHEDULER_PID=$!

# Wait a moment for startup
sleep 3

# Check if process is running
if kill -0 "$SCHEDULER_PID" 2>/dev/null; then
    echo "✅ Scheduler started successfully (PID: $SCHEDULER_PID)"
    echo ""
    echo "📊 Monitor the scheduler:"
    echo "   - Logs: tail -f $LOG_DIR/scheduler.log"
    echo "   - Status: dgas scheduler status"
    echo "   - Stop: dgas scheduler stop"
    echo ""
    echo "🔔 Discord notifications will be sent for signals with confidence >= 0.65"
    echo "📊 View the dashboard: http://93.127.160.30:8501"
else
    echo "❌ ERROR: Scheduler failed to start"
    echo "   Check logs: $LOG_DIR/scheduler.log"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                              PRODUCTION READY"
echo "════════════════════════════════════════════════════════════════════════════════"
