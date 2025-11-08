#!/usr/bin/env python3
"""Quick test of data loader performance."""

import os
from datetime import datetime, timezone
from pathlib import Path

# Add src to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
src_path = project_root / "src"
import sys
sys.path.insert(0, str(src_path))

from dgas.backtesting.portfolio_data_loader import PortfolioDataLoader

# Test with 10 symbols first
symbols = ["AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "NVDA", "META", "TSLA", "AVGO", "PEP"]

start = datetime(2025, 8, 8, tzinfo=timezone.utc)
end = datetime(2025, 11, 1, tzinfo=timezone.utc)

print("Testing data loader with 30 symbols...")
print(f"Period: {start.date()} to {end.date()}")

loader = PortfolioDataLoader(regular_hours_only=True, exchange_code="US")

import time
t0 = time.time()
bundles = loader.load_portfolio_data(symbols, "30m", start, end)
t1 = time.time()

print(f"\n✓ Loaded data in {t1 - t0:.1f} seconds")
print(f"Symbols loaded: {len(bundles)}")

for symbol, bundle in list(bundles.items())[:3]:
    print(f"  {symbol}: {len(bundle.bars)} bars")
