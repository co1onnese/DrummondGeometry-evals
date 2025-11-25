#!/bin/bash
# DGAS Daily Health Check Script
# Runs hourly to verify all services are operational

LOG_FILE="/var/log/dgas/health_check.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')
PROJECT_DIR="/opt/DrummondGeometry-evals"

cd "$PROJECT_DIR" || exit 1

# Source environment if .env exists
if [ -f .env ]; then
    source .env
fi

echo "[$DATE] Starting health check..." >> "$LOG_FILE"

# Check data collection
if uv run dgas data-collection status > /dev/null 2>&1; then
    echo "[$DATE] ✓ Data collection: RUNNING" >> "$LOG_FILE"
else
    echo "[$DATE] ✗ Data collection: STOPPED" >> "$LOG_FILE"
fi

# Check prediction scheduler
if uv run dgas scheduler status > /dev/null 2>&1; then
    echo "[$DATE] ✓ Prediction scheduler: RUNNING" >> "$LOG_FILE"
else
    echo "[$DATE] ✗ Prediction scheduler: STOPPED" >> "$LOG_FILE"
fi

# Check dashboard
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 2>/dev/null || echo "000")
if [ "$HTTP_CODE" = "200" ]; then
    echo "[$DATE] ✓ Dashboard: RUNNING" >> "$LOG_FILE"
else
    echo "[$DATE] ✗ Dashboard: STOPPED (HTTP $HTTP_CODE)" >> "$LOG_FILE"
fi

# Check database (using dgas status which verifies DB connection)
if uv run dgas status 2>&1 | grep -q "Status: connected" > /dev/null 2>&1; then
    echo "[$DATE] ✓ Database: ACCESSIBLE" >> "$LOG_FILE"
elif [ -n "$DGAS_DATABASE_URL" ]; then
    # Fallback: check if URL is configured
    echo "[$DATE] ⚠ Database: URL configured but connection check failed" >> "$LOG_FILE"
else
    echo "[$DATE] ✗ Database: URL not configured" >> "$LOG_FILE"
fi

echo "[$DATE] Health check completed" >> "$LOG_FILE"
