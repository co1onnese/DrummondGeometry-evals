# DGAS Production Quick Reference

**Purpose**: Quick reference guide for running DGAS in production

---

## Pre-Flight Checklist

Before starting production, verify:

- [ ] PostgreSQL is running: `sudo systemctl status postgresql`
- [ ] Database connection works: `psql "$DGAS_DATABASE_URL" -c "SELECT 1;"`
- [ ] Environment variables set: `source .env && echo $EODHD_API_TOKEN | head -c 10`
- [ ] Historical data verified: `uv run python scripts/check_data_gaps.py --interval 30m`
- [ ] Discord bot configured: `echo $DGAS_DISCORD_BOT_TOKEN | head -c 10`
- [ ] Configuration validated: `uv run dgas configure validate --config config/production.yaml`

---

## Starting All Services

### Quick Start (Recommended)

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

### Manual Start

```bash
cd /opt/DrummondGeometry-evals
source .env

# 1. Data Collection
screen -S dgas_data_collection
uv run dgas data-collection start --config config/production.yaml
# Press Ctrl+A, then D

# 2. Prediction Scheduler
screen -S dgas_prediction_scheduler
uv run dgas scheduler start --daemon --config config/production.yaml
# Press Ctrl+A, then D

# 3. Dashboard
screen -S dgas_dashboard
uv run python run_dashboard.py
# Press Ctrl+A, then D
```

---

## Service Management

### Check Status

```bash
# All services
uv run dgas status

# Individual services
uv run dgas data-collection status
uv run dgas scheduler status
curl -I http://localhost:8501
```

### View Screen Sessions

```bash
# List all sessions
screen -ls

# Attach to session
screen -r dgas_data_collection
screen -r dgas_prediction_scheduler
screen -r dgas_dashboard

# Detach from session: Press Ctrl+A, then D
```

### Stop Services

```bash
# Data collection
uv run dgas data-collection stop

# Prediction scheduler
uv run dgas scheduler stop

# Dashboard
screen -X -S dgas_dashboard quit
```

---

## Verification Commands

### Data Collection

```bash
# Service status
uv run dgas data-collection status

# Recent statistics
uv run dgas data-collection stats

# Data freshness
uv run python scripts/verify_data_freshness.py

# Recent collection runs
psql "$DGAS_DATABASE_URL" -c "SELECT run_timestamp, symbols_updated, bars_stored FROM data_collection_runs ORDER BY run_timestamp DESC LIMIT 5;"
```

### Prediction Scheduler

```bash
# Service status
uv run dgas scheduler status

# Recent signals
uv run dgas report recent-signals --hours 24

# Recent prediction runs
psql "$DGAS_DATABASE_URL" -c "SELECT run_timestamp, symbols_processed, signals_generated FROM prediction_runs ORDER BY run_timestamp DESC LIMIT 5;"

# Manual test
uv run dgas scheduler run-once --config config/production.yaml
```

### Dashboard

```bash
# Check if running
curl -I http://localhost:8501

# Access dashboard
# Local: http://localhost:8501
# Remote: http://93.127.160.30:8501
```

---

## Monitoring

### Key Metrics

```bash
# System status
uv run dgas status

# Data collection stats
uv run dgas data-collection stats

# Recent signals
uv run dgas report recent-signals --hours 24

# Performance metrics
uv run dgas monitor --summary --hours 24
```

### Log Files

```bash
# Data collection
tail -f /var/log/dgas/data_collection.log

# Prediction scheduler
tail -f /var/log/dgas/scheduler.log

# Dashboard
tail -f /var/log/dgas/dashboard.log
```

### Database Queries

```bash
# Recent signals with Discord notifications
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    symbol,
    signal_type,
    confidence,
    notification_sent,
    signal_timestamp
FROM generated_signals
WHERE confidence >= 0.65
ORDER BY signal_timestamp DESC
LIMIT 10;
EOF

# Collection success rate
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    DATE(run_timestamp) as date,
    COUNT(*) as total_runs,
    SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful_runs
FROM data_collection_runs
WHERE run_timestamp > NOW() - INTERVAL '7 days'
GROUP BY DATE(run_timestamp)
ORDER BY date DESC;
EOF
```

---

## Troubleshooting

### Service Not Starting

```bash
# Check if already running
uv run dgas data-collection status
uv run dgas scheduler status

# Remove stale PID files
rm -f .dgas_data_collection.pid
rm -f .dgas_scheduler.pid

# Check logs
tail -50 /var/log/dgas/data_collection.log
tail -50 /var/log/dgas/scheduler.log
```

### No Data Being Collected

```bash
# Test API connection
uv run python scripts/test_eodhd_api_direct.py  # if exists

# Manual collection test
uv run dgas data-collection run-once --config config/production.yaml

# Check database
psql "$DGAS_DATABASE_URL" -c "SELECT COUNT(*) FROM market_data WHERE timestamp > NOW() - INTERVAL '1 hour';"
```

### No Signals Generated

```bash
# Check data freshness
uv run python scripts/verify_data_freshness.py

# Manual prediction test
uv run dgas predict AAPL MSFT --config config/production.yaml

# Check configuration
grep -A 10 "prediction:" config/production.yaml
```

### Discord Notifications Not Working

```bash
# Verify environment variables
grep -E "DGAS_DISCORD" .env

# Test Discord (if script exists)
uv run python scripts/test_discord_send.py

# Check logs
grep -i discord /var/log/dgas/scheduler.log | tail -20
```

### Dashboard Not Loading

```bash
# Check if running
ps aux | grep streamlit

# Check port
lsof -i :8501

# Restart dashboard
screen -X -S dgas_dashboard quit
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
```

---

## Historical Data Verification

### Quick Check

```bash
# Data gaps
uv run python scripts/check_data_gaps.py --interval 30m --target-date $(date +%Y-%m-%d)

# Data freshness
uv run python scripts/verify_data_freshness.py

# Symbol coverage
psql "$DGAS_DATABASE_URL" -c "SELECT COUNT(*) FROM market_symbols WHERE is_active = true;"
```

### Detailed Verification

```bash
# Check data coverage
psql "$DGAS_DATABASE_URL" << 'EOF'
SELECT 
    s.symbol,
    COUNT(md.timestamp) as bar_count,
    MAX(md.timestamp) as latest_bar
FROM market_symbols s
LEFT JOIN market_data md ON md.symbol_id = s.id AND md.interval_type = '30m'
WHERE s.is_active = true
GROUP BY s.symbol
ORDER BY latest_bar ASC
LIMIT 20;
EOF
```

---

## Configuration

### Key Settings

**File**: `config/production.yaml`

- `data_collection.enabled: true` - Enable data collection
- `data_collection.use_websocket: true` - Use WebSocket during market hours
- `notifications.discord.enabled: true` - Enable Discord notifications
- `scheduler.cron_expression: "*/15 * * * *"` - Run every 15 minutes
- `prediction.min_confidence: 0.65` - Only signals with 65%+ confidence

### Environment Variables

**File**: `.env`

- `EODHD_API_TOKEN` - EODHD API token
- `DGAS_DATABASE_URL` - PostgreSQL connection string
- `DGAS_DISCORD_BOT_TOKEN` - Discord bot token
- `DGAS_DISCORD_CHANNEL_ID` - Discord channel ID

---

## Recovery Procedures

### Restart All Services

```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
```

### Restart Individual Service

```bash
# Data collection
screen -r dgas_data_collection
# Or if session doesn't exist:
screen -S dgas_data_collection
cd /opt/DrummondGeometry-evals
source .env
uv run dgas data-collection start --config config/production.yaml

# Prediction scheduler
screen -r dgas_prediction_scheduler
# Or if session doesn't exist:
screen -S dgas_prediction_scheduler
cd /opt/DrummondGeometry-evals
source .env
uv run dgas scheduler start --daemon --config config/production.yaml

# Dashboard
screen -r dgas_dashboard
# Or if session doesn't exist:
screen -S dgas_dashboard
cd /opt/DrummondGeometry-evals
source .env
uv run python run_dashboard.py
```

---

## Daily Checklist

- [ ] All services running: `uv run dgas status`
- [ ] Data collection active: `uv run dgas data-collection status`
- [ ] Recent data collected: `uv run python scripts/verify_data_freshness.py`
- [ ] Signals generated: `uv run dgas report recent-signals --hours 24`
- [ ] Discord notifications working: Check Discord channel
- [ ] Dashboard accessible: `curl -I http://localhost:8501`
- [ ] No errors in logs: `grep -i error /var/log/dgas/*.log | tail -20`

---

## Support

For detailed information, see:
- **Full Production Plan**: `docs/PRODUCTION_RUN_STRATEGY.md`
- **Production Deployment Plan**: `docs/PRODUCTION_DEPLOYMENT_PLAN.md`
- **Production Run Plan**: `docs/PRODUCTION_RUN_PLAN.md`

---

**Last Updated**: 2025-01-27
