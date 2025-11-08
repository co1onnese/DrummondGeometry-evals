#!/usr/bin/env python3
"""Launcher script for evaluation backtest with proper output handling."""

import sys
import subprocess
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Import and run the main function
from run_evaluation_backtest import main

if __name__ == "__main__":
    sys.exit(main())
