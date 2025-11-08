# Evaluation Backtest Monitoring Guide

This guide explains how to monitor the long-running evaluation backtest for errors and progress.

## Quick Start

### Start Monitoring (Foreground)
```bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
python3 scripts/monitor_evaluation.py
```

### Start Monitoring (Background)
```bash
cd /opt/DrummondGeometry-evals
./scripts/start_monitor.sh
```

### View Monitor Output
```bash
tail -f /tmp/evaluation_monitor.log
```

### Check Status Once
```bash
python3 scripts/monitor_evaluation.py --once
```

## Monitoring Features

The monitor watches the log file (`/tmp/full_evaluation.log`) for:

- **Errors**: Detects ImportError, ValueError, exceptions, tracebacks, and other error patterns
- **Warnings**: Detects warnings and cautionary messages
- **Progress**: Tracks progress updates (e.g., "Progress: 10.1%")
- **Completion**: Detects when backtest completes successfully
- **Process Status**: Checks if the evaluation process is running and shows CPU/memory usage

## Monitor Options

```bash
python3 scripts/monitor_evaluation.py [OPTIONS]

Options:
  --log-file PATH     Path to log file (default: /tmp/full_evaluation.log)
  --interval SECONDS  Check interval in seconds (default: 5.0)
  --no-alert          Don't alert on errors
  --once              Check once and exit (don't monitor continuously)
```

## Example Usage

### Monitor with 10-second intervals
```bash
python3 scripts/monitor_evaluation.py --interval 10
```

### Monitor different log file
```bash
python3 scripts/monitor_evaluation.py --log-file /path/to/custom.log
```

### Silent monitoring (no alerts)
```bash
python3 scripts/monitor_evaluation.py --no-alert
```

## What the Monitor Shows

The monitor displays:

1. **Process Status**: Whether the evaluation process is running, CPU/memory usage, elapsed time
2. **Log File Status**: File path, size, last update time
3. **Statistics**: Total errors, warnings, monitor uptime
4. **Recent Progress**: Last 5 progress updates
5. **New Errors/Warnings**: Errors and warnings detected since last check
6. **Error History**: Last 5 errors encountered
7. **Completion Status**: Whether backtest has completed
8. **Stale Log Warning**: Alerts if log hasn't been updated in 5+ minutes

## Error Detection

The monitor automatically detects:

- `✗ ERROR`
- `ERROR:`
- `Exception:`
- `Traceback`
- `ImportError`
- `ValueError`
- `KeyError`
- `AttributeError`
- `TypeError`
- `RuntimeError`
- `Failed` / `failed`
- `FATAL`

## Other Monitoring Tools

### Check Process Status
```bash
python3 scripts/check_evaluation_status.py
```

### Diagnose Issues
```bash
python3 scripts/diagnose_evaluation.py
```

### View Log File Directly
```bash
tail -f /tmp/full_evaluation.log
```

### View Last 100 Lines
```bash
tail -n 100 /tmp/full_evaluation.log
```

### Search for Errors
```bash
grep -i "error\|exception\|traceback" /tmp/full_evaluation.log | tail -20
```

## Troubleshooting

### Monitor shows "Process NOT RUNNING"
- Check if evaluation is actually running: `pgrep -f run_evaluation_backtest.py`
- If not running, start it: `./scripts/run_evaluation_with_debug.sh`

### Monitor shows "Log file hasn't been updated"
- Process may be hung or waiting on something
- Check CPU usage: `top -p $(pgrep -f run_evaluation_backtest.py)`
- Check database connections if process is waiting on DB

### Monitor shows many errors
- Check the error details in the monitor output
- Review the log file: `tail -n 200 /tmp/full_evaluation.log`
- Fix the root cause and restart the backtest

### Monitor output is too verbose
- Use `--interval 10` to check less frequently
- Use `--once` to check once and exit
- Use `--no-alert` to suppress error alerts

## Best Practices

1. **Start monitor before starting backtest**: This ensures you catch errors from the beginning
2. **Run monitor in background**: Use `start_monitor.sh` to run it in the background
3. **Check periodically**: Even with background monitoring, check the monitor log periodically
4. **Save monitor output**: The monitor log is saved to `/tmp/evaluation_monitor.log`
5. **Monitor on separate terminal**: Keep a terminal open just for monitoring

## Expected Backtest Duration

- **Estimated time**: 8-15 hours for 101 symbols over 3 months
- **Progress updates**: Every 5% of timesteps (approximately every 70 timesteps)
- **Total timesteps**: ~1,401 timestamps

## Monitoring During Long Runs

For very long runs, consider:

1. **Run monitor in background**: `./scripts/start_monitor.sh`
2. **Set up email alerts**: Modify monitor to send emails on errors (future enhancement)
3. **Use screen/tmux**: Run monitor in a screen/tmux session so it persists
4. **Check periodically**: Even with automated monitoring, check manually every few hours

## Example Monitor Output

```
================================================================================
EVALUATION BACKTEST MONITOR - 2025-11-08 08:55:00
================================================================================
✓ Process Status: RUNNING
  CPU: 45.2% | Memory: 12.3% | Elapsed: 02:15:30 | State: R

✓ Log File: /tmp/full_evaluation.log (1234.5 KB)

Monitor Uptime: 2:15:30
Last Log Update: 3 seconds ago
Total Errors: 0
Total Warnings: 2

📊 Recent Progress Updates:
  [08:54:45] Progress: 15.2% (213/1,401 timesteps)
  [08:54:50] Progress: 15.3% (214/1,401 timesteps)
  [08:54:55] Progress: 15.4% (215/1,401 timesteps)

================================================================================
Press Ctrl+C to stop monitoring
================================================================================
```
