# Data Collection Service Troubleshooting Guide

## Problem: Data Collection Service Not Collecting Data

### Symptoms
- Service appears to be running (screen session exists, PID file present)
- No recent data collection runs in database, or runs are failing
- Logs show "maximum number of running instances reached (1)"
- Data is stale (>60 minutes old)

### Root Cause Analysis

The most common issue is a **stuck collection cycle** that prevents subsequent cycles from running. This happens when:

1. The initial collection cycle (started on service startup) hangs and never completes
2. The execution lock is held indefinitely
3. Subsequent cycles are blocked because `max_instances=1` prevents overlapping executions

### Diagnosis Steps

1. **Run the diagnostic script:**
   ```bash
   uv run python scripts/diagnose_data_collection.py
   ```

2. **Check screen session logs:**
   ```bash
   screen -S data-collection -X hardcopy /tmp/dc_log.txt
   tail -100 /tmp/dc_log.txt
   ```

3. **Check startup log:**
   ```bash
   cat /tmp/data_collection_startup.log
   ```

4. **Check service status:**
   ```bash
   uv run python -m dgas data-collection status
   ```

5. **Query recent collection runs:**
   ```sql
   SELECT run_id, run_timestamp, status, symbols_updated, symbols_failed, bars_stored
   FROM data_collection_runs
   ORDER BY run_timestamp DESC
   LIMIT 10;
   ```

### Solutions

#### Solution 1: Restart the Service (Quick Fix)

Use the restart script:
```bash
bash scripts/restart_data_collection.sh
```

Or manually:
```bash
# Stop service
screen -S data-collection -X quit
rm -f .dgas_data_collection.pid

# Start service
screen -dmS data-collection bash -c "cd /opt/DrummondGeometry-evals && /root/.local/bin/uv run dgas data-collection start 2>&1 | tee /tmp/data_collection_startup.log"
```

#### Solution 2: Force a Manual Collection Cycle

If the service is running but cycles are stuck, try forcing a cycle:
```bash
uv run python -m dgas data-collection run-once
```

If this fails with "already executing", the cycle is stuck and you need to restart.

#### Solution 3: Check for Network/API Issues

The collection cycle may hang due to:
- Network connectivity issues
- EODHD API rate limiting
- API authentication problems

Test API connectivity:
```bash
uv run python scripts/diagnose_data_collection.py
```

Look for "API Connectivity Test" section.

#### Solution 4: Investigate Stuck Cycle

If cycles consistently get stuck, check:

1. **Database connection issues:**
   - Verify database is accessible
   - Check connection pool settings
   - Look for database locks

2. **API rate limiting:**
   - Check if you're hitting rate limits
   - Verify `requests_per_minute` setting
   - Consider reducing batch size

3. **Memory/resource issues:**
   - Check system memory usage
   - Verify disk space
   - Check for process limits

### Prevention

1. **Monitor collection runs:**
   - Set up alerts for failed runs
   - Monitor data freshness
   - Track execution times

2. **Improve stuck cycle detection:**
   - The scheduler has timeout protection (1 hour max)
   - Stuck cycle detection should release locks after 2 hours
   - Consider reducing timeout if cycles consistently hang

3. **Add health checks:**
   - Implement periodic health checks
   - Automatically restart on stuck cycles
   - Alert on consecutive failures

### Configuration

Key settings in `config/production.yaml`:

```yaml
data_collection:
  enabled: true
  interval_market_hours: "30m"
  interval_after_hours: "30m"
  interval_weekends: "30m"
  batch_size: 50
  requests_per_minute: 80
  max_retries: 3
  error_threshold_pct: 10.0
```

### Monitoring Queries

**Check recent collection runs:**
```sql
SELECT 
    run_timestamp,
    status,
    symbols_updated,
    symbols_failed,
    bars_stored,
    execution_time_ms
FROM data_collection_runs
ORDER BY run_timestamp DESC
LIMIT 20;
```

**Check data freshness:**
```sql
SELECT 
    ms.symbol,
    MAX(md.timestamp) as latest_timestamp,
    EXTRACT(EPOCH FROM (NOW() - MAX(md.timestamp))) / 60 as age_minutes
FROM market_symbols ms
LEFT JOIN market_data md ON ms.symbol_id = md.symbol_id
WHERE ms.is_active = true
GROUP BY ms.symbol
HAVING MAX(md.timestamp) IS NULL OR EXTRACT(EPOCH FROM (NOW() - MAX(md.timestamp))) / 60 > 60
ORDER BY age_minutes DESC NULLS FIRST
LIMIT 20;
```

### Common Issues

1. **"Collection cycle already running"**
   - Cycle is stuck, restart service

2. **"Maximum number of running instances reached"**
   - Previous cycle never completed, restart service

3. **"High error rate detected: 100.0%"**
   - All symbols failed to collect
   - Check API connectivity and authentication
   - Verify symbols are valid

4. **"Network error contacting EODHD"**
   - Network connectivity issue
   - API may be temporarily unavailable
   - Check internet connection

### Next Steps

After resolving the immediate issue:

1. Monitor the service for 24 hours
2. Verify data is being collected regularly
3. Check that data freshness improves
4. Set up automated monitoring/alerts
5. Consider implementing automatic restart on stuck cycles
