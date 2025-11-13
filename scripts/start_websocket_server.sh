#!/bin/bash
# Start WebSocket server for DGAS dashboard real-time updates

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="/var/log/dgas"

echo "════════════════════════════════════════════════════════════════════════════════"
echo "                    DGAS WebSocket Server Launcher"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Check if already running
if pgrep -f "dgas.dashboard.websocket_server" > /dev/null; then
    echo "⚠️  WebSocket server is already running"
    echo "   Use 'pkill -f dgas.dashboard.websocket_server' to stop it first"
    exit 1
fi

# Check environment
if [[ ! -f "$PROJECT_DIR/.env" ]]; then
    echo "❌ ERROR: .env file not found in $PROJECT_DIR"
    exit 1
fi

# Create log directory
mkdir -p "$LOG_DIR"

# Source environment
echo "📋 Loading environment..."
source "$PROJECT_DIR/.env"

# Check if uv is available
if ! command -v uv &> /dev/null; then
    echo "❌ ERROR: 'uv' command not found"
    exit 1
fi

echo "✅ Environment loaded"
echo ""

# Start the WebSocket server
echo "🚀 Starting WebSocket server..."
echo "   Host: localhost"
echo "   Port: 8765"
echo "   Log file: $LOG_DIR/websocket_server.log"
echo ""

cd "$PROJECT_DIR"
nohup /root/.local/bin/uv run python -m dgas.dashboard.websocket_server > "$LOG_DIR/websocket_server.log" 2>&1 &
WS_PID=$!

# Wait a moment for startup
sleep 3

# Check if process is running
if kill -0 "$WS_PID" 2>/dev/null; then
    echo "✅ WebSocket server started successfully (PID: $WS_PID)"
    echo ""
    echo "📊 Monitor the server:"
    echo "   - Logs: tail -f $LOG_DIR/websocket_server.log"
    echo "   - Status: ss -tuln | grep 8765"
    echo "   - Stop: pkill -f dgas.dashboard.websocket_server"
    echo ""
    echo "🔌 Connection: ws://localhost:8765"
else
    echo "❌ ERROR: WebSocket server failed to start"
    echo "   Check logs: $LOG_DIR/websocket_server.log"
    exit 1
fi

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                              SERVER READY"
echo "════════════════════════════════════════════════════════════════════════════════"