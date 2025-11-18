# Data Collection Troubleshooting Guide

## Common Issues

### Issue: High Failure Rate (99%+)

**Symptoms**: Collection runs show `symbols_failed` close to `symbols_requested`

**Causes**:
1. **Weekend/Market Closure**: No new data available - this is **expected behavior**
2. **Invalid Symbols**: Symbols that don't exist in EODHD API (e.g., EVAL_NOV6)
3. **Data Already Up-to-Date**: All fetched data is older than latest DB timestamp

**Solutions**:

1. **Check if it's a weekend/holiday**:
   ```bash
   date
   # If Saturday/Sunday, failures are expected - no market data
   ```

2. **Deactivate invalid symbols**:
   ```bash
   cd /opt/DrummondGeometry-evals
   source .env
   uv run python scripts/fix_data_collection.py
   ```

3. **Verify API is working**:
   ```bash
   uv run python -c "
   from dgas.data.client import EODHDClient, EODHDConfig
   from dgas.settings import get_settings
   client = EODHDClient(EODHDConfig.from_settings(get_settings()))
   data = client.fetch_intraday('AAPL', interval='30m', limit=5)
   print(f'API working: {len(data)} bars fetched')
   client.close()
   "
   ```

### Issue: "Filtered out X bars that are older than latest DB timestamp"

**Explanation**: This is **normal behavior**. The incremental update function:
- Fetches data from the last few days
- Filters out any bars that are older than what's already in the database
- Only stores new data

**When this happens**:
- Weekend/holiday (no new data)
- Data is already up-to-date
- Market hasn't opened yet

**Action**: None needed - this is expected.

### Issue: Service Stopped Running

**Check status**:
```bash
uv run dgas data-collection status
screen -ls | grep data_collection
```

**Restart**:
```bash
cd /opt/DrummondGeometry-evals
./scripts/start_all_services.sh
# Or manually:
screen -dmS dgas_data_collection bash -c "cd /opt/DrummondGeometry-evals && source .env && exec uv run dgas data-collection start --config config/production.yaml 2>&1 | tee /var/log/dgas/data_collection.log"
```

### Issue: Invalid Symbols Causing Errors

**Symptoms**: Logs show "404 - Ticker Not Found" for specific symbols

**Solution**:
```bash
# Deactivate invalid symbols
cd /opt/DrummondGeometry-evals
source .env
uv run python scripts/fix_data_collection.py

# Or manually:
uv run python -c "
from dgas.db import get_connection
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute(\"UPDATE market_symbols SET is_active = false WHERE symbol LIKE '%EVAL%' OR symbol LIKE '%TEST%'\")
        print(f'Deactivated: {cur.rowcount} symbols')
        conn.commit()
"
```

## Understanding Collection Results

### Normal Weekend Behavior

On weekends, you may see:
- `symbols_updated: 0` - No new data (markets closed)
- `symbols_failed: 517` - All symbols have no new data
- `bars_fetched: 14` - Some historical data fetched but filtered out
- `bars_stored: 0` - No new data to store

**This is expected** - markets are closed, so there's no new data to collect.

### Normal Weekday Behavior

On weekdays during market hours:
- `symbols_updated: 50-100+` - Many symbols have new data
- `symbols_failed: 0-50` - Some symbols may have no new data yet
- `bars_fetched: 1000+` - New bars fetched
- `bars_stored: 1000+` - New bars stored

## Monitoring

### Check Recent Collection Runs

```bash
cd /opt/DrummondGeometry-evals
source .env
uv run python -c "
from dgas.db import get_connection
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute('''
            SELECT run_timestamp, symbols_requested, symbols_updated, symbols_failed, 
                   bars_fetched, bars_stored, status
            FROM data_collection_runs
            ORDER BY run_timestamp DESC
            LIMIT 5
        ''')
        for row in cur.fetchall():
            print(f'{row[0]}: req={row[1]}, upd={row[2]}, fail={row[3]}, fetched={row[4]}, stored={row[5]}, status={row[6]}')
"
```

### Check Logs

```bash
# Recent errors
tail -100 /var/log/dgas/data_collection.log | grep -i error

# Recent collection cycles
tail -100 /var/log/dgas/data_collection.log | grep -E "Collection complete|Starting data collection"
```

### Check Data Freshness

```bash
cd /opt/DrummondGeometry-evals
source .env
uv run python scripts/verify_data_freshness.py
```

## Best Practices

1. **Monitor on weekdays**: Collection is most active during market hours
2. **Expect weekend failures**: No new data = "failures" (this is normal)
3. **Clean invalid symbols**: Remove EVAL, TEST symbols regularly
4. **Check logs regularly**: Look for actual errors, not just failure counts
5. **Verify API access**: Test API connection if all symbols fail

## When to Worry

**Worry if**:
- All symbols fail on a **weekday during market hours**
- API errors (not 404s) appear in logs
- Service stops running
- Error rate > 50% on active trading days

**Don't worry if**:
- High failure rate on weekends/holidays
- "Filtered out bars" messages
- 0 bars stored when markets are closed
- Some symbols have no new data (normal variation)
