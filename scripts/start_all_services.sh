#!/bin/bash
# Start all DGAS production services in screen sessions
# Usage: ./scripts/start_all_services.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_DIR="/var/log/dgas"

cd "$PROJECT_DIR"

# Source environment
if [ -f .env ]; then
    source .env
else
    echo "❌ ERROR: .env file not found in $PROJECT_DIR"
    exit 1
fi

echo "════════════════════════════════════════════════════════════════════════════════"
echo "                    Starting DGAS Production Services"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Check if services are already running
check_service() {
    local service_name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            echo "⚠️  WARNING: $service_name appears to be running (PID: $pid)"
            echo "   Use 'screen -r dgas_${service_name}' to check, or stop it first"
            return 1
        else
            echo "🧹 Cleaning up stale PID file: $pid_file"
            rm -f "$pid_file"
        fi
    fi
    return 0
}

# 1. Start Data Collection Service
echo "[1/3] Starting Data Collection Service..."
if check_service "data_collection" "$PROJECT_DIR/.dgas_data_collection.pid"; then
    screen -dmS dgas_data_collection bash -c "cd $PROJECT_DIR && source .env && exec uv run dgas data-collection start --config config/production.yaml 2>&1 | tee $LOG_DIR/data_collection.log"
    sleep 3
    if screen -list | grep -q "dgas_data_collection"; then
        echo "   ✓ Data collection service started in screen session"
        echo "   Attach with: screen -r dgas_data_collection"
    else
        echo "   ✗ Failed to start data collection service"
    fi
fi
echo ""

# 2. Start Prediction Scheduler
echo "[2/3] Starting Prediction Scheduler..."
if check_service "prediction_scheduler" "$PROJECT_DIR/.dgas_scheduler.pid"; then
    screen -dmS dgas_prediction_scheduler bash -c "cd $PROJECT_DIR && source .env && exec uv run dgas scheduler start --daemon --config config/production.yaml 2>&1 | tee $LOG_DIR/scheduler.log"
    sleep 3
    if screen -list | grep -q "dgas_prediction_scheduler"; then
        echo "   ✓ Prediction scheduler started in screen session"
        echo "   Attach with: screen -r dgas_prediction_scheduler"
    else
        echo "   ✗ Failed to start prediction scheduler"
    fi
fi
echo ""

# 3. Start Dashboard
echo "[3/3] Starting Dashboard..."
if screen -list | grep -q "dgas_dashboard"; then
    echo "   ⚠️  WARNING: Dashboard screen session already exists"
    echo "   Use 'screen -r dgas_dashboard' to check, or 'screen -X -S dgas_dashboard quit' to stop"
else
    # Check if dashboard dependencies are installed
    if ! uv run python -c "import streamlit; import plotly" 2>/dev/null; then
        echo "   ⚠️  Dashboard dependencies not found, installing..."
        uv sync --extra dashboard > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo "   ✓ Dashboard dependencies installed"
        else
            echo "   ✗ Failed to install dashboard dependencies"
            echo "   Dashboard will not start. Install manually: uv sync --extra dashboard"
        fi
    fi
    
    screen -dmS dgas_dashboard bash -c "cd $PROJECT_DIR && source .env && exec uv run python run_dashboard.py 2>&1 | tee $LOG_DIR/dashboard.log"
    sleep 5
    if screen -list | grep -q "dgas_dashboard"; then
        echo "   ✓ Dashboard started in screen session"
        echo "   Attach with: screen -r dgas_dashboard"
        echo "   Access at: http://localhost:8501"
    else
        echo "   ✗ Failed to start dashboard"
        echo "   Check logs: $LOG_DIR/dashboard.log"
    fi
fi
echo ""

# Wait a moment for services to initialize
echo "Waiting for services to initialize..."
sleep 5

# Verify services
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                          Service Status Check"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""

# Check data collection
echo -n "Data Collection: "
if uv run dgas data-collection status > /dev/null 2>&1; then
    echo "✓ RUNNING"
else
    echo "✗ NOT RUNNING (check logs: $LOG_DIR/data_collection.log)"
fi

# Check prediction scheduler
echo -n "Prediction Scheduler: "
if uv run dgas scheduler status > /dev/null 2>&1; then
    echo "✓ RUNNING"
else
    echo "✗ NOT RUNNING (check logs: $LOG_DIR/scheduler.log)"
fi

# Check dashboard
echo -n "Dashboard: "
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ RUNNING (HTTP $HTTP_CODE)"
else
    echo "✗ NOT RUNNING (HTTP $HTTP_CODE, check logs: $LOG_DIR/dashboard.log)"
fi

echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
echo "                          Management Commands"
echo "════════════════════════════════════════════════════════════════════════════════"
echo ""
echo "View all screen sessions:"
echo "  screen -ls"
echo ""
echo "Attach to sessions:"
echo "  screen -r dgas_data_collection"
echo "  screen -r dgas_prediction_scheduler"
echo "  screen -r dgas_dashboard"
echo ""
echo "Stop services:"
echo "  uv run dgas data-collection stop"
echo "  uv run dgas scheduler stop"
echo "  screen -X -S dgas_dashboard quit"
echo ""
echo "View logs:"
echo "  tail -f $LOG_DIR/data_collection.log"
echo "  tail -f $LOG_DIR/scheduler.log"
echo "  tail -f $LOG_DIR/dashboard.log"
echo ""
echo "════════════════════════════════════════════════════════════════════════════════"
