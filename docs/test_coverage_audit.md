# Test Coverage Audit (Pre-Enhancement)

Date: 2025-11-06  
Author: GPT-5 Codex

## Calculations

- `tests/calculations/test_patterns.py`
  - Covers baseline detections for PLdot Push, Refresh, Exhaust (bullish/bearish, extension validation), C-Wave, and Congestion Oscillation.
  - Lacks scenarios for adaptive tolerances, slope acceleration, volume filters, or multi-timeframe confirmation (to be added during enhancements).

- `tests/calculations/test_multi_timeframe.py`
  - Exercises `MultiTimeframeCoordinator` alignment scoring, PLdot overlay, confluence zone detection, and congestion handling.
  - Does not currently validate Drummond line integration, zone weighting, or volatility-adjusted tolerances.

## Backtesting

- `tests/backtesting/test_runner.py`
  - Confirms orchestration of dataset loading, strategy instantiation, engine execution, performance calculation, and persistence toggles.
  - Relies on stubs; no coverage of multi-timeframe strategy logic or trailing-stop/position-sizing behaviors.

- `tests/backtesting/test_metrics.py`
  - Validates summary metrics (returns, drawdown, Sharpe/Sortino) against deterministic snapshots.

- `tests/backtesting/test_persistence.py`
  - Exercises database persistence of results and trades.
  - Does not include schema migration assertions for forthcoming metadata fields.

## Gaps & Action Items

1. Introduce edge-case suites for pattern detectors once new parameters are implemented (volatility regimes, slope acceleration, volume overlays).
2. Add strategy-level tests that simulate entries/exits with trailing stops and envelope-based sizing.
3. Extend multi-timeframe tests to cover Drummond line confluence weighting and adaptive tolerance controls.
4. Plan integration or regression tests to confirm prediction engine parity with enhanced strategy outputs.

This audit serves as the baseline reference before implementing the roadmap described in
`docs/drummond_geometry_enhancement_plan.md`.

