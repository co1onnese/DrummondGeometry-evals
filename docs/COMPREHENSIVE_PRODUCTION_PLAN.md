# DGAS Comprehensive Production Deployment Plan

**Version**: 2.0  
**Date**: 2025-11-16  
**Purpose**: Complete strategic plan for 24/7 production operation of DGAS with continuous data collection, signal generation, and Discord notifications

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Pre-Deployment Verification](#pre-deployment-verification)
3. [System Architecture](#system-architecture)
4. [Data Collection Service Strategy](#data-collection-service-strategy)
5. [Prediction Scheduler Strategy](#prediction-scheduler-strategy)
6. [Discord Notification Setup](#discord-notification-setup)
7. [Dashboard Deployment Strategy](#dashboard-deployment-strategy)
8. [Screen Session Management](#screen-session-management)
9. [Monitoring & Health Checks](#monitoring--health-checks)
10. [Historical Data Verification](#historical-data-verification)
11. [Startup Sequence](#startup-sequence)
12. [Ongoing Operations](#ongoing-operations)
13. [Troubleshooting Strategy](#troubleshooting-strategy)
14. [Recovery Procedures](#recovery-procedures)
15. [Maintenance Schedule](#maintenance-schedule)

---

## Executive Summary

### Production Goals

The DGAS system will operate 24/7 in production to:

1. **Continuously collect market data** for 517+ US stocks via EODHD API
2. **Generate trading signals** every 15 minutes with Drummond Geometry analysis
3. **Post Discord alerts** automatically when signals with confidence ≥ 65% are generated
4. **Serve a real-time dashboard** for monitoring and analysis
5. **Maintain data freshness** with automatic gap detection and backfilling

### Key Components

| Component | Purpose | Runtime | Screen Session |
|-----------|---------|---------|----------------|
| **Data Collection Service** | 24/7 market data ingestion | Continuous | `dgas_data_collection` |
| **Prediction Scheduler** | Automated signal generation | Every 15 min | `dgas_prediction_scheduler` |
| **Dashboard** | Web-based monitoring interface | Continuous | `dgas_dashboard` |
| **PostgreSQL Database** | Data persistence | Continuous | N/A (systemd) |

### Success Criteria

- ✅ All services running in persistent screen sessions
- ✅ Data collection running 24/7 with <1% failure rate
- ✅ Prediction scheduler executing every 15 minutes
- ✅ Discord notifications working for high-confidence signals
- ✅ Dashboard accessible and showing real-time data
- ✅ Historical data verified and complete

---

## Pre-Deployment Verification

### 1. Database Verification

**Objective**: Ensure PostgreSQL is running, accessible, and properly configured.

**Verification Steps**:

```bash
# 1. Check PostgreSQL service status
sudo systemctl status postgresql
# Expected: active (running)

# 2. Verify database connection from .env
cd /opt/DrummondGeometry-evals
source .env
psql "$DGAS_DATABASE_URL" -c "SELECT version();"
# Expected: PostgreSQL version information

# 3. Verify database schema and migrations
uv run python -m dgas.db.migrations
# Expected: "All migrations applied" or migration output

# 4. Check symbol count
psql "$DGAS_DATABASE_URL" -c "SELECT COUNT(*) FROM market_symbols WHERE is_active = true;"
# Expected: 517+ symbols

# 5. Verify connection pool configuration
psql "$DGAS_DATABASE_URL" -c "SHOW max_connections;"
# Expected: Sufficient connections (default 100, we use pool_size: 10)
```

**Checklist**:
- [ ] PostgreSQL service is running
- [ ] Database connection string in `.env` is correct
- [ ] Database user has proper permissions (SELECT, INSERT, UPDATE, DELETE)
- [ ] All migrations have been applied
- [ ] 517+ symbols registered in `market_symbols` table
- [ ] Connection pool size is appropriate (10 connections for 3 CPUs)

### 2. Historical Data Verification

**Objective**: Confirm all historical data has been backfilled correctly and is ready for production.

**Verification Steps**:

```bash
# 1. Check data coverage for all symbols
cd /opt/DrummondGeometry-evals
uv run python scripts/check_data_gaps.py --interval 30m --target-date $(date +%Y-%m-%d)

# 2. Verify data freshness (latest timestamps)
uv run python scripts/verify_data_freshness.py

# 3. Check specific symbol coverage
uv run dgas data quality-report --symbol AAPL --interval 30m

# 4. Verify data completeness for production symbols
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    s.symbol,
    COUNT(md.timestamp) as bar_count,
    MIN(md.timestamp) as earliest_bar,
    MAX(md.timestamp) as latest_bar,
    MAX(md.timestamp) > NOW() - INTERVAL '2 days' as recent_data
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true
GROUP BY s.symbol
HAVING COUNT(md.timestamp) > 0
ORDER BY latest_bar DESC
LIMIT 20;
EOF

# 5. Check for data gaps in critical timeframes
psql "$DGAS_DATABASE_URL" << 'EOF'
-- Check for symbols with no recent data (last 7 days)
SELECT 
    s.symbol,
    MAX(md.timestamp) as latest_timestamp,
    NOW() - MAX(md.timestamp) as age
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true
GROUP BY s.symbol
HAVING MAX(md.timestamp) < NOW() - INTERVAL '7 days' OR MAX(md.timestamp) IS NULL
ORDER BY age DESC;
EOF
```

**Expected Results**:
- All 517+ active symbols have historical data
- Latest timestamps are within 2 days of current date (for active trading days)
- No symbols show "no data" status
- Data quality metrics show >99% completeness
- No significant gaps in 30m interval data

**Checklist**:
- [ ] All active symbols have historical data
- [ ] Data is current up to most recent trading day
- [ ] No significant gaps in 30m interval data
- [ ] Data quality metrics are acceptable (>99% completeness)
- [ ] Latest timestamps are recent (within 2 days for active trading)

### 3. Environment Configuration Verification

**Objective**: Verify all required environment variables are set correctly.

**Verification Steps**:

```bash
# 1. Check .env file exists and is readable
cd /opt/DrummondGeometry-evals
ls -la .env
# Expected: File exists with proper permissions (600 recommended)

# 2. Verify critical variables (without exposing secrets)
grep -E "^[A-Z_]+=" .env | cut -d'=' -f1 | sort
# Expected: List of all environment variables

# 3. Test environment loading
source .env
echo "EODHD token set: $([ -n "$EODHD_API_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Database URL set: $([ -n "$DGAS_DATABASE_URL" ] && echo 'YES' || echo 'NO')"
echo "Data dir set: $([ -n "$DGAS_DATA_DIR" ] && echo 'YES' || echo 'NO')"
echo "Discord bot token set: $([ -n "$DGAS_DISCORD_BOT_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Discord channel ID set: $([ -n "$DGAS_DISCORD_CHANNEL_ID" ] && echo 'YES' || echo 'NO')"

# 4. Verify API token format (first 10 chars only)
echo "EODHD token preview: ${EODHD_API_TOKEN:0:10}..."
# Expected: Token starts with expected format

# 5. Test database connection with environment
python3 << 'EOF'
import os
from dotenv import load_dotenv
load_dotenv()
db_url = os.getenv('DGAS_DATABASE_URL')
if db_url:
    print(f"✓ Database URL configured: {db_url.split('@')[1] if '@' in db_url else 'configured'}")
else:
    print("✗ Database URL not configured")
EOF
```

**Required Environment Variables**:

| Variable | Purpose | Required | Example |
|----------|---------|----------|---------|
| `EODHD_API_TOKEN` | EODHD API authentication | ✅ Yes | `abc123...` |
| `DGAS_DATABASE_URL` | PostgreSQL connection string | ✅ Yes | `postgresql://user:pass@host:5432/dgas` |
| `DGAS_DATA_DIR` | Local data directory | ⚠️ Optional | `/opt/dgas/data` |
| `DGAS_DISCORD_BOT_TOKEN` | Discord bot token | ✅ Yes (for notifications) | `MTIzNDU2...` |
| `DGAS_DISCORD_CHANNEL_ID` | Discord channel ID | ✅ Yes (for notifications) | `123456789012345678` |

**Checklist**:
- [ ] `.env` file exists and is readable
- [ ] `EODHD_API_TOKEN` is set and valid
- [ ] `DGAS_DATABASE_URL` is set and correct
- [ ] `DGAS_DISCORD_BOT_TOKEN` is set (if using Discord)
- [ ] `DGAS_DISCORD_CHANNEL_ID` is set (if using Discord)
- [ ] All environment variables load correctly

### 4. Configuration File Verification

**Objective**: Verify production configuration file is correct and complete.

**Verification Steps**:

```bash
# 1. Check production config exists
ls -la /opt/DrummondGeometry-evals/config/production.yaml

# 2. Validate configuration
cd /opt/DrummondGeometry-evals
uv run dgas configure validate --config config/production.yaml
# Expected: Configuration is valid

# 3. Verify key configuration points
grep -A 2 "enabled:" config/production.yaml | head -20
# Expected: data_collection.enabled: true, notifications.discord.enabled: true

# 4. Check scheduler configuration
grep -A 5 "scheduler:" config/production.yaml
# Expected: cron_expression: "*/15 * * * *", market_hours_only: false

# 5. Check prediction thresholds
grep -A 3 "prediction:" config/production.yaml
# Expected: min_confidence: 0.65, min_signal_strength: 0.60
```

**Key Configuration Points**:

| Setting | Expected Value | Purpose |
|---------|----------------|---------|
| `data_collection.enabled` | `true` | Enable data collection service |
| `data_collection.use_websocket` | `true` | Use WebSocket during market hours |
| `notifications.discord.enabled` | `true` | Enable Discord notifications |
| `scheduler.cron_expression` | `"*/15 * * * *"` | Run every 15 minutes |
| `scheduler.market_hours_only` | `false` | Run 24/7 |
| `prediction.min_confidence` | `0.65` | Only signals with 65%+ confidence |
| `prediction.min_signal_strength` | `0.60` | Minimum signal strength |

**Checklist**:
- [ ] `config/production.yaml` exists and is valid
- [ ] Data collection is enabled
- [ ] WebSocket is enabled for market hours
- [ ] Discord notifications are enabled
- [ ] Scheduler runs every 15 minutes
- [ ] Minimum confidence threshold is 0.65
- [ ] Configuration validates without errors

---

## System Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Production Server                            │
│                                                                 │
│  ┌──────────────────────┐  ┌──────────────────────┐            │
│  │  Screen Session      │  │  Screen Session      │            │
│  │  Data Collection    │  │  Prediction          │            │
│  │  Service            │  │  Scheduler           │            │
│  │                     │  │                      │            │
│  │  • WebSocket (Mkt)  │  │  • Every 15 min     │            │
│  │  • REST API (Aft)   │  │  • 517+ symbols     │            │
│  │  • 24/7 operation   │  │  • Signal generation│            │
│  └──────────┬──────────┘  └──────────┬──────────┘            │
│             │                         │                        │
│             └─────────────┬───────────┘                        │
│                           │                                    │
│                  ┌─────────▼─────────┐                         │
│                  │  PostgreSQL DB     │                         │
│                  │  (Historical Data)│                         │
│                  └─────────┬─────────┘                         │
│                             │                                    │
│  ┌──────────────────────────▼──────────────────────┐          │
│  │     Screen Session: Dashboard                    │          │
│  │     Streamlit on port 8501                       │          │
│  │     • Real-time monitoring                       │          │
│  │     • Signal visualization                       │          │
│  │     • System status                              │          │
│  └──────────────────────────────────────────────────┘          │
│                                                                 │
│  ┌──────────────────────────────────────────────────┐          │
│  │  External Services                                │          │
│  │  • EODHD API (Market Data)                        │          │
│  │  • Discord API (Notifications)                   │          │
│  └──────────────────────────────────────────────────┘          │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow

1. **Data Collection Flow**:
   ```
   EODHD API → Data Collection Service → PostgreSQL
   ├─ Market Hours: WebSocket → Tick Aggregator → 30m bars
   └─ After Hours: REST API → 30m bars directly
   ```

2. **Signal Generation Flow**:
   ```
   PostgreSQL → Prediction Scheduler → Drummond Analysis → Signal Generator
   → Discord Notification (if confidence ≥ 65%)
   → Database (prediction_runs, generated_signals)
   ```

3. **Dashboard Flow**:
   ```
   PostgreSQL → Dashboard → Streamlit UI
   └─ Real-time updates via WebSocket (if configured)
   ```

---

## Data Collection Service Strategy

### Overview

The data collection service runs 24/7 to continuously gather market data for 517+ US stocks. It uses:
- **WebSocket** during market hours (9:30 AM - 4:00 PM ET, Mon-Fri) for real-time tick data
- **REST API** for after-hours and weekends
- **Dynamic intervals**: 30m during market hours, 30m after hours, 30m weekends

### Configuration Strategy

**File**: `config/production.yaml`

```yaml
data_collection:
  enabled: true
  use_websocket: true              # WebSocket during market hours
  websocket_interval: "30m"        # Aggregate ticks into 30m bars
  interval_market_hours: "30m"     # REST fallback interval
  interval_after_hours: "30m"     # After-hours interval
  interval_weekends: "30m"        # Weekend interval
  batch_size: 50                   # Symbols per batch
  max_concurrent_batches: 1        # Sequential (safer)
  requests_per_minute: 80          # EODHD API limit
  max_retries: 3                   # Retry failed symbols
  retry_delay_seconds: 5          # Exponential backoff
  error_threshold_pct: 10.0       # Alert if >10% fail
  log_collection_stats: true      # Detailed logging
  track_freshness: true           # Track data age
  health_check_interval: 60       # Health check every 60s
```

### Deployment Strategy

**Method**: Screen session for persistence across SSH disconnects

**Steps**:

```bash
# 1. Navigate to project directory
cd /opt/DrummondGeometry-evals

# 2. Load environment
source .env

# 3. Create screen session for data collection
screen -S dgas_data_collection

# 4. Start data collection service
uv run dgas data-collection start --config config/production.yaml

# 5. Detach from screen (Ctrl+A, then D)
# Service continues running in background
```

**Alternative**: Use startup script

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

### Verification Strategy

**Immediate Verification**:

```bash
# 1. Check service status
uv run dgas data-collection status
# Expected: Service is running

# 2. View recent statistics
uv run dgas data-collection stats --config config/production.yaml
# Expected: Shows collection cycles, symbols updated, bars fetched

# 3. Check screen session
screen -ls
# Expected: dgas_data_collection session exists

# 4. Attach to session to view output
screen -r dgas_data_collection
# Expected: See service logs and status
```

**Ongoing Verification**:

```bash
# 1. Check data freshness
uv run python scripts/verify_data_freshness.py
# Expected: Latest timestamps are recent

# 2. Monitor collection cycles
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    run_timestamp,
    interval_type,
    symbols_requested,
    symbols_updated,
    symbols_failed,
    bars_fetched,
    bars_stored,
    status,
    execution_time_ms
FROM data_collection_runs
ORDER BY run_timestamp DESC
LIMIT 10;
EOF

# 3. Check for collection errors
tail -f /var/log/dgas/data_collection.log | grep -i error
```

### Expected Behavior

- ✅ Service starts and connects to EODHD API
- ✅ During market hours: WebSocket connection established automatically
- ✅ After market hours: Switches to REST API polling
- ✅ Logs show collection cycles with success/failure counts
- ✅ Database receives new bars every 30 minutes (or configured interval)
- ✅ Failed symbols are retried with exponential backoff
- ✅ Health checks run every 60 seconds

### Troubleshooting Strategy

**Issue**: Service not starting
- Check if already running: `uv run dgas data-collection status`
- Check logs: `tail -50 /var/log/dgas/data_collection.log`
- Verify API token: `echo ${EODHD_API_TOKEN:0:10}...`
- Check database connection: `psql "$DGAS_DATABASE_URL" -c "SELECT 1;"`

**Issue**: No data being collected
- Test API connection: `uv run python scripts/test_eodhd_api_direct.py`
- Run manual collection: `uv run dgas data-collection run-once --config config/production.yaml`
- Check database: `psql "$DGAS_DATABASE_URL" -c "SELECT COUNT(*) FROM market_data WHERE timestamp > NOW() - INTERVAL '1 hour';"`

**Issue**: WebSocket not connecting
- Check if market is open (WebSocket only during market hours)
- Verify WebSocket configuration: `grep -A 5 "use_websocket" config/production.yaml`
- Check WebSocket status in logs: `grep -i websocket /var/log/dgas/data_collection.log`

---

## Prediction Scheduler Strategy

### Overview

The prediction scheduler runs every 15 minutes to:
1. Load latest market data from database
2. Calculate Drummond Geometry indicators (PLdot, envelopes, states, patterns)
3. Perform multi-timeframe analysis (HTF + Trading TF)
4. Generate trading signals with confidence scores
5. Filter signals (min confidence: 0.65, min signal strength: 0.60)
6. Send notifications to Discord for qualifying signals
7. Store results in database

### Configuration Strategy

**File**: `config/production.yaml`

```yaml
scheduler:
  cron_expression: "*/15 * * * *"  # Every 15 minutes
  timezone: America/New_York
  market_hours_only: false          # Run 24/7
  symbols: ["AAPL"]                  # Placeholder - loaded from DB
  htf_interval: "30m"                # Higher timeframe
  trading_interval: "30m"            # Trading timeframe

prediction:
  min_confidence: 0.65               # Only 65%+ confidence signals
  min_signal_strength: 0.60          # Minimum signal strength
  stop_loss_atr_multiplier: 1.5      # Risk management
  target_atr_multiplier: 2.5         # Reward target
  wait_for_fresh_data: true          # Coordinate with data collection
  max_wait_minutes: 5                # Max wait for fresh data
  freshness_threshold_minutes: 15     # Data age threshold
```

### Deployment Strategy

**Method**: Screen session with daemon mode

**Steps**:

```bash
# 1. Navigate to project directory
cd /opt/DrummondGeometry-evals

# 2. Load environment
source .env

# 3. Create screen session for prediction scheduler
screen -S dgas_prediction_scheduler

# 4. Start prediction scheduler
uv run dgas scheduler start --daemon --config config/production.yaml

# 5. Detach from screen (Ctrl+A, then D)
# Scheduler continues running in background
```

**Alternative**: Use startup script

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

### Verification Strategy

**Immediate Verification**:

```bash
# 1. Check scheduler status
uv run dgas scheduler status
# Expected: Scheduler is running

# 2. View scheduler state in database
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT * FROM scheduler_state ORDER BY updated_at DESC LIMIT 1;
EOF
# Expected: Shows scheduler is active

# 3. Check screen session
screen -ls
# Expected: dgas_prediction_scheduler session exists

# 4. Attach to session to view output
screen -r dgas_prediction_scheduler
# Expected: See scheduler logs and status
```

**Ongoing Verification**:

```bash
# 1. Check recent prediction runs
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    run_timestamp,
    status,
    symbols_processed,
    signals_generated,
    execution_time_ms,
    error_count
FROM prediction_runs
ORDER BY run_timestamp DESC
LIMIT 10;
EOF

# 2. Check recent signals
uv run dgas report recent-signals --hours 24
# Expected: Shows signals generated in last 24 hours

# 3. Monitor scheduler logs
tail -f /var/log/dgas/scheduler.log | grep -i "prediction\|signal\|error"

# 4. Run manual prediction cycle (test)
uv run dgas scheduler run-once --config config/production.yaml
# Expected: Executes one prediction cycle immediately
```

### Expected Behavior

- ✅ Scheduler starts and registers cron job (every 15 minutes)
- ✅ Every 15 minutes: Prediction cycle executes automatically
- ✅ Logs show symbols processed, signals generated
- ✅ Discord notifications sent for signals with confidence ≥ 65%
- ✅ Database records prediction runs and generated signals
- ✅ Scheduler coordinates with data collection (waits for fresh data if needed)

### Troubleshooting Strategy

**Issue**: Scheduler not running
- Check status: `uv run dgas scheduler status`
- Check PID file: `ls -la .dgas_scheduler.pid`
- Check logs: `tail -50 /var/log/dgas/scheduler.log`
- Verify screen session: `screen -r dgas_prediction_scheduler`

**Issue**: No signals generated
- Check if data is fresh: `uv run python scripts/verify_data_freshness.py`
- Run manual prediction: `uv run dgas predict AAPL MSFT --config config/production.yaml`
- Check prediction configuration: `grep -A 10 "prediction:" config/production.yaml`
- Check database for prediction runs: `psql "$DGAS_DATABASE_URL" -c "SELECT * FROM prediction_runs ORDER BY run_timestamp DESC LIMIT 5;"`

**Issue**: Discord notifications not working
- See [Discord Notification Setup](#discord-notification-setup) section

---

## Discord Notification Setup

### Overview

Discord notifications are sent automatically when trading signals with confidence ≥ 65% are generated. The system uses Discord Bot API (not webhooks) for richer formatting with embeds.

### Prerequisites

1. **Discord Bot Token**: Create a Discord bot and obtain the token
2. **Discord Channel ID**: Get the channel ID where notifications should be posted
3. **Bot Permissions**: Bot needs "Send Messages" permission in the channel

### Setup Steps

#### Step 1: Create Discord Application

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name it (e.g., "DGAS Trading Signals")
4. Click "Create"

#### Step 2: Create Bot

1. Go to "Bot" section in left sidebar
2. Click "Add Bot"
3. Click "Yes, do it!" to confirm
4. Under "Token", click "Reset Token" or "Copy" to get the bot token
5. **Save this token** - this is `DGAS_DISCORD_BOT_TOKEN`
6. Enable "Message Content Intent" (required for bot to read messages if needed)

#### Step 3: Get Channel ID

1. Enable Developer Mode in Discord:
   - User Settings → Advanced → Developer Mode (toggle ON)
2. Navigate to your Discord server
3. Right-click on the channel where you want notifications
4. Click "Copy ID"
5. **Save this ID** - this is `DGAS_DISCORD_CHANNEL_ID`

#### Step 4: Invite Bot to Server

1. Go to "OAuth2" → "URL Generator" in Discord Developer Portal
2. Under "Scopes", select:
   - `bot`
3. Under "Bot Permissions", select:
   - `Send Messages`
   - `Embed Links` (for rich embeds)
   - `Read Message History` (optional, for context)
4. Copy the generated URL at the bottom
5. Open the URL in your browser
6. Select your Discord server
7. Click "Authorize"
8. Complete any CAPTCHA if prompted

#### Step 5: Configure Environment Variables

Add to `.env` file:

```bash
# Discord Bot Configuration
DGAS_DISCORD_BOT_TOKEN=your_bot_token_here
DGAS_DISCORD_CHANNEL_ID=your_channel_id_here
```

**Security Note**: Never commit `.env` file to version control. It's already in `.gitignore`.

#### Step 6: Verify Configuration

```bash
# 1. Check environment variables are set
cd /opt/DrummondGeometry-evals
source .env
echo "Bot token set: $([ -n "$DGAS_DISCORD_BOT_TOKEN" ] && echo 'YES' || echo 'NO')"
echo "Channel ID set: $([ -n "$DGAS_DISCORD_CHANNEL_ID" ] && echo 'YES' || echo 'NO')"

# 2. Test Discord connection (if test script exists)
uv run python scripts/test_discord_send.py
# Expected: Test message sent to Discord channel

# 3. Verify notification configuration
grep -A 5 "notifications:" config/production.yaml
# Expected: discord.enabled: true
```

### Notification Format

When a signal with confidence ≥ 65% is generated, Discord will receive an embed with:

- **Symbol**: Stock ticker (e.g., AAPL)
- **Signal Type**: LONG, SHORT, EXIT_LONG, or EXIT_SHORT
- **Entry Price**: Recommended entry price
- **Stop Loss**: Stop loss price
- **Target Price**: Take profit target
- **Confidence**: Confidence score (0-1)
- **Signal Strength**: Signal strength score (0-1)
- **Risk/Reward Ratio**: Calculated risk/reward
- **Timestamp**: When signal was generated

### Verification Strategy

**Test Notifications**:

```bash
# 1. Generate a test signal (if possible)
uv run dgas predict AAPL --config config/production.yaml
# Check Discord channel for notification

# 2. Check notification logs
grep -i discord /var/log/dgas/scheduler.log | tail -20
# Expected: Shows Discord notification attempts and results

# 3. Verify signals in database
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    symbol,
    signal_type,
    confidence,
    signal_strength,
    notification_sent,
    notification_sent_at
FROM generated_signals
WHERE confidence >= 0.65
ORDER BY signal_timestamp DESC
LIMIT 10;
EOF
# Expected: notification_sent = true for recent signals
```

### Troubleshooting Strategy

**Issue**: Notifications not being sent
- Verify environment variables: `grep -E "DGAS_DISCORD" .env`
- Check notification configuration: `grep -A 5 "notifications:" config/production.yaml`
- Test Discord API: `uv run python scripts/test_discord_send.py`
- Check logs: `grep -i discord /var/log/dgas/scheduler.log`

**Issue**: "401 Unauthorized" error
- Bot token is invalid or expired
- Regenerate token in Discord Developer Portal
- Update `DGAS_DISCORD_BOT_TOKEN` in `.env`
- Restart prediction scheduler

**Issue**: "403 Forbidden" error
- Bot doesn't have permission to send messages
- Re-invite bot with "Send Messages" permission
- Verify bot is in the correct channel

**Issue**: "404 Not Found" error
- Channel ID is incorrect
- Verify channel ID by right-clicking channel → Copy ID
- Update `DGAS_DISCORD_CHANNEL_ID` in `.env`
- Restart prediction scheduler

---

## Dashboard Deployment Strategy

### Overview

The dashboard provides a web-based interface for:
- Viewing recent signals and predictions
- Monitoring system status
- Analyzing market data
- Real-time updates via WebSocket (if configured)

### Deployment Strategy

**Method**: Screen session for persistence

**Steps**:

```bash
# 1. Navigate to project directory
cd /opt/DrummondGeometry-evals

# 2. Load environment
source .env

# 3. Verify dashboard dependencies
uv run python -c "import streamlit; import plotly"
# Expected: No errors

# 4. Install dashboard dependencies if needed
uv sync --extra dashboard

# 5. Create screen session for dashboard
screen -S dgas_dashboard

# 6. Start dashboard
uv run python run_dashboard.py
# Or directly:
# uv run streamlit run src/dgas/dashboard/app.py --server.port=8501 --server.address=0.0.0.0

# 7. Detach from screen (Ctrl+A, then D)
# Dashboard continues running in background
```

**Alternative**: Use startup script

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

### Access Points

- **Local**: http://localhost:8501
- **Remote**: http://93.127.160.30:8501 (if firewall allows)

### Verification Strategy

**Immediate Verification**:

```bash
# 1. Check if dashboard is running
ps aux | grep streamlit
# Expected: streamlit process running

# 2. Check port
netstat -tuln | grep 8501
# Expected: Port 8501 is listening

# 3. Test HTTP response
curl -I http://localhost:8501
# Expected: HTTP/1.1 200 OK

# 4. Check screen session
screen -ls
# Expected: dgas_dashboard session exists

# 5. Attach to session to view output
screen -r dgas_dashboard
# Expected: See Streamlit logs and status
```

**Functional Verification**:

1. Open dashboard in browser: http://localhost:8501
2. Navigate to "Overview" page
3. Verify recent signals are visible
4. Navigate to "System Status" page
5. Verify all components show green/healthy status
6. Navigate to "Predictions" page
7. Verify prediction data loads correctly

### Expected Behavior

- ✅ Dashboard starts and binds to port 8501
- ✅ Web interface loads with navigation menu
- ✅ Pages show data from database
- ✅ Real-time updates via WebSocket (if configured)
- ✅ No errors in console/logs

### Troubleshooting Strategy

**Issue**: Dashboard not loading
- Check if port is in use: `lsof -i :8501`
- Check Streamlit installation: `uv run streamlit --version`
- Check logs: `tail -50 /var/log/dgas/dashboard.log`
- Verify screen session: `screen -r dgas_dashboard`

**Issue**: No data showing
- Verify database connection: `uv run dgas status --check-database`
- Check if data exists: `uv run dgas data quality-report --symbol AAPL`
- Check database queries in logs: `grep -i "error\|exception" /var/log/dgas/dashboard.log`

**Issue**: Dashboard dependencies missing
- Install dependencies: `uv sync --extra dashboard`
- Verify installation: `uv run python -c "import streamlit; import plotly"`

---

## Screen Session Management

### Overview

All services run in screen sessions for persistence across SSH disconnects and system reboots (if screen sessions are configured to persist).

### Screen Session Names

| Service | Screen Session Name | Purpose |
|--------|-------------------|---------|
| Data Collection | `dgas_data_collection` | 24/7 data collection |
| Prediction Scheduler | `dgas_prediction_scheduler` | Signal generation |
| Dashboard | `dgas_dashboard` | Web interface |

### Management Commands

**List all screen sessions**:

```bash
screen -ls
# Expected: Shows all active screen sessions
```

**Attach to session**:

```bash
screen -r dgas_data_collection      # Data collection service
screen -r dgas_prediction_scheduler # Prediction scheduler
screen -r dgas_dashboard            # Dashboard
```

**Detach from session**:
- Press `Ctrl+A`, then `D`

**Kill a screen session**:

```bash
screen -X -S dgas_data_collection quit
screen -X -S dgas_prediction_scheduler quit
screen -X -S dgas_dashboard quit
```

**Create detached session** (for startup scripts):

```bash
screen -dmS dgas_data_collection bash -c "cd /opt/DrummondGeometry-evals && source .env && exec uv run dgas data-collection start --config config/production.yaml"
```

### Screen Configuration (Optional)

Create `~/.screenrc` for better screen experience:

```bash
cat > ~/.screenrc << 'EOF'
# Screen configuration for DGAS
startup_message off
defscrollback 10000
hardstatus alwayslastline
hardstatus string '%{= kG}[ %{G}%H %{g}][%= %{= kw}%?%-Lw%?%{r}(%{W}%n*%f%t%?(%u)%?%{r})%{w}%?%+Lw%?%?%= %{g}][%{B} %m-%d %{W}%c %{g}]'
EOF
```

---

## Monitoring & Health Checks

### System Health Monitoring

**Daily Health Check Script**:

Create `/opt/DrummondGeometry-evals/scripts/daily_health_check.sh`:

```bash
#!/bin/bash
# DGAS Daily Health Check Script

LOG_FILE="/var/log/dgas/health_check.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')
PROJECT_DIR="/opt/DrummondGeometry-evals"

cd "$PROJECT_DIR"
source .env

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

# Check database
if psql "$DGAS_DATABASE_URL" -c "SELECT 1;" > /dev/null 2>&1; then
    echo "[$DATE] ✓ Database: ACCESSIBLE" >> "$LOG_FILE"
else
    echo "[$DATE] ✗ Database: INACCESSIBLE" >> "$LOG_FILE"
fi

echo "[$DATE] Health check completed" >> "$LOG_FILE"
```

**Make executable**:

```bash
chmod +x /opt/DrummondGeometry-evals/scripts/daily_health_check.sh
```

**Set up cron job** (runs every hour):

```bash
(crontab -l 2>/dev/null; echo "0 * * * * /opt/DrummondGeometry-evals/scripts/daily_health_check.sh") | crontab -
```

### Key Metrics to Monitor

#### 1. Data Collection Metrics

```bash
# Collection cycle success rate
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    DATE(run_timestamp) as date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful_runs,
    ROUND(100.0 * SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate_pct
FROM data_collection_runs
WHERE run_timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE(run_timestamp)
ORDER BY date DESC;
EOF

# Data freshness
uv run python scripts/verify_data_freshness.py

# Symbols updated per cycle
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    run_timestamp,
    symbols_requested,
    symbols_updated,
    symbols_failed,
    ROUND(100.0 * symbols_updated / NULLIF(symbols_requested, 0), 2) as success_rate_pct
FROM data_collection_runs
ORDER BY run_timestamp DESC
LIMIT 10;
EOF
```

#### 2. Prediction Scheduler Metrics

```bash
# Prediction cycle execution time
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    run_timestamp,
    status,
    symbols_processed,
    signals_generated,
    execution_time_ms,
    ROUND(execution_time_ms / 1000.0, 2) as execution_time_seconds
FROM prediction_runs
ORDER BY run_timestamp DESC
LIMIT 10;
EOF

# Signals generated per cycle
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    DATE(signal_timestamp) as date,
    COUNT(*) as total_signals,
    SUM(CASE WHEN confidence >= 0.65 THEN 1 ELSE 0 END) as high_confidence_signals,
    AVG(confidence) as avg_confidence
FROM generated_signals
WHERE signal_timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE(signal_timestamp)
ORDER BY date DESC;
EOF

# Discord notification success rate
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    DATE(signal_timestamp) as date,
    COUNT(*) as total_signals,
    SUM(CASE WHEN notification_sent = true THEN 1 ELSE 0 END) as notifications_sent,
    ROUND(100.0 * SUM(CASE WHEN notification_sent = true THEN 1 ELSE 0 END) / COUNT(*), 2) as notification_rate_pct
FROM generated_signals
WHERE signal_timestamp > NOW() - INTERVAL '7 days'
  AND confidence >= 0.65
GROUP BY DATE(signal_timestamp)
ORDER BY date DESC;
EOF
```

#### 3. Database Metrics

```bash
# Database size
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    pg_size_pretty(pg_database_size('dgas')) as database_size;
EOF

# Table sizes
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) AS size
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC
LIMIT 10;
EOF

# Connection pool usage (if monitoring available)
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT count(*) as active_connections 
FROM pg_stat_activity 
WHERE datname = 'dgas' AND state = 'active';
EOF
```

#### 4. System Resource Metrics

```bash
# CPU and memory usage
top -bn1 | grep -E "Cpu|Mem"

# Disk space
df -h /opt/DrummondGeometry-evals

# Process status
ps aux | grep -E "dgas|streamlit" | grep -v grep
```

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

## Historical Data Verification

### Verification Strategy

**Objective**: Ensure all historical data is complete and ready for production signal generation.

### Step 1: Symbol Coverage Verification

```bash
# Check all active symbols have data
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    COUNT(DISTINCT s.id) as total_symbols,
    COUNT(DISTINCT md.symbol_id) as symbols_with_data,
    COUNT(DISTINCT s.id) - COUNT(DISTINCT md.symbol_id) as symbols_without_data
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true;
EOF
# Expected: symbols_without_data = 0
```

### Step 2: Data Completeness Verification

```bash
# Check data coverage for each symbol
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    s.symbol,
    COUNT(md.timestamp) as bar_count,
    MIN(md.timestamp) as earliest_bar,
    MAX(md.timestamp) as latest_bar,
    CASE 
        WHEN MAX(md.timestamp) > NOW() - INTERVAL '2 days' THEN 'RECENT'
        WHEN MAX(md.timestamp) > NOW() - INTERVAL '7 days' THEN 'STALE'
        ELSE 'VERY_STALE'
    END as freshness_status
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true
GROUP BY s.symbol
HAVING COUNT(md.timestamp) > 0
ORDER BY latest_bar ASC
LIMIT 20;
EOF
# Expected: Most symbols show 'RECENT' status
```

### Step 3: Data Gap Detection

```bash
# Run gap detection script
cd /opt/DrummondGeometry-evals
uv run python scripts/check_data_gaps.py --interval 30m --target-date $(date +%Y-%m-%d)
# Expected: No significant gaps reported
```

### Step 4: Data Quality Verification

```bash
# Check data quality for sample symbols
for symbol in AAPL MSFT GOOGL AMZN TSLA; do
    echo "Checking $symbol..."
    uv run dgas data quality-report --symbol "$symbol" --interval 30m
done
# Expected: All symbols show good quality metrics
```

### Step 5: Multi-Timeframe Readiness

```bash
# Verify we have sufficient data for multi-timeframe analysis
psql "$DGAS_DATABASE_URL" << 'EOF'
-- Check if we have enough bars for HTF analysis (need at least 100 bars)
SELECT 
    s.symbol,
    COUNT(md.timestamp) as bar_count,
    CASE 
        WHEN COUNT(md.timestamp) >= 100 THEN 'SUFFICIENT'
        ELSE 'INSUFFICIENT'
    END as readiness
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true
GROUP BY s.symbol
HAVING COUNT(md.timestamp) < 100
ORDER BY bar_count DESC
LIMIT 20;
EOF
# Expected: All symbols have sufficient data (100+ bars)
```

### Verification Checklist

- [ ] All 517+ active symbols have historical data
- [ ] Latest timestamps are within 2 days of current date (for active trading)
- [ ] No significant gaps in 30m interval data
- [ ] Data quality metrics show >99% completeness
- [ ] All symbols have sufficient data for multi-timeframe analysis (100+ bars)
- [ ] Data is ready for production signal generation

---

## Startup Sequence

### Complete Production Startup Procedure

**Step-by-step sequence**:

```bash
# 1. Navigate to project directory
cd /opt/DrummondGeometry-evals

# 2. Load environment
source .env

# 3. Verify database is running
sudo systemctl status postgresql
# If not running: sudo systemctl start postgresql

# 4. Verify database connection
psql "$DGAS_DATABASE_URL" -c "SELECT 1;"
# Expected: Returns 1

# 5. Start data collection service (in screen)
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --config config/production.yaml
# Press Ctrl+A, then D to detach

# 6. Start prediction scheduler (in screen)
screen -S dgas_prediction_scheduler
cd /opt/DrummondGeometry-evals
source .env
uv run dgas scheduler start --daemon --config config/production.yaml
# Press Ctrl+A, then D to detach

# 7. Start dashboard (in screen)
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
# Press Ctrl+A, then D to detach

# 8. Verify all services
uv run dgas status
uv run dgas data-collection status
uv run dgas scheduler status
curl -I http://localhost:8501
```

### Quick Startup Script

Use the provided startup script:

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

This script:
- Checks if services are already running
- Starts all services in screen sessions
- Verifies services are running
- Provides management commands

### Post-Startup Verification

```bash
# 1. Check all screen sessions
screen -ls
# Expected: Three sessions (data_collection, prediction_scheduler, dashboard)

# 2. Check service statuses
uv run dgas status
# Expected: All services show as running

# 3. Check data collection
uv run dgas data-collection status
# Expected: Service is running

# 4. Check prediction scheduler
uv run dgas scheduler status
# Expected: Scheduler is running

# 5. Check dashboard
curl -I http://localhost:8501
# Expected: HTTP/1.1 200 OK

# 6. Monitor logs
tail -f /var/log/dgas/data_collection.log
tail -f /var/log/dgas/scheduler.log
tail -f /var/log/dgas/dashboard.log
```

---

## Ongoing Operations

### Daily Operations Checklist

**Morning (9:00 AM ET)**:

- [ ] Check system status: `uv run dgas status`
- [ ] Review overnight data collection: `uv run dgas data-collection stats`
- [ ] Check recent signals: `uv run dgas report recent-signals --hours 24`
- [ ] Verify data freshness: `uv run python scripts/verify_data_freshness.py`
- [ ] Review any errors in logs: `grep -i error /var/log/dgas/*.log | tail -20`

**Midday (1:00 PM ET)**:

- [ ] Monitor prediction cycle execution
- [ ] Check Discord notifications are working
- [ ] Review database performance metrics

**Evening (5:00 PM ET)**:

- [ ] Review daily summary: `uv run dgas report recent-signals --hours 24`
- [ ] Check scheduler status: `uv run dgas scheduler status`
- [ ] Verify next-day scheduling is correct

### Weekly Operations

**Sunday Evening**:

- [ ] Review weekly performance metrics
- [ ] Check database size and growth
- [ ] Review and archive logs
- [ ] Verify backup procedures
- [ ] Check for system updates

### Monthly Operations

**First Sunday of Month**:

- [ ] Full system health review
- [ ] Database optimization (VACUUM ANALYZE)
- [ ] Review and update configuration if needed
- [ ] Check for system updates
- [ ] Review signal accuracy and calibration

---

## Troubleshooting Strategy

### Common Issues and Solutions

#### Issue 1: Service Not Starting

**Symptoms**:
- Service status shows "STOPPED"
- No process found
- PID file exists but process is dead

**Diagnosis**:
```bash
# Check service status
uv run dgas data-collection status
uv run dgas scheduler status

# Check for stale PID files
ls -la .dgas_*.pid

# Check logs
tail -50 /var/log/dgas/data_collection.log
tail -50 /var/log/dgas/scheduler.log
```

**Solution**:
```bash
# Remove stale PID files
rm -f .dgas_data_collection.pid
rm -f .dgas_scheduler.pid

# Restart service in screen
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --config config/production.yaml
```

#### Issue 2: No Data Being Collected

**Symptoms**:
- Collection cycles show 0 symbols updated
- No new bars in database
- Collection status shows FAILED

**Diagnosis**:
```bash
# Check API connection
uv run python scripts/test_eodhd_api_direct.py

# Check database connection
psql "$DGAS_DATABASE_URL" -c "SELECT 1;"

# Check recent collection runs
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT * FROM data_collection_runs ORDER BY run_timestamp DESC LIMIT 5;
EOF
```

**Solution**:
```bash
# Test manual collection
uv run dgas data-collection run-once --config config/production.yaml

# Verify API token
echo ${EODHD_API_TOKEN:0:10}...

# Check rate limiting
grep -i "rate limit" /var/log/dgas/data_collection.log
```

#### Issue 3: No Signals Generated

**Symptoms**:
- Prediction runs show 0 signals generated
- No signals in database
- Discord notifications not received

**Diagnosis**:
```bash
# Check data freshness
uv run python scripts/verify_data_freshness.py

# Run manual prediction
uv run dgas predict AAPL MSFT --config config/production.yaml

# Check prediction configuration
grep -A 10 "prediction:" config/production.yaml

# Check recent prediction runs
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT * FROM prediction_runs ORDER BY run_timestamp DESC LIMIT 5;
EOF
```

**Solution**:
```bash
# Verify data is fresh
uv run python scripts/verify_data_freshness.py

# Check confidence thresholds
grep "min_confidence" config/production.yaml

# Test with lower threshold temporarily
# (Edit config, test, then revert)
```

#### Issue 4: Discord Notifications Not Working

**Symptoms**:
- Signals generated but no Discord messages
- Notification logs show errors
- Discord API errors in logs

**Diagnosis**:
```bash
# Check environment variables
grep -E "DGAS_DISCORD" .env

# Test Discord connection
uv run python scripts/test_discord_send.py

# Check notification logs
grep -i discord /var/log/dgas/scheduler.log | tail -20
```

**Solution**:
```bash
# Verify bot token and channel ID
echo "Bot token: ${DGAS_DISCORD_BOT_TOKEN:0:10}..."
echo "Channel ID: $DGAS_DISCORD_CHANNEL_ID"

# Test Discord API
uv run python scripts/test_discord_send.py

# Restart scheduler to pick up new config
uv run dgas scheduler stop
screen -S dgas_prediction_scheduler
uv run dgas scheduler start --daemon --config config/production.yaml
```

#### Issue 5: Dashboard Not Loading

**Symptoms**:
- Browser shows "This site can't be reached"
- Streamlit error in console
- Port 8501 not accessible

**Diagnosis**:
```bash
# Check if dashboard is running
ps aux | grep streamlit

# Check port
netstat -tuln | grep 8501
lsof -i :8501

# Check logs
tail -50 /var/log/dgas/dashboard.log
```

**Solution**:
```bash
# Restart dashboard
screen -X -S dgas_dashboard quit
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
```

---

## Recovery Procedures

### Service Recovery

**If data collection stops**:

```bash
# 1. Check status
uv run dgas data-collection status

# 2. Restart in screen
screen -r dgas_data_collection
# Or if session doesn't exist:
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --config config/production.yaml
```

**If prediction scheduler stops**:

```bash
# 1. Check status
uv run dgas scheduler status

# 2. Restart in screen
screen -r dgas_prediction_scheduler
# Or if session doesn't exist:
screen -S dgas_prediction_scheduler
cd /opt/DrummondGeometry-evals
source .env
uv run dgas scheduler start --daemon --config config/production.yaml
```

**If dashboard stops**:

```bash
# 1. Check if running
ps aux | grep streamlit

# 2. Restart in screen
screen -r dgas_dashboard
# Or if session doesn't exist:
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
```

### Complete System Recovery

**If all services stop**:

```bash
# 1. Stop all services (cleanup)
uv run dgas data-collection stop
uv run dgas scheduler stop
screen -X -S dgas_dashboard quit

# 2. Verify database is running
sudo systemctl status postgresql

# 3. Restart all services
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh

# 4. Verify all services
uv run dgas status
```

### Data Recovery

**If data collection fails for extended period**:

```bash
# 1. Check data gaps
uv run python scripts/check_data_gaps.py --interval 30m --target-date $(date +%Y-%m-%d)

# 2. Backfill missing data
uv run python scripts/backfill_to_latest.py

# 3. Verify data is complete
uv run python scripts/verify_data_freshness.py
```

---

## Maintenance Schedule

### Daily Maintenance (Automated)

- **2:00 AM**: Database backup (if configured)
- **3:00 AM**: Log rotation (if configured)
- **4:00 AM**: Cache cleanup (if configured)

### Weekly Maintenance (Manual - Sunday)

1. **Review Performance**
   - Generate weekly report
   - Analyze trends
   - Identify issues

2. **Check Database**
   - Run VACUUM ANALYZE
   - Check index usage
   - Review table sizes

3. **Review Logs**
   - Archive old logs
   - Search for recurring errors
   - Clean up temporary files

**Commands**:
```bash
# Weekly maintenance
psql "$DGAS_DATABASE_URL" -c "VACUUM ANALYZE;"
uv run dgas report recent-signals --hours 168 --output reports/weekly_$(date +%Y%m%d).md
```

### Monthly Maintenance (Manual - First Sunday)

1. **Database Maintenance**
   - Full VACUUM
   - Reindex if needed
   - Update statistics

2. **Performance Review**
   - Analyze monthly trends
   - Compare to SLAs
   - Plan optimizations

3. **Configuration Review**
   - Check for outdated settings
   - Review thresholds
   - Update if needed

**Commands**:
```bash
# Monthly maintenance
psql "$DGAS_DATABASE_URL" -c "VACUUM FULL ANALYZE;"
psql "$DGAS_DATABASE_URL" -c "REINDEX DATABASE dgas;"
```

---

## Conclusion

This comprehensive production plan provides a complete strategy for deploying and operating DGAS in a 24/7 production environment. Key success factors:

1. **Thorough Pre-Deployment Verification**: Ensure all prerequisites are met
2. **Proper Service Management**: Use screen sessions for persistence
3. **Continuous Monitoring**: Track key metrics and health indicators
4. **Effective Troubleshooting**: Quick diagnosis and resolution of issues
5. **Regular Maintenance**: Keep system optimized and up-to-date

### Next Steps

1. Complete pre-deployment verification checklist
2. Set up Discord bot and configure notifications
3. Start all services using startup script
4. Verify all services are running correctly
5. Monitor for first 24 hours
6. Review and adjust configuration as needed

### Success Criteria

- ✅ All services running in screen sessions
- ✅ Data collection running 24/7
- ✅ Prediction scheduler executing every 15 minutes
- ✅ Discord notifications working
- ✅ Dashboard accessible
- ✅ Historical data verified and complete

---

**Document Version**: 2.0  
**Last Updated**: 2025-11-16  
**Next Review**: 2025-12-16
