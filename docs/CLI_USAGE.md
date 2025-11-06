# Drummond Geometry Analysis CLI

## Overview

The CLI exposes two primary workflows:

- `dgas analyze` for real-time Drummond Geometry analysis
- `dgas backtest` for running historical strategy backtests with reporting and optional persistence

### Analyze Command

The `dgas analyze` command provides comprehensive Drummond Geometry analysis for market symbols, including:

- **PLdot Calculations**: 3-period moving average with forward projection
- **Envelope Bands**: Drummond 3-period volatility-based bands
- **Market State Classification**: 5-state model (TREND, CONGESTION_ENTRANCE, CONGESTION_ACTION, CONGESTION_EXIT, REVERSAL)
- **Pattern Detection**: PLdot Push, PLdot Refresh, Exhaust, C-Wave, Congestion Oscillation
- **Multi-Timeframe Coordination**: HTF trend filtering with confluence detection
- **Trading Signals**: Long/short/wait/reduce recommendations with risk levels

### Backtest Command Overview

The `dgas backtest` command orchestrates historical simulations on data already stored in PostgreSQL. It:

- Loads OHLCV history via `dgas.data.repository.fetch_market_data`
- Runs the configured strategy through the deterministic `SimulationEngine`
- Computes performance metrics (return, Sharpe, drawdown, trade stats)
- Optionally persists results into `backtest_results` / `backtest_trades`
- Produces console output plus optional Markdown/JSON artifacts

Typical usage:

```bash
uv run python -m dgas backtest AAPL MSFT \
  --interval 1h \
  --strategy multi_timeframe \
  --start 2022-01-01 --end 2023-12-31 \
  --initial-capital 100000 \
  --commission-rate 0.0005 \
  --risk-free-rate 0.02 \
  --output-format detailed \
  --report reports/backtests --json-output reports/backtests
```

### Key Backtest Options

| Flag | Description |
| --- | --- |
| `--strategy` | Strategy registry key (default `multi_timeframe`). |
| `--strategy-param key=value` | Override strategy-specific parameters (repeatable). |
| `--initial-capital` | Starting capital for simulation. |
| `--commission-rate` | Decimal commission per trade leg. |
| `--slippage-bps` | Slippage in basis points applied to fills. |
| `--risk-free-rate` | Annual risk-free rate for Sharpe/Sortino. |
| `--no-save` | Do not persist results to the database. |
| `--output-format` | `summary`, `detailed`, or `json`. |
| `--report` | Markdown report target (file or directory). |
| `--json-output` | JSON report target (file or directory). |
| `--limit-bars` | Limit number of most recent bars (debugging/testing). |

`--report` / `--json-output` accept either a direct file path (single symbol) or a directory (per-symbol files auto-named).

## Installation

Ensure you have the required dependencies:

```bash
uv sync
```

## Basic Usage

### Analyze a Single Symbol

```bash
uv run python -m dgas analyze AAPL
```

This will:
1. Load 200 bars of data from the database (default)
2. Calculate indicators for 4h (HTF) and 1h (trading) timeframes
3. Perform multi-timeframe coordination analysis
4. Display results in a beautiful table format

### Analyze Multiple Symbols

```bash
uv run python -m dgas analyze AAPL MSFT GOOGL
```

Analyzes multiple symbols in sequence with full reports for each.

## Command Options

### Timeframe Configuration

**Higher Timeframe (HTF)** - Defines trend direction:
```bash
uv run python -m dgas analyze AAPL --htf 1d
uv run python -m dgas analyze AAPL --higher-timeframe 1d  # Same as above
```

**Trading Timeframe** - Entry signals:
```bash
uv run python -m dgas analyze AAPL --trading 30min
uv run python -m dgas analyze AAPL --trading-timeframe 30min  # Same as above
```

**Combined**:
```bash
uv run python -m dgas analyze AAPL --htf 1d --trading 4h
```

Common timeframe combinations:
- **Day Trading**: `--htf 1d --trading 1h`
- **Swing Trading**: `--htf 1w --trading 1d`
- **Scalping**: `--htf 4h --trading 15min`

### Data Range

**Lookback Bars**:
```bash
uv run python -m dgas analyze AAPL --lookback 500
```

Specifies how many bars to load for analysis. Default: 200

- Minimum: ~50 bars (for indicator calculations)
- Recommended: 200-500 bars
- Maximum: Limited by database and memory

### Output Formats

**Summary** (default) - Multi-timeframe analysis only:
```bash
uv run python -m dgas analyze AAPL --format summary
```

**Detailed** - Shows single timeframe analysis + multi-timeframe:
```bash
uv run python -m dgas analyze AAPL --format detailed
```

**JSON** (coming soon) - Machine-readable output:
```bash
uv run python -m dgas analyze AAPL --format json
```

### Database Persistence

**Save Results**:
```bash
uv run python -m dgas analyze AAPL --save
```

Saves the following to database:
- Market states (both timeframes)
- Pattern events (both timeframes)
- Multi-timeframe analysis
- Confluence zones

This allows:
- Historical tracking of signals
- Backtesting validation
- Dashboard integration
- Signal alerts

## Output Interpretation

### Multi-Timeframe Analysis Display

```
╭─────────────────────────────────────────────────────────────╮
│ Multi-Timeframe Analysis: AAPL                              │
╰─────────────────────────────────────────────────────────────╯

Timeframe Comparison
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Timeframe      Trend    Strength
──────────────────────────────────────────────────────────────
HTF (4h)       UP       85.00%
Trading (1h)   UP       N/A

Alignment Type:     PERFECT
Alignment Score:    92.00%
Trade Permitted:    ✅ YES

HTF PLdot:          $150.25
Trading PLdot:      $150.45
Distance:           0.13%
Position:           AT HTF

Signal Strength:    78.00%
Risk Level:         LOW
Recommended Action: LONG
Pattern Confluence: ✅ YES

╭─────────────────────────────────────────────────────────────╮
│ 🚀 Trading Signal                                            │
├─────────────────────────────────────────────────────────────┤
│ LONG SIGNAL                                                  │
│ Signal Strength: 78.0%                                       │
│ Risk Level: LOW                                              │
│ HTF Trend: UP                                                │
╰─────────────────────────────────────────────────────────────╯
```

### Key Metrics Explained

#### Alignment Type
- **PERFECT** (≥80%): Both timeframes fully aligned - high confidence
- **PARTIAL** (≥60%): Good alignment - tradeable
- **DIVERGENT** (≥30%): Weak alignment - caution
- **CONFLICTING** (<30%): Opposing signals - wait

#### Signal Strength (0-100%)
Composite score from:
- Alignment score (40% weight)
- HTF trend strength (30% weight)
- Confluence zone proximity (15% weight)
- Pattern confluence (15% weight)

Interpretation:
- **≥70%**: Strong signal - full position
- **60-70%**: Moderate signal - reduced position
- **50-60%**: Weak signal - minimal position
- **<50%**: No trade

#### Risk Level
- **LOW**: High alignment, strong HTF trend, good confluence
- **MEDIUM**: Partial alignment or moderate signals
- **HIGH**: Low alignment, conflicting trends, or low confidence

#### Recommended Action
- **LONG**: Enter long position
- **SHORT**: Enter short position
- **WAIT**: No clear opportunity
- **REDUCE**: Close or reduce existing positions

## Examples

### Example 1: Basic Analysis

```bash
uv run python -m dgas analyze AAPL
```

**Use Case**: Quick check of AAPL's current Drummond state

**Expected Output**:
- HTF and trading timeframe trends
- Alignment metrics
- Signal recommendation
- Confluence zones

### Example 2: Day Trading Setup

```bash
uv run python -m dgas analyze TSLA --htf 1d --trading 1h --lookback 300
```

**Use Case**: Day trading TSLA with daily trend filter

**Configuration**:
- HTF (1d): Defines overall trend direction
- Trading (1h): Entry signals
- 300 bars: ~2 weeks of hourly data

### Example 3: Multi-Symbol Screen

```bash
uv run python -m dgas analyze AAPL MSFT GOOGL AMZN NVDA --save
```

**Use Case**: Screen multiple stocks for opportunities

**Configuration**:
- Analyzes 5 symbols
- Saves all results to database
- Can filter high-strength signals in database

### Example 4: Detailed Analysis with Persistence

```bash
uv run python -m dgas analyze AAPL --format detailed --save --htf 4h --trading 15min
```

**Use Case**: Detailed intraday analysis with record keeping

**Shows**:
- Individual timeframe PLdot, envelopes, states, patterns
- Multi-timeframe coordination
- All results saved to database

### Example 5: Custom Timeframe Ratio

```bash
uv run python -m dgas analyze SPY --htf 1w --trading 1d --lookback 500
```

**Use Case**: Swing trading with weekly trend filter

**Configuration**:
- HTF (1w): Weekly trend direction (authoritative)
- Trading (1d): Daily entry signals
- 500 bars: ~2 years of daily data

## Integration with Database

### Prerequisites

1. **Database Running**: Ensure PostgreSQL is running
2. **Migration Applied**: Run migration 002:
   ```bash
   psql -U postgres -d drummond_db -f src/dgas/migrations/002_enhanced_states_patterns.sql
   ```
3. **Data Available**: Market data must be ingested first

### Workflow with Persistence

```bash
# 1. Analyze and save
uv run python -m dgas analyze AAPL MSFT --save

# 2. Query results (using psql or Python)
psql -U postgres -d drummond_db -c "
  SELECT
    timestamp, htf_trend, trading_tf_trend,
    recommended_action, signal_strength, risk_level
  FROM multi_timeframe_analysis
  WHERE symbol_id = (SELECT symbol_id FROM market_symbols WHERE symbol = 'AAPL')
  ORDER BY timestamp DESC
  LIMIT 10;
"

# 3. Backtest validation (future feature)
# Results can be compared against actual market movements
```

## Troubleshooting

### "Symbol not found in database"

```bash
# Check available symbols
psql -U postgres -d drummond_db -c "SELECT symbol, exchange FROM market_symbols;"

# If missing, ingest data first (Phase 1)
```

### "No market data found"

```bash
# Check data availability
psql -U postgres -d drummond_db -c "
  SELECT COUNT(*), MIN(timestamp), MAX(timestamp)
  FROM market_data
  WHERE symbol_id = (SELECT symbol_id FROM market_symbols WHERE symbol = 'AAPL')
    AND interval_type = '1h';
"

# If missing, run data ingestion
```

### "Database persistence not available"

This means `psycopg2` is not installed. The `--save` flag will be ignored, but analysis still works.

To enable persistence:
```bash
uv pip install psycopg2-binary
```

### "At least 3 intervals are required"

PLdot calculation requires minimum 3 bars. Check:
- Database has enough data
- Lookback value is sufficient
- Interval type matches data in database

## Performance Notes

### Speed
- **Single symbol**: ~1-2 seconds (200 bars)
- **10 symbols**: ~10-15 seconds
- **Database save**: +500ms per symbol

### Resource Usage
- **Memory**: ~50MB per symbol (200 bars)
- **Database**: ~10KB per analysis record
- **CPU**: Mostly pandas operations

### Optimization Tips

1. **Batch Analysis**: Analyze multiple symbols in one command rather than separate runs
2. **Lookback**: Use minimum necessary lookback (200 bars usually sufficient)
3. **Persistence**: Only save when needed for historical tracking
4. **Timeframes**: Avoid extreme ratios (e.g., 1w vs 5min)

## Advanced Usage

### Scripting

```python
#!/usr/bin/env python
from dgas.cli import run_analyze_command

# Analyze watchlist
watchlist = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "TSLA"]

exit_code = run_analyze_command(
    symbols=watchlist,
    htf_interval="1d",
    trading_interval="1h",
    lookback_bars=200,
    save_to_db=True,
    output_format="summary",
)
```

### Cron Jobs

```bash
# Daily analysis at market close
0 16 * * 1-5 cd /path/to/project && uv run python -m dgas analyze AAPL MSFT GOOGL --save >> /var/log/dgas/analysis.log 2>&1
```

### Dashboard Integration

```python
# Get latest analysis for dashboard
from dgas.db.persistence import DrummondPersistence

with DrummondPersistence() as db:
    analysis = db.get_latest_multi_timeframe_analysis("AAPL", "4h", "1h")

    if analysis and analysis["trade_permitted"]:
        display_signal(
            symbol="AAPL",
            action=analysis["recommended_action"],
            strength=analysis["signal_strength"],
            risk=analysis["risk_level"]
        )
```

## Next Steps

After running analysis:

1. **Verify Signals**: Check confluence zones against current price
2. **Risk Management**: Use risk_level for position sizing
3. **Entry Timing**: Use trading timeframe for precise entries
4. **Stop Loss**: Place below nearest confluence support (longs) or resistance (shorts)
5. **Target**: Use next confluence level in trend direction
6. **Monitor**: Re-run analysis periodically to track state changes

## See Also

- [Multi-Timeframe Implementation](MULTI_TIMEFRAME_IMPLEMENTATION.md) - Technical details
- [Database Schema](../src/dgas/migrations/002_enhanced_states_patterns.sql) - Persistence structure
- [Implementation Status](IMPLEMENTATION_STATUS_UPDATE.md) - Current capabilities

## Feedback

Report issues or request features at:
https://github.com/anthropics/claude-code/issues
