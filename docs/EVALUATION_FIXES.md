# Evaluation Backtest Fixes

## Issues Fixed

### 1. Import Error: `attempted relative import beyond top-level package`

**Location**: `src/dgas/backtesting/portfolio_engine.py:423`

**Problem**: Relative import `from ...prediction.engine` failed when script was run directly.

**Fix**: Changed to absolute import:
```python
# Before:
from ...prediction.engine import GeneratedSignal, SignalType

# After:
from dgas.prediction.engine import GeneratedSignal, SignalType
```

### 2. Undefined Variable: `current_prices`

**Location**: `src/dgas/backtesting/portfolio_engine.py:479`

**Problem**: Variable `current_prices` was used but not defined in `_generate_entry_signals` method.

**Fix**: Added calculation of `current_prices` from timestep before it's used:
```python
# Added before Phase 3:
current_prices = {
    symbol: bar.close for symbol, bar in timestep.bars.items()
}
```

## Testing the Fixes

### Quick Test
```bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
python3 scripts/run_evaluation_backtest.py 2>&1 | head -100
```

### Full Test with Monitoring
```bash
# Terminal 1: Start the backtest
cd /opt/DrummondGeometry-evals
source .venv/bin/activate
./scripts/run_evaluation_with_debug.sh

# Terminal 2: Monitor for errors
python3 scripts/monitor_evaluation.py
```

## Monitoring Setup

### Real-time Monitoring

The evaluation monitor watches the log file for:
- **Errors**: ImportError, ValueError, exceptions, tracebacks
- **Warnings**: Warning messages and cautions
- **Progress**: Progress updates (e.g., "Progress: 10.1%")
- **Completion**: Successful completion detection
- **Process Status**: CPU/memory usage, process state

### Start Monitoring

**Foreground (interactive)**:
```bash
python3 scripts/monitor_evaluation.py
```

**Background**:
```bash
./scripts/start_monitor.sh
tail -f /tmp/evaluation_monitor.log
```

**One-time check**:
```bash
python3 scripts/monitor_evaluation.py --once
```

### Monitor Options

- `--interval SECONDS`: Check interval (default: 5 seconds)
- `--log-file PATH`: Custom log file path
- `--no-alert`: Suppress error alerts
- `--once`: Check once and exit

## Expected Behavior

After fixes, the backtest should:

1. **Start successfully**: No import errors
2. **Load data**: Load 101 symbols with data
3. **Pre-load HTF data**: Cache higher timeframe data
4. **Process timesteps**: Progress through ~1,401 timesteps
5. **Generate signals**: Use PredictionEngine's SignalGenerator
6. **Complete**: Finish and save results to database

## Progress Tracking

The backtest shows progress updates approximately every 5% of timesteps:
- `Progress: 0.1% (1/1,401 timesteps)`
- `Progress: 5.1% (71/1,401 timesteps)`
- `Progress: 10.1% (141/1,401 timesteps)`
- etc.

## Estimated Duration

- **Time**: 8-15 hours for 101 symbols over 3 months
- **Timesteps**: ~1,401 unique timestamps
- **Progress updates**: Every ~70 timesteps (5%)

## Troubleshooting

### If errors still occur:

1. **Check monitor output**: `python3 scripts/monitor_evaluation.py --once`
2. **Check log file**: `tail -n 200 /tmp/full_evaluation.log`
3. **Check process**: `python3 scripts/check_evaluation_status.py`
4. **Diagnose**: `python3 scripts/diagnose_evaluation.py`

### Common Issues:

- **Process not running**: Check if it crashed or was killed
- **Log not updating**: Process may be hung (check CPU usage)
- **Import errors**: Ensure virtual environment is activated
- **Database errors**: Check database connection and schema

## Next Steps

1. **Start the backtest**: `./scripts/run_evaluation_with_debug.sh`
2. **Start monitoring**: `python3 scripts/monitor_evaluation.py`
3. **Check periodically**: Monitor for errors and progress
4. **Review results**: After completion, check database for results

## Files Modified

- `src/dgas/backtesting/portfolio_engine.py`: Fixed imports and variable scope

## Files Created

- `scripts/monitor_evaluation.py`: Real-time monitoring script
- `scripts/start_monitor.sh`: Background monitor launcher
- `docs/EVALUATION_MONITORING.md`: Monitoring guide
- `docs/EVALUATION_FIXES.md`: This file
