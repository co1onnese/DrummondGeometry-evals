#!/bin/bash
# DGAS System Health Monitor

LOGFILE="/var/log/dgas/monitor.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Check database connectivity
DB_CHECK=$(sudo -u postgres psql -d dgas -t -c "SELECT COUNT(*) FROM market_symbols;" 2>&1 || echo "FAIL")
if [[ $DB_CHECK =~ FAIL ]]; then
    echo "[$TIMESTAMP] ERROR: Database connection failed" >> $LOGFILE
    exit 1
fi

# Check dashboard
DASHBOARD_CHECK=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 2>&1 || echo "000")
if [[ $DASHBOARD_CHECK != "200" ]]; then
    echo "[$TIMESTAMP] WARNING: Dashboard not responding (HTTP $DASHBOARD_CHECK)" >> $LOGFILE
fi

# Check scheduler
if [[ -f /opt/DrummondGeometry-evals/.dgas_scheduler.pid ]]; then
    SCHEDULER_PID=$(cat /opt/DrummondGeometry-evals/.dgas_scheduler.pid)
    if ! kill -0 $SCHEDULER_PID 2>/dev/null; then
        echo "[$TIMESTAMP] WARNING: Scheduler process not running" >> $LOGFILE
    fi
else
    echo "[$TIMESTAMP] INFO: Scheduler not running" >> $LOGFILE
fi

# Disk space check
DISK_USAGE=$(df /opt/DrummondGeometry-evals | tail -1 | awk '{print $5}' | sed 's/%//')
if [[ $DISK_USAGE -gt 85 ]]; then
    echo "[$TIMESTAMP] WARNING: Disk usage at ${DISK_USAGE}%" >> $LOGFILE
fi

# Memory check
MEMORY_USAGE=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100.0}')
if [[ $MEMORY_USAGE -gt 80 ]]; then
    echo "[$TIMESTAMP] WARNING: Memory usage at ${MEMORY_USAGE}%" >> $LOGFILE
fi

echo "[$TIMESTAMP] INFO: System health check completed" >> $LOGFILE
