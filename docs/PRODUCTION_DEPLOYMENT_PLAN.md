# DGAS Production Deployment Plan

**Version**: 1.0  
**Date**: 2025-11-10  
**Purpose**: Comprehensive plan for deploying DGAS in production with 24/7 data collection, signal generation, and Discord notifications

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Pre-Deployment Verification](#pre-deployment-verification)
3. [System Architecture Overview](#system-architecture-overview)
4. [Component Setup](#component-setup)
5. [Data Collection Service](#data-collection-service)
6. [Prediction Scheduler](#prediction-scheduler)
7. [Dashboard Service](#dashboard-service)
8. [Discord Notification Setup](#discord-notification-setup)
9. [Monitoring & Health Checks](#monitoring--health-checks)
10. [Startup Sequence](#startup-sequence)
11. [Verification Procedures](#verification-procedures)
12. [Troubleshooting Guide](#troubleshooting-guide)
13. [Maintenance Procedures](#maintenance-procedures)

---

## Executive Summary

This plan outlines the deployment of the Drummond Geometry Analysis System (DGAS) for 24/7 production operation. The system will:

- **Continuously collect market data** for 517+ US stocks via EODHD API
- **Generate trading signals** every 15 minutes during market hours
- **Post alerts to Discord** when signals with confidence ≥ 65% are generated
- **Serve a real-time dashboard** for monitoring and analysis
- **Run all services under screen sessions** for persistence and recovery

### Key Components

1. **Data Collection Service**: 24/7 data ingestion with WebSocket (market hours) and REST API (after-hours)
2. **Prediction Scheduler**: Automated signal generation every 15 minutes
3. **Dashboard**: Streamlit web interface on port 8501
4. **Discord Integration**: Automated alerts for high-confidence signals

---

## Pre-Deployment Verification

### 1. Database Status Check

**Objective**: Verify PostgreSQL is running and accessible with correct configuration.

```bash
# Check PostgreSQL status
sudo systemctl status postgresql

# Verify database connection
psql -h localhost -U fireworks_app -d dgas -c "SELECT COUNT(*) FROM market_symbols;"

# Expected: Should return count of registered symbols (517+)
```

**Verification Points**:
- [ ] PostgreSQL service is running
- [ ] Database connection string in `.env` is correct
- [ ] Database user has proper permissions
- [ ] All migrations have been applied

**Commands**:
```bash
# Check database migrations
cd /opt/DrummondGeometry-evals
uv run python -m dgas.db.migrations

# Verify connection from Python
uv run python -c "from dgas.db import get_connection; list(get_connection())"
```

### 2. Historical Data Verification

**Objective**: Confirm all historical data has been backfilled correctly.

```bash
# Run data gap check script
cd /opt/DrummondGeometry-evals
uv run python scripts/check_data_gaps.py --interval 30m --target-date $(date +%Y-%m-%d)

# Check specific symbol coverage
uv run dgas data quality-report --symbol AAPL --interval 30m

# Verify data freshness
uv run python scripts/verify_data_freshness.py
```

**Verification Points**:
- [ ] All 517+ symbols have data
- [ ] Data is current up to today (or most recent trading day)
- [ ] No significant gaps in 30m interval data
- [ ] Data quality metrics are acceptable

**Expected Results**:
- All symbols should have data up to the most recent trading day
- Latest timestamps should be within 24 hours of current time (for active trading days)
- No symbols should show "no data" status

### 3. Environment Configuration

**Objective**: Verify all required environment variables are set.

```bash
# Check .env file exists
ls -la /opt/DrummondGeometry-evals/.env

# Verify critical variables (without exposing secrets)
grep -E "^[A-Z_]+=" /opt/DrummondGeometry-evals/.env | cut -d'=' -f1
```

**Required Environment Variables**:
- [ ] `EODHD_API_TOKEN` - EODHD API authentication token
- [ ] `DGAS_DATABASE_URL` - PostgreSQL connection string
- [ ] `DGAS_DATA_DIR` - Local data directory path
- [ ] `DGAS_DISCORD_BOT_TOKEN` - Discord bot token (for notifications)
- [ ] `DGAS_DISCORD_CHANNEL_ID` - Discord channel ID (for notifications)

**Verification**:
```bash
# Test environment loading
cd /opt/DrummondGeometry-evals
source .env
echo "EODHD token set: $([ -n "$EODHD_API_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Database URL set: $([ -n "$DGAS_DATABASE_URL" ] && echo 'YES' || echo 'NO')"
echo "Discord token set: $([ -n "$DGAS_DISCORD_BOT_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Discord channel set: $([ -n "$DGAS_DISCORD_CHANNEL_ID" ] && echo 'YES' || echo 'NO')"
```

### 4. Configuration File Check

**Objective**: Verify production configuration file is correct.

```bash
# Check production config exists
ls -la /opt/DrummondGeometry-evals/config/production.yaml

# Validate configuration
cd /opt/DrummondGeometry-evals
uv run dgas configure validate --config config/production.yaml
```

**Key Configuration Points**:
- [ ] Data collection enabled: `data_collection.enabled: true`
- [ ] WebSocket enabled: `data_collection.use_websocket: true`
- [ ] Discord notifications enabled: `notifications.discord.enabled: true`
- [ ] Scheduler cron expression: `*/15 * * * *` (every 15 minutes)
- [ ] Minimum confidence threshold: `prediction.min_confidence: 0.65`

---

## System Architecture Overview

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Production Server                        │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  Screen Session  │  │  Screen Session  │                │
│  │  Data Collection │  │  Prediction      │                │
│  │  Scheduler       │  │  Scheduler       │                │
│  └────────┬─────────┘  └────────┬────────┘                │
│           │                      │                          │
│           └──────────┬───────────┘                          │
│                      │                                      │
│           ┌──────────▼──────────┐                           │
│           │   PostgreSQL DB     │                           │
│           │   (Historical Data) │                           │
│           └──────────┬──────────┘                           │
│                      │                                      │
│  ┌───────────────────▼──────────────────┐                  │
│  │     Screen Session: Dashboard        │                  │
│  │     Streamlit on port 8501           │                  │
│  └──────────────────────────────────────┘                  │
│                                                             │
│  ┌──────────────────────────────────────┐                 │
│  │  External Services                    │                 │
│  │  • EODHD API (Market Data)            │                 │
│  │  • Discord API (Notifications)        │                 │
│  └──────────────────────────────────────┘                 │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Data Collection**:
   - EODHD API → Data Collection Service → PostgreSQL
   - WebSocket (market hours) or REST API (after-hours)
   - Runs continuously with dynamic intervals

2. **Signal Generation**:
   - Prediction Scheduler → Loads data from PostgreSQL
   - Calculates Drummond Geometry indicators
   - Generates signals with confidence scores
   - Filters signals (min confidence: 0.65)

3. **Notifications**:
   - Generated signals → Discord Adapter → Discord Channel
   - Only signals with confidence ≥ 65% are sent

4. **Dashboard**:
   - Reads from PostgreSQL
   - Displays real-time updates via WebSocket
   - Shows signals, predictions, system status

---

## Component Setup

### 1. Screen Installation

**Objective**: Install and configure screen for persistent sessions.

```bash
# Install screen if not already installed
sudo apt-get update
sudo apt-get install -y screen

# Verify installation
screen -v

# Create screen configuration (optional)
cat > ~/.screenrc << 'EOF'
# Screen configuration for DGAS
startup_message off
defscrollback 10000
hardstatus alwayslastline
hardstatus string '%{= kG}[ %{G}%H %{g}][%= %{= kw}%?%-Lw%?%{r}(%{W}%n*%f%t%?(%u)%?%{r})%{w}%?%+Lw%?%?%= %{g}][%{B} %m-%d %{W}%c %{g}]'
EOF
```

### 2. Log Directory Setup

**Objective**: Create centralized logging directory.

```bash
# Create log directory
sudo mkdir -p /var/log/dgas
sudo chown $USER:$USER /var/log/dgas
chmod 755 /var/log/dgas

# Verify
ls -ld /var/log/dgas
```

### 3. Working Directory

**Objective**: Ensure proper working directory structure.

```bash
# Navigate to project root
cd /opt/DrummondGeometry-evals

# Verify structure
ls -la
# Should see: src/, config/, scripts/, .env, etc.

# Check permissions
ls -ld /opt/DrummondGeometry-evals
```

---

## Data Collection Service

### Overview

The data collection service runs 24/7 to continuously gather market data. It uses:
- **WebSocket** during market hours (9:30 AM - 4:00 PM ET, Mon-Fri) for real-time data
- **REST API** for after-hours and weekends
- **Dynamic intervals**: 30m during market hours, 30m after hours, 30m weekends

### Configuration

The service is configured in `config/production.yaml`:

```yaml
data_collection:
  enabled: true
  use_websocket: true
  websocket_interval: "30m"
  interval_market_hours: "30m"
  interval_after_hours: "30m"
  interval_weekends: "30m"
  batch_size: 50
  max_concurrent_batches: 1
  requests_per_minute: 80
  max_retries: 3
  retry_delay_seconds: 5
```

### Starting the Service

**Method 1: Using Screen (Recommended)**

```bash
# Create a new screen session for data collection
screen -S dgas_data_collection

# Navigate to project directory
cd /opt/DrummondGeometry-evals

# Load environment
source .env

# Start data collection service
uv run dgas data-collection start --daemon --config config/production.yaml

# Detach from screen: Press Ctrl+A, then D
# Reattach later: screen -r dgas_data_collection
```

**Method 2: Using nohup (Alternative)**

```bash
cd /opt/DrummondGeometry-evals
source .env
nohup uv run dgas data-collection start --daemon --config config/production.yaml > /var/log/dgas/data_collection.log 2>&1 &
echo $! > .dgas_data_collection.pid
```

### Verifying Data Collection

```bash
# Check service status
uv run dgas data-collection status

# View recent statistics
uv run dgas data-collection stats --config config/production.yaml

# Check data freshness
uv run python scripts/verify_data_freshness.py

# Monitor logs
tail -f /var/log/dgas/data_collection.log
```

### Expected Behavior

- Service starts and connects to EODHD API
- During market hours: WebSocket connection established
- After market hours: Switches to REST API polling
- Logs show collection cycles with success/failure counts
- Database receives new bars every 30 minutes (or configured interval)

### Troubleshooting Data Collection

**Issue**: Service not starting
```bash
# Check if already running
uv run dgas data-collection status

# Check logs
tail -50 /var/log/dgas/data_collection.log

# Verify API token
echo $EODHD_API_TOKEN | head -c 10  # Should show first 10 chars
```

**Issue**: No data being collected
```bash
# Test API connection
uv run python scripts/test_eodhd_api_direct.py

# Check database connection
uv run python -c "from dgas.db import get_connection; list(get_connection())"

# Run manual collection cycle
uv run dgas data-collection run-once --config config/production.yaml
```

**Issue**: WebSocket not connecting
```bash
# Check if market is open
uv run python -c "from dgas.prediction.scheduler import MarketHoursManager, TradingSession; m = MarketHoursManager('US', TradingSession()); print('Market open:', m.is_market_open(datetime.now(timezone.utc)))"

# Verify WebSocket configuration
grep -A 5 "use_websocket" config/production.yaml
```

---

## Prediction Scheduler

### Overview

The prediction scheduler runs every 15 minutes to:
1. Load latest market data from database
2. Calculate Drummond Geometry indicators
3. Generate trading signals with confidence scores
4. Filter signals (min confidence: 0.65)
5. Send notifications to Discord for qualifying signals

### Configuration

Configured in `config/production.yaml`:

```yaml
scheduler:
  cron_expression: "*/15 * * * *"  # Every 15 minutes
  timezone: America/New_York
  market_hours_only: false  # Run 24/7

prediction:
  min_confidence: 0.65  # Only signals with 65%+ confidence
  min_signal_strength: 0.60
  stop_loss_atr_multiplier: 1.5
  target_atr_multiplier: 2.5
```

### Starting the Scheduler

**Method 1: Using Screen (Recommended)**

```bash
# Create a new screen session for prediction scheduler
screen -S dgas_prediction_scheduler

# Navigate to project directory
cd /opt/DrummondGeometry-evals

# Load environment
source .env

# Start prediction scheduler
uv run dgas scheduler start --daemon --config config/production.yaml

# Detach from screen: Press Ctrl+A, then D
# Reattach later: screen -r dgas_prediction_scheduler
```

**Method 2: Using the Production Script**

```bash
cd /opt/DrummondGeometry-evals
./start_production.sh
```

### Verifying Prediction Scheduler

```bash
# Check scheduler status
uv run dgas scheduler status

# View recent prediction runs
uv run dgas report recent-signals --hours 24

# Check scheduler logs
tail -f ~/.dgas/logs/scheduler.log
# Or if using production script:
tail -f /var/log/dgas/scheduler.log

# Run manual prediction cycle
uv run dgas scheduler run-once --config config/production.yaml
```

### Expected Behavior

- Scheduler starts and registers cron job
- Every 15 minutes: Prediction cycle executes
- Logs show symbols processed, signals generated
- Discord notifications sent for signals with confidence ≥ 65%
- Database records prediction runs and generated signals

### Troubleshooting Prediction Scheduler

**Issue**: Scheduler not running
```bash
# Check status
uv run dgas scheduler status

# Check for PID file
ls -la .dgas_scheduler.pid

# Check logs
tail -50 ~/.dgas/logs/scheduler.log
```

**Issue**: No signals generated
```bash
# Check if data is fresh
uv run python scripts/verify_data_freshness.py

# Run manual prediction
uv run dgas predict AAPL MSFT --config config/production.yaml

# Check prediction configuration
grep -A 10 "prediction:" config/production.yaml
```

**Issue**: Discord notifications not working
- See [Discord Notification Setup](#discord-notification-setup) section

---

## Dashboard Service

### Overview

The dashboard provides a web-based interface for:
- Viewing recent signals and predictions
- Monitoring system status
- Analyzing market data
- Real-time updates via WebSocket

### Starting the Dashboard

**Method 1: Using Screen (Recommended)**

```bash
# Create a new screen session for dashboard
screen -S dgas_dashboard

# Navigate to project directory
cd /opt/DrummondGeometry-evals

# Load environment
source .env

# Start dashboard
uv run python run_dashboard.py

# Or directly:
uv run streamlit run src/dgas/dashboard/app.py --server.port=8501 --server.address=0.0.0.0

# Detach from screen: Press Ctrl+A, then D
# Reattach later: screen -r dgas_dashboard
```

**Method 2: Using nohup**

```bash
cd /opt/DrummondGeometry-evals
source .env
nohup uv run python run_dashboard.py > /var/log/dgas/dashboard.log 2>&1 &
echo $! > .dgas_dashboard.pid
```

### Accessing the Dashboard

- **Local**: http://localhost:8501
- **Remote**: http://93.127.160.30:8501 (if firewall allows)

### Verifying Dashboard

```bash
# Check if dashboard is running
ps aux | grep streamlit

# Check port
netstat -tuln | grep 8501

# Test HTTP response
curl -I http://localhost:8501

# Check logs
tail -f /var/log/dgas/dashboard.log
```

### Expected Behavior

- Dashboard starts and binds to port 8501
- Web interface loads with navigation menu
- Pages show data from database
- Real-time updates via WebSocket (if configured)

### Troubleshooting Dashboard

**Issue**: Dashboard not loading
```bash
# Check if port is in use
lsof -i :8501

# Check Streamlit installation
uv run streamlit --version

# Check logs for errors
tail -50 /var/log/dgas/dashboard.log
```

**Issue**: No data showing
```bash
# Verify database connection
uv run dgas status --check-database

# Check if data exists
uv run dgas data quality-report --symbol AAPL
```

---

## Discord Notification Setup

### Overview

Discord notifications are sent automatically when trading signals with confidence ≥ 65% are generated. The system uses Discord Bot API (not webhooks) for richer formatting.

### Prerequisites

1. **Discord Bot Token**: Create a Discord bot and obtain the token
2. **Discord Channel ID**: Get the channel ID where notifications should be posted
3. **Bot Permissions**: Bot needs "Send Messages" permission in the channel

### Configuration

**Environment Variables** (in `.env`):
```bash
DGAS_DISCORD_BOT_TOKEN=your_bot_token_here
DGAS_DISCORD_CHANNEL_ID=your_channel_id_here
```

**Configuration File** (`config/production.yaml`):
```yaml
notifications:
  discord:
    enabled: true
    # Token and channel ID come from environment variables
```

### Setting Up Discord Bot

1. **Create Discord Application**:
   - Go to https://discord.com/developers/applications
   - Click "New Application"
   - Name it (e.g., "DGAS Trading Signals")

2. **Create Bot**:
   - Go to "Bot" section
   - Click "Add Bot"
   - Copy the bot token (this is `DGAS_DISCORD_BOT_TOKEN`)

3. **Get Channel ID**:
   - Enable Developer Mode in Discord (User Settings → Advanced → Developer Mode)
   - Right-click on the channel → "Copy ID"
   - This is `DGAS_DISCORD_CHANNEL_ID`

4. **Invite Bot to Server**:
   - Go to "OAuth2" → "URL Generator"
   - Select "bot" scope
   - Select "Send Messages" permission
   - Copy the generated URL and open it in browser
   - Select your server and authorize

### Verifying Discord Setup

```bash
# Test Discord configuration
cd /opt/DrummondGeometry-evals
source .env

# Check environment variables
echo "Bot token set: $([ -n "$DGAS_DISCORD_BOT_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Channel ID set: $([ -n "$DGAS_DISCORD_CHANNEL_ID" ] && echo 'YES' || echo 'NO')"

# Test Discord connection (if test script exists)
uv run python scripts/test_discord_send.py
```

### Expected Behavior

- When a signal with confidence ≥ 65% is generated:
  - Discord adapter creates a rich embed with signal details
  - Embed includes: symbol, signal type, entry price, stop loss, target, confidence
  - Message is posted to configured Discord channel
  - Logs show successful Discord post

### Troubleshooting Discord Notifications

**Issue**: Notifications not being sent
```bash
# Verify environment variables
grep -E "DGAS_DISCORD" .env

# Check notification configuration
grep -A 5 "notifications:" config/production.yaml

# Test Discord API directly
uv run python scripts/test_discord_send.py
```

**Issue**: "401 Unauthorized" error
- Bot token is invalid or expired
- Regenerate token in Discord Developer Portal

**Issue**: "403 Forbidden" error
- Bot doesn't have permission to send messages
- Re-invite bot with "Send Messages" permission

**Issue**: "404 Not Found" error
- Channel ID is incorrect
- Verify channel ID by right-clicking channel → Copy ID

---

## Monitoring & Health Checks

### System Health Monitoring

**Daily Health Check Script**:

```bash
#!/bin/bash
# /opt/DrummondGeometry-evals/scripts/daily_health_check.sh

LOG_FILE="/var/log/dgas/health_check.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

echo "[$DATE] Starting health check..." >> $LOG_FILE

# Check data collection
if uv run dgas data-collection status > /dev/null 2>&1; then
    echo "[$DATE] ✓ Data collection: RUNNING" >> $LOG_FILE
else
    echo "[$DATE] ✗ Data collection: STOPPED" >> $LOG_FILE
fi

# Check prediction scheduler
if uv run dgas scheduler status > /dev/null 2>&1; then
    echo "[$DATE] ✓ Prediction scheduler: RUNNING" >> $LOG_FILE
else
    echo "[$DATE] ✗ Prediction scheduler: STOPPED" >> $LOG_FILE
fi

# Check dashboard
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 | grep -q "200"; then
    echo "[$DATE] ✓ Dashboard: RUNNING" >> $LOG_FILE
else
    echo "[$DATE] ✗ Dashboard: STOPPED" >> $LOG_FILE
fi

# Check database
if psql -h localhost -U fireworks_app -d dgas -c "SELECT 1;" > /dev/null 2>&1; then
    echo "[$DATE] ✓ Database: ACCESSIBLE" >> $LOG_FILE
else
    echo "[$DATE] ✗ Database: INACCESSIBLE" >> $LOG_FILE
fi

echo "[$DATE] Health check completed" >> $LOG_FILE
```

**Set up cron job**:
```bash
# Add to crontab (runs every hour)
(crontab -l 2>/dev/null; echo "0 * * * * /opt/DrummondGeometry-evals/scripts/daily_health_check.sh") | crontab -
```

### Key Metrics to Monitor

1. **Data Collection**:
   - Collection cycle success rate
   - Data freshness (latest timestamp)
   - Symbols updated per cycle
   - API error rate

2. **Prediction Scheduler**:
   - Prediction cycle execution time
   - Signals generated per cycle
   - Discord notification success rate
   - Error rate

3. **Database**:
   - Connection pool usage
   - Query performance
   - Database size growth
   - Index usage

4. **System Resources**:
   - CPU usage
   - Memory usage
   - Disk space
   - Network connectivity

### Monitoring Commands

```bash
# Overall system status
uv run dgas status

# Data collection statistics
uv run dgas data-collection stats

# Recent signals
uv run dgas report recent-signals --hours 24

# Performance metrics
uv run dgas monitor --summary --hours 24

# Data freshness
uv run python scripts/verify_data_freshness.py
```

---

## Startup Sequence

### Complete Production Startup

**Step-by-step procedure**:

```bash
# 1. Navigate to project directory
cd /opt/DrummondGeometry-evals

# 2. Load environment
source .env

# 3. Verify database is running
sudo systemctl status postgresql
# If not running: sudo systemctl start postgresql

# 4. Start data collection service (in screen)
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --daemon --config config/production.yaml
# Press Ctrl+A, then D to detach

# 5. Start prediction scheduler (in screen)
screen -S dgas_prediction_scheduler
cd /opt/DrummondGeometry-evals
source .env
uv run dgas scheduler start --daemon --config config/production.yaml
# Press Ctrl+A, then D to detach

# 6. Start dashboard (in screen)
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
# Press Ctrl+A, then D to detach

# 7. Verify all services
uv run dgas status
uv run dgas data-collection status
uv run dgas scheduler status
curl -I http://localhost:8501
```

### Quick Startup Script

Create `/opt/DrummondGeometry-evals/scripts/start_all_services.sh`:

```bash
#!/bin/bash
# Start all DGAS production services

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
source .env

echo "Starting DGAS production services..."

# Start data collection
echo "Starting data collection service..."
screen -dmS dgas_data_collection bash -c "cd $PROJECT_DIR && source .env && uv run dgas data-collection start --daemon --config config/production.yaml"

# Start prediction scheduler
echo "Starting prediction scheduler..."
screen -dmS dgas_prediction_scheduler bash -c "cd $PROJECT_DIR && source .env && uv run dgas scheduler start --daemon --config config/production.yaml"

# Start dashboard
echo "Starting dashboard..."
screen -dmS dgas_dashboard bash -c "cd $PROJECT_DIR && source .env && uv run python run_dashboard.py"

sleep 5

# Verify services
echo ""
echo "Verifying services..."
uv run dgas data-collection status && echo "✓ Data collection: RUNNING" || echo "✗ Data collection: FAILED"
uv run dgas scheduler status && echo "✓ Prediction scheduler: RUNNING" || echo "✗ Prediction scheduler: FAILED"
curl -s -o /dev/null -w "%{http_code}" http://localhost:8501 | grep -q "200" && echo "✓ Dashboard: RUNNING" || echo "✗ Dashboard: FAILED"

echo ""
echo "All services started. Use 'screen -r <session_name>' to attach to sessions."
echo "  - Data collection: screen -r dgas_data_collection"
echo "  - Prediction scheduler: screen -r dgas_prediction_scheduler"
echo "  - Dashboard: screen -r dgas_dashboard"
```

**Make executable**:
```bash
chmod +x /opt/DrummondGeometry-evals/scripts/start_all_services.sh
```

**Usage**:
```bash
/opt/DrummondGeometry-evals/scripts/start_all_services.sh
```

---

## Verification Procedures

### Post-Deployment Verification

**1. Verify Data Collection**:
```bash
# Check service status
uv run dgas data-collection status

# Check recent collection runs
uv run dgas data-collection stats

# Verify data is being collected
uv run python scripts/verify_data_freshness.py

# Check database for new data
psql -h localhost -U fireworks_app -d dgas -c "SELECT COUNT(*) FROM market_data WHERE timestamp > NOW() - INTERVAL '1 hour';"
```

**2. Verify Prediction Scheduler**:
```bash
# Check scheduler status
uv run dgas scheduler status

# View recent prediction runs
uv run dgas report recent-signals --hours 24

# Check database for prediction runs
psql -h localhost -U fireworks_app -d dgas -c "SELECT COUNT(*) FROM prediction_runs WHERE run_timestamp > NOW() - INTERVAL '1 hour';"
```

**3. Verify Discord Notifications**:
```bash
# Check Discord configuration
grep -E "DGAS_DISCORD" .env

# Test Discord connection (if test script exists)
uv run python scripts/test_discord_send.py

# Generate a test signal (if possible)
uv run dgas predict AAPL --config config/production.yaml
# Check Discord channel for notification
```

**4. Verify Dashboard**:
```bash
# Check dashboard is accessible
curl -I http://localhost:8501

# Check dashboard process
ps aux | grep streamlit

# Open dashboard in browser and verify:
# - Overview page loads
# - Recent signals are visible
# - System status shows green
```

### Daily Verification Checklist

- [ ] Data collection service is running
- [ ] Prediction scheduler is running
- [ ] Dashboard is accessible
- [ ] Recent data has been collected (check latest timestamps)
- [ ] Prediction cycles are executing (check prediction_runs table)
- [ ] Discord notifications are working (check Discord channel)
- [ ] No errors in logs

---

## Troubleshooting Guide

### Common Issues

#### Issue: Screen sessions not persisting after logout

**Solution**: Use `screen -dmS` to create detached sessions, or use `tmux` as alternative.

#### Issue: Services stop after SSH disconnect

**Solution**: Ensure services are started in screen sessions, not directly in SSH session.

#### Issue: Database connection errors

**Solution**:
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Verify connection string
echo $DGAS_DATABASE_URL

# Test connection
psql $DGAS_DATABASE_URL -c "SELECT 1;"
```

#### Issue: API rate limiting

**Solution**:
- Check EODHD API subscription limits
- Adjust `requests_per_minute` in config
- Increase `delay_between_batches` if needed

#### Issue: Discord notifications not working

**Solution**: See [Discord Notification Setup](#discord-notification-setup) troubleshooting section.

### Log Locations

- **Data Collection**: `/var/log/dgas/data_collection.log` or `~/.dgas/logs/`
- **Prediction Scheduler**: `~/.dgas/logs/scheduler.log` or `/var/log/dgas/scheduler.log`
- **Dashboard**: Console output or `/var/log/dgas/dashboard.log`
- **Application Logs**: `~/.dgas/logs/`

### Recovery Procedures

**If data collection stops**:
```bash
# Restart in screen
screen -r dgas_data_collection
# Or if session doesn't exist:
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --daemon --config config/production.yaml
```

**If prediction scheduler stops**:
```bash
# Restart in screen
screen -r dgas_prediction_scheduler
# Or if session doesn't exist:
screen -S dgas_prediction_scheduler
cd /opt/DrummondGeometry-evals
source .env
uv run dgas scheduler start --daemon --config config/production.yaml
```

**If dashboard stops**:
```bash
# Restart in screen
screen -r dgas_dashboard
# Or if session doesn't exist:
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
```

---

## Maintenance Procedures

### Daily Maintenance

- **Morning Check** (9:00 AM ET):
  - Verify all services are running
  - Check overnight data collection
  - Review any errors in logs

- **Evening Check** (5:00 PM ET):
  - Review daily signal generation
  - Check data freshness
  - Verify Discord notifications

### Weekly Maintenance

- **Sunday Evening**:
  - Review weekly performance metrics
  - Check database size and growth
  - Review and archive logs
  - Verify backup procedures

### Monthly Maintenance

- **First Sunday of Month**:
  - Full system health review
  - Database optimization (VACUUM ANALYZE)
  - Review and update configuration if needed
  - Check for system updates

### Backup Procedures

**Database Backup**:
```bash
# Daily backup (add to crontab)
0 2 * * * pg_dump -h localhost -U fireworks_app dgas > /backup/dgas_$(date +\%Y\%m\%d).sql
```

**Configuration Backup**:
```bash
# Backup configuration files
tar -czf ~/dgas_config_backup_$(date +%Y%m%d).tar.gz \
  /opt/DrummondGeometry-evals/.env \
  /opt/DrummondGeometry-evals/config/production.yaml
```

---

## Appendix

### Screen Session Management

**List all screen sessions**:
```bash
screen -ls
```

**Attach to session**:
```bash
screen -r dgas_data_collection
screen -r dgas_prediction_scheduler
screen -r dgas_dashboard
```

**Detach from session**:
- Press `Ctrl+A`, then `D`

**Kill a screen session**:
```bash
screen -X -S dgas_data_collection quit
```

### Useful Commands Reference

```bash
# System status
uv run dgas status

# Data collection
uv run dgas data-collection status
uv run dgas data-collection stats
uv run dgas data-collection run-once

# Prediction scheduler
uv run dgas scheduler status
uv run dgas scheduler run-once

# Reports
uv run dgas report recent-signals --hours 24
uv run dgas monitor --summary

# Data verification
uv run python scripts/check_data_gaps.py
uv run python scripts/verify_data_freshness.py
```

### Configuration File Locations

- **Production Config**: `/opt/DrummondGeometry-evals/config/production.yaml`
- **Environment Variables**: `/opt/DrummondGeometry-evals/.env`
- **Log Directory**: `/var/log/dgas/`
- **Application Logs**: `~/.dgas/logs/`

---

**Document Version**: 1.0  
**Last Updated**: 2025-11-10  
**Next Review**: 2025-12-10
