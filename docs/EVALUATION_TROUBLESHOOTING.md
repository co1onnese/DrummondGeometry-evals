# Evaluation Backtest Troubleshooting Guide

## Problem: Empty Log File After Hours of Running

**Symptoms:**
- Script started with `nohup python -u scripts/run_evaluation_backtest.py > /tmp/full_evaluation.log 2>&1 &`
- Log file exists but is completely empty (0 bytes)
- Process appears to be running but no output

**Possible Causes:**

### 1. Import Error (Most Likely)
The script crashes before any output due to:
- Missing module/dependency
- Syntax error in imported module
- Database connection failure during import

**Solution:**
```bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
python3 scripts/test_evaluation_imports.py
```

### 2. Data Verification Hanging
The `verify_data_availability()` function checks 101 symbols sequentially, which can take a very long time if database queries are slow.

**Solution:**
- Check database connection and query performance
- The function now includes progress updates (every 10 symbols)
- Consider skipping verification for faster startup

### 3. Database Query Hanging
The portfolio data loader's batch query might be hanging if:
- Database is locked
- Query is too slow for large date ranges
- Connection timeout

**Solution:**
```bash
# Check database connections
psql -U your_user -d your_db -c "SELECT count(*) FROM pg_stat_activity WHERE state = 'active';"

# Check for locks
psql -U your_user -d your_db -c "SELECT * FROM pg_locks WHERE NOT granted;"
```

### 4. Process Actually Crashed
The process may have crashed but the shell still shows it as running.

**Solution:**
```bash
# Check if process is actually running
ps aux | grep run_evaluation_backtest

# Check process state (R=running, S=sleeping, Z=zombie, D=uninterruptible sleep)
ps -o pid,state,cmd -p $(pgrep -f run_evaluation_backtest)
```

## Immediate Actions

### Step 1: Kill Existing Process
```bash
pkill -f run_evaluation_backtest.py
# Wait a few seconds
ps aux | grep run_evaluation_backtest  # Verify it's gone
```

### Step 2: Test Imports
```bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
python3 scripts/test_evaluation_imports.py
```

### Step 3: Run with Better Error Capture
```bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
chmod +x scripts/run_evaluation_with_debug.sh
nohup bash scripts/run_evaluation_with_debug.sh &
```

### Step 4: Monitor Immediately
```bash
# Watch log file grow
tail -f /tmp/full_evaluation.log

# In another terminal, check process
watch -n 5 'ps aux | grep run_evaluation_backtest | grep -v grep'
```

## Expected Output Timeline

If working correctly, you should see:

1. **Immediately (< 1 second):**
   ```
   ================================================================================
   DRUMMOND GEOMETRY EVALUATION BACKTEST
   Testing PredictionEngine SignalGenerator Accuracy
   ================================================================================
   ```

2. **Within 5 seconds:**
   ```
   Configuration:
     Date Range: 2025-09-08 to 2025-11-07
     ...
   ```

3. **Within 30 seconds:**
   ```
   Loaded 101 symbols from ...
   Verifying data availability...
   ```

4. **Within 5-10 minutes:**
   ```
   ✓ 95 symbols have data
   ✗ 6 symbols missing data
   ```

5. **Within 10-15 minutes:**
   ```
   Loading market data...
   ```

If you don't see output within 30 seconds, something is wrong.

## Quick Fix: Skip Data Verification

If data verification is hanging, you can modify the script to skip it:

```python
# In run_evaluation_backtest.py, replace:
symbols_with_data, symbols_missing = verify_data_availability(...)

# With:
symbols_with_data = all_symbols  # Skip verification
symbols_missing = []
print(f"\n⚠ Skipping data verification - using all {len(symbols_with_data)} symbols\n", flush=True)
```

The portfolio engine will fail fast if data is missing anyway.

## Check Database Performance

```bash
# Connect to database
psql -U your_user -d your_db

# Check query performance
EXPLAIN ANALYZE SELECT COUNT(*) FROM market_data WHERE interval_type = '30m' AND timestamp >= '2025-09-08' AND timestamp <= '2025-11-07';

# Check indexes
\d market_data
```

## Contact Points

If the issue persists:
1. Check database logs
2. Check system logs: `journalctl -u postgresql` or `tail -f /var/log/postgresql/postgresql-*.log`
3. Verify disk space: `df -h`
4. Check memory: `free -h`
