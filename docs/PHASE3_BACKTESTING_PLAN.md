## Phase 3 Backtesting & Analytics Toolkit

### Objectives
- Deliver the deterministic backtesting engine, strategy interface, and analytics tooling mandated by PRD §2.2.1 (BR-001‒BR-003).
- Persist results into existing schema tables (`backtest_results`, `backtest_trades`, `trading_signals`) with complete metadata for replay.
- Provide CLI-driven workflows for running single runs, walk-forward batches, and parameter sweeps.
- Produce reproducible reports and regression harnesses to support future phases.

### Architecture Summary

```
┌────────────────────────────────────────────────────────────────────────┐
│                           Backtesting Runner                           │
│  backtesting/runner.py                                                │
│    ├─ parse config / CLI options                                      │
│    ├─ orchestrate historical data loads                               │
│    ├─ invoke Engine for each symbol/strategy combo                    │
│    └─ persist & report results                                        │
└───────────────────────┬────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────┐
│                            Engine Layer                                │
│  backtesting/engine.py                                                │
│    ├─ SimulationEngine (core loop)                                    │
│    │    • iterates bars chronologically                               │
│    │    • maintains positions, equity curve                           │
│    │    • enforces slippage, commission, stops                        │
│    ├─ Order/Position dataclasses                                      │
│    └─ hooks Strategy instances                                        │
└───────────────────────┬────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────┐
│                         Strategy Interface                             │
│  backtesting/strategies/base.py                                       │
│    ├─ StrategyConfig (pydantic model)                                 │
│    ├─ StrategyContext (read-only view of data & positions)            │
│    └─ BaseStrategy.generate_signals(...)                              │
│  backtesting/strategies/multi_timeframe.py                            │
│    └─ Reference strategy using Phase 2 coordinator outputs            │
└───────────────────────┬────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────┐
│                            Data Access                                 │
│  backtesting/data_loader.py                                           │
│    ├─ load_ohlcv(symbol, interval, start, end)                        │
│    │    • reuses dgas.data.models.IntervalData                        │
│    │    • returns chronological iterator                              │
│    ├─ load_indicators(...)                                            │
│    │    • PLdot, envelopes, states, patterns (Phase 2 outputs)        │
│    └─ caching hooks for reuse                                         │
└───────────────────────┬────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────┐
│                          Metrics & Persistence                         │
│  backtesting/metrics.py                                               │
│    ├─ equity_curve(), drawdown(), sharpe(), sortino(), etc.           │
│  backtesting/persistence.py                                           │
│    ├─ save_results(BacktestReport) → backtest_results                 │
│    └─ save_trades([...]) → backtest_trades                            │
└────────────────────────────────────────────────────────────────────────┘
```

### Key Decisions
1. **Immutability**: Continue using frozen dataclasses for trade snapshots and strategy signals to avoid accidental mutation.
2. **Strategy Contracts**: Strategies emit `Signal` objects (entry/exit/stop adjustments) rather than directly mutating positions.
3. **Timeframe Handling**: The engine receives pre-aligned data bundles (HTF + trading TF) supplied by the runner to ensure deterministic sequencing.
4. **Extensibility**: Strategy registry allows discovery via entry-points or internal mapping for Phase 4 automation.
5. **Performance Hooks**: Engine surfaces instrumentation (bars processed/sec, trade counts) for logging and CLI progress output.

### Data Loading Plan
- Add repository helper `fetch_market_data(conn, symbol_id, interval, start, end) -> list[IntervalData]` in `dgas/data/repository.py` with optional chunking.
- Create loader functions to map DB rows to IntervalData and to fetch precomputed indicators (market states, pattern events, multi_timeframe_analysis) when present.
- Implement graceful fallback when indicator history is missing: either recompute on the fly (stretch) or skip advanced signals with warnings.

### Simulation Flow
1. Runner fetches config: symbols, intervals, strategy, parameter grid, walk-forward windows.
2. For each (symbol, parameter set):
   - Load OHLCV and dependent indicators for the training + testing periods.
   - Instantiate Strategy with config and metadata.
   - Feed chronological bar stream into `SimulationEngine`.
   - Capture fills, equity curve, and metrics snapshot.
   - Persist results and optionally emit CLI report line.
3. Aggregate metrics for sweeps and produce Markdown/JSON outputs.

### Metrics Inventory
- Cumulative/annualized return
- Sharpe, Sortino, Calmar, Information ratio
- Max drawdown + duration
- Win rate, profit factor, average win/loss
- Value-at-Risk (historical), Conditional VaR
- Exposure statistics (time in market, average position size)

### Persistence Strategy
- Use explicit transactions via `dgas/db/get_connection` to write `backtest_results` and `backtest_trades`.
- Store runtime configuration in `backtest_results.test_config` JSONB (strategy, parameters, walk-forward metadata).
- Optionally emit `trading_signals` rows if strategies choose to materialize actionable signals; include foreign key back to `backtest_id`.

### CLI Enhancements
- Extend `dgas.__main__` with `backtest` subcommand delegating to new runner module.
- Support output modes: summary (console table), detailed (per-trade snippet), json (machine-readable).
- Accept flags for saving Markdown/CSV reports to disk.
- Provide `--walk-forward` and `--optimize` toggles along with concurrency hints (future use).

### Testing Approach
- Unit tests for metrics with deterministic fixtures.
- Engine tests using synthetic price series verifying P&L math and order lifecycle.
- Integration test running CLI backtest on sample dataset (fixtures under `tests/backtesting/`).
- Regression harness storing expected result snapshot for baseline strategy to detect drift.

### Open Questions / Follow-ups
1. Do we recompute Phase 2 indicators on the fly if database lacks history? (Proposed: fail gracefully with actionable message.)
2. Should walk-forward windows be persisted as multiple `backtest_results` rows or single row with embedded detail? (Proposed: one parent row with child records stored in JSON array within `test_config`.)
3. For large universes, do we need interim caching of data bundles on disk? (Out of scope for first pass; document limitations.)

