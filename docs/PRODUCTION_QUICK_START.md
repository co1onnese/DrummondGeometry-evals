# DGAS Production Quick Start Guide

**Quick reference for deploying DGAS in production**

---

## Pre-Flight Checklist

Before starting, verify:

- [ ] PostgreSQL is running and accessible
- [ ] `.env` file exists with all required variables
- [ ] Historical data has been backfilled
- [ ] Discord bot token and channel ID are configured
- [ ] `config/production.yaml` is correct

---

## Quick Start Commands

### 1. Start All Services

```bash
cd /opt/DrummondGeometry-evals
source .env

# Start data collection (in screen)
screen -S dgas_data_collection
uv run dgas data-collection start --daemon --config config/production.yaml
# Press Ctrl+A, then D to detach

# Start prediction scheduler (in screen)
screen -S dgas_prediction_scheduler
uv run dgas scheduler start --daemon --config config/production.yaml
# Press Ctrl+A, then D to detach

# Start dashboard (in screen)
screen -S dgas_dashboard
uv run python run_dashboard.py
# Press Ctrl+A, then D to detach
```

### 2. Verify Services

```bash
# Check all services
uv run dgas status
uv run dgas data-collection status
uv run dgas scheduler status
curl -I http://localhost:8501
```

### 3. Monitor Services

```bash
# View screen sessions
screen -ls

# Attach to sessions
screen -r dgas_data_collection
screen -r dgas_prediction_scheduler
screen -r dgas_dashboard

# View logs
tail -f /var/log/dgas/data_collection.log
tail -f ~/.dgas/logs/scheduler.log
```

---

## Required Environment Variables

In `.env` file:

```bash
EODHD_API_TOKEN=your_token_here
DGAS_DATABASE_URL=postgresql://user:pass@localhost:5432/dgas
DGAS_DATA_DIR=/path/to/data
DGAS_DISCORD_BOT_TOKEN=your_bot_token
DGAS_DISCORD_CHANNEL_ID=your_channel_id
```

---

## Key Configuration Points

In `config/production.yaml`:

- `data_collection.enabled: true`
- `data_collection.use_websocket: true`
- `notifications.discord.enabled: true`
- `scheduler.cron_expression: "*/15 * * * *"`
- `prediction.min_confidence: 0.65`

---

## Service Management

### Stop Services

```bash
# Stop data collection
uv run dgas data-collection stop

# Stop prediction scheduler
uv run dgas scheduler stop

# Stop dashboard
screen -X -S dgas_dashboard quit
# Or: pkill -f streamlit
```

### Restart Services

```bash
# Restart data collection
uv run dgas data-collection stop
screen -S dgas_data_collection
uv run dgas data-collection start --daemon --config config/production.yaml

# Restart prediction scheduler
uv run dgas scheduler stop
screen -S dgas_prediction_scheduler
uv run dgas scheduler start --daemon --config config/production.yaml
```

---

## Verification Commands

```bash
# Check data collection
uv run dgas data-collection stats

# Check recent signals
uv run dgas report recent-signals --hours 24

# Check data freshness
uv run python scripts/verify_data_freshness.py

# Check system health
uv run dgas status
uv run dgas monitor --summary
```

---

## Troubleshooting

### Service Not Starting

```bash
# Check if already running
uv run dgas data-collection status
uv run dgas scheduler status

# Check logs
tail -50 /var/log/dgas/data_collection.log
tail -50 ~/.dgas/logs/scheduler.log

# Verify environment
source .env
echo $EODHD_API_TOKEN | head -c 10
```

### No Data Being Collected

```bash
# Test API connection
uv run python scripts/test_eodhd_api_direct.py

# Run manual collection
uv run dgas data-collection run-once --config config/production.yaml

# Check database
psql $DGAS_DATABASE_URL -c "SELECT COUNT(*) FROM market_data;"
```

### Discord Notifications Not Working

```bash
# Verify environment variables
grep -E "DGAS_DISCORD" .env

# Test Discord
uv run python scripts/test_discord_send.py

# Check configuration
grep -A 5 "notifications:" config/production.yaml
```

---

## Access Points

- **Dashboard**: http://localhost:8501 (or http://93.127.160.30:8501)
- **Database**: `psql $DGAS_DATABASE_URL`
- **Logs**: `/var/log/dgas/` and `~/.dgas/logs/`

---

## Daily Checklist

- [ ] All services running (`uv run dgas status`)
- [ ] Data collection active (`uv run dgas data-collection status`)
- [ ] Prediction scheduler active (`uv run dgas scheduler status`)
- [ ] Dashboard accessible (`curl -I http://localhost:8501`)
- [ ] Recent data collected (check latest timestamps)
- [ ] Signals being generated (check `prediction_runs` table)
- [ ] Discord notifications working (check Discord channel)

---

For detailed information, see [PRODUCTION_DEPLOYMENT_PLAN.md](./PRODUCTION_DEPLOYMENT_PLAN.md)
