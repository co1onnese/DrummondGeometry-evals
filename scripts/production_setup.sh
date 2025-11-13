#!/bin/bash
# Production Setup Script for DGAS
# Sets up logging, monitoring, and systemd services

set -e

echo "=== DGAS Production Setup ==="
echo "Setting up logging, monitoring, and services..."
echo ""

# 1. Create log directory
echo "[1/6] Creating log directory..."
mkdir -p /var/log/dgas
chmod 755 /var/log/dgas

# 2. Setup log rotation
echo "[2/6] Setting up log rotation..."
cat > /etc/logrotate.d/dgas <<EOF
/var/log/dgas/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    sharedscripts
    postrotate
        systemctl reload dgas-dashboard || true
        systemctl reload dgas-scheduler || true
    endscript
}
EOF

# 3. Create monitoring script
echo "[3/6] Creating monitoring script..."
cat > /opt/DrummondGeometry-evals/scripts/monitor_system.sh <<'EOF'
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
EOF

chmod +x /opt/DrummondGeometry-evals/scripts/monitor_system.sh

# 4. Create cron job for monitoring
echo "[4/6] Setting up monitoring cron job..."
(crontab -l 2>/dev/null; echo "*/15 * * * * /opt/DrummondGeometry-evals/scripts/monitor_system.sh") | crontab -

# 5. Setup systemd service for monitoring
echo "[5/6] Setting up monitoring service..."
cat > /etc/systemd/system/dgas-monitor.service <<'EOF'
[Unit]
Description=DGAS System Monitor
After=network.target postgresql.service

[Service]
Type=oneshot
ExecStart=/opt/DrummondGeometry-evals/scripts/monitor_system.sh
User=root

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and start services
echo "[6/6] Enabling systemd services..."
systemctl daemon-reload
systemctl enable dgas-dashboard
systemctl enable dgas-scheduler
systemctl enable dgas-monitor

echo ""
echo "=== Production Setup Complete ==="
echo ""
echo "Services enabled:"
echo "  - dgas-dashboard: Dashboard on port 8501"
echo "  - dgas-scheduler: Prediction scheduler"
echo "  - dgas-monitor: System health monitoring"
echo ""
echo "Monitoring:"
echo "  - Health checks run every 15 minutes"
echo "  - Logs in: /var/log/dgas/"
echo "  - Log rotation: daily, keep 30 days"
echo ""
echo "Access dashboard at:"
echo "  - Local: http://localhost:8501"
echo "  - Public: http://93.127.160.30:8501"
echo ""
