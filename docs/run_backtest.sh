#!/bin/bash
cd /opt/DrummondGeometry-evals
source .venv/bin/activate

# Read symbols from file
SYMBOLS=$(cat /tmp/full_symbols.txt)

# Run backtest
dgas backtest $SYMBOLS \
  --interval 30m \
  --htf 1d \
  --start 2025-05-01 \
  --end 2025-11-06 \
  --initial-capital 100000 \
  --commission-rate 0.0 \
  --slippage-bps 1 \
  --strategy multi_timeframe \
  --strategy-param max_risk_fraction=0.02 \
  --output-format summary \
  --report reports/full_universe_may_nov_2025.md \
  --json-output reports/full_universe_may_nov_2025.json \
  2>&1 | tee /tmp/backtest_run.log
