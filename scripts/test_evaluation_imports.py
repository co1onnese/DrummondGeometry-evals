#!/usr/bin/env python3
"""Test evaluation script imports and early execution."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

print("Testing imports...", flush=True)

try:
    print("  Importing dgas.backtesting.portfolio_engine...", flush=True)
    from dgas.backtesting.portfolio_engine import (
        PortfolioBacktestConfig,
        PortfolioBacktestEngine,
        PortfolioBacktestResult,
    )
    print("  ✓ portfolio_engine imported", flush=True)
except Exception as e:
    print(f"  ✗ Failed to import portfolio_engine: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("  Importing dgas.backtesting.strategies.prediction_signal...", flush=True)
    from dgas.backtesting.strategies.prediction_signal import (
        PredictionSignalStrategy,
        PredictionSignalStrategyConfig,
    )
    print("  ✓ prediction_signal imported", flush=True)
except Exception as e:
    print(f"  ✗ Failed to import prediction_signal: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("  Importing dgas.backtesting.metrics...", flush=True)
    from dgas.backtesting.metrics import calculate_performance
    print("  ✓ metrics imported", flush=True)
except Exception as e:
    print(f"  ✗ Failed to import metrics: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

try:
    print("  Importing dgas.db...", flush=True)
    from dgas.db import get_connection
    print("  ✓ db imported", flush=True)
except Exception as e:
    print(f"  ✗ Failed to import db: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting database connection...", flush=True)
try:
    with get_connection() as conn:
        print("  ✓ Database connection successful", flush=True)
except Exception as e:
    print(f"  ✗ Database connection failed: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting symbol loading...", flush=True)
try:
    csv_path = Path(__file__).parent.parent / "data" / "nasdaq100_constituents.csv"
    if not csv_path.exists():
        print(f"  ✗ CSV file not found: {csv_path}", flush=True)
        sys.exit(1)
    
    symbols = []
    with open(csv_path, "r") as f:
        next(f)  # Skip header
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if parts and parts[0]:
                symbol = parts[0].strip()
                if symbol:
                    symbols.append(symbol)
    
    print(f"  ✓ Loaded {len(symbols)} symbols", flush=True)
except Exception as e:
    print(f"  ✗ Failed to load symbols: {e}", flush=True)
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✓ All imports and basic checks passed!", flush=True)
print("The evaluation script should be able to start.", flush=True)
