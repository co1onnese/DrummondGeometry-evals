## Phase 3 CLI & Testing Plan

### Goals
- Surface backtesting capabilities directly through the `dgas` CLI.
- Provide reproducible reports (console, Markdown, JSON) for strategy runs, walk-forward batches, and parameter sweeps.
- Establish automated tests (unit + integration) that validate engine correctness, metric outputs, persistence wiring, and CLI UX.

### CLI Scope

```
python -m dgas backtest --symbols AAPL MSFT \
    --strategy multi_timeframe \
    --interval 1h \
    --start 2022-01-01 --end 2024-01-01 \
    --initial-capital 100000 \
    --risk-free-rate 0.02 \
    --output-format summary \
    --report reports/backtests/aapl.md \
    --json-output reports/backtests/aapl.json
```

| Flag | Purpose |
| --- | --- |
| `--symbols` | One or more ticker symbols (space-delimited). |
| `--interval` | Interval string stored in DB (default `1h`). |
| `--strategy` | Strategy registry key (default `multi_timeframe`). |
| `--start`, `--end` | ISO dates delimiting historical window (optional). |
| `--initial-capital` | Seed capital passed to `SimulationConfig`. |
| `--commission-rate` | Per-trade commission (bps). |
| `--slippage-bps` | Entry/exit slippage in basis points. |
| `--risk-free-rate` | Annual risk-free rate for metrics (default 0). |
| `--walk-forward` | JSON or YAML config describing train/test windows. |
| `--optimize` | Parameter sweep spec (e.g., `param=value1,value2`). |
| `--output-format` | `summary` (default), `detailed`, or `json`. |
| `--report` | Optional Markdown file path for human-readable output. |
| `--json-output` | Optional JSON artifact for automation. |
| `--save` | Persist backtest + trades to DB (default True). |
| `--no-save` | Disable persistence (for experimental runs). |

### Module Additions

- `src/dgas/backtesting/runner.py`
  - Parse `BacktestRequest` objects (multi-symbol, optional sweeps).
  - Resolve strategy entry via registry (`STRATEGY_REGISTRY`).
  - Loop symbols → load dataset → run engine → compute metrics → persist (optional) → collect results.
  - Build `BacktestReport` dataclass summarizing metrics/trades for downstream formatting.

- `src/dgas/backtesting/reporting.py`
  - Functions to format reports:
    - `render_summary_table(reports) -> str`
    - `render_detailed_report(report) -> str`
    - `export_markdown(report, path)`
    - `export_json(report, path)`

- `src/dgas/cli/backtest.py`
  - CLI handler bridging argparse namespace to `BacktestRunner`.
  - Uses `rich` tables/panels for console output matching existing CLI styling.

- Update `dgas/__main__.py`
  - Add `backtest` subcommand wiring to new CLI handler.

### Testing Strategy

#### Unit Tests (`tests/backtesting/`)
- `test_metrics.py`: Validate metric calculations using deterministic `BacktestResult` fixtures.
- `test_persistence.py`: Use an in-memory or temporary Postgres (via pytest fixtures/mocks) to ensure SQL inserts behave as expected (mocked cursor to avoid real DB in unit tests).
- `test_runner.py`: Mock dataset loader, engine, metrics, and persistence to verify CLI orchestrator flows, parameter parsing, and filtering logic.

#### Integration Tests (`tests/cli/test_backtest_cli.py`)
- Create small synthetic dataset fixtures (using sqlite or stub repository) to run end-to-end CLI invocation via `CliRunner` (pytest subprocess expected).
- Assert console output contains key metrics, generated files exist (Markdown/JSON), and persistence is invoked when configured (mock DB).

#### Regression Harness
- Store canonical backtest scenario (1 symbol, 10 bars) with expected JSON summary under `tests/backtesting/fixtures/reference_backtest.json`.
- Regression test to compare output of `calculate_performance` + `persist_backtest` (with mocked DB) to expected fields.

### Implementation Sequence
1. Strategy registry + runner module.
2. CLI argparse integration with Rich formatting.
3. Reporting utilities (Markdown/JSON).
4. Tests for metrics/persistence (unit) → runner (unit) → CLI (integration).
5. Wire CLI docs (`docs/CLI_USAGE.md`, `llms.txt`) and README updates.

### Risk Mitigations
- **Database writes**: Guard persistence with explicit `--save/--no-save`; handle missing symbols with clear error.
- **Large datasets**: Introduce `--limit-bars` flag for debugging/testing to avoid exhausting memory.
- **Strategy lookups**: Raise helpful error if strategy not registered.
- **Reporting**: Fail gracefully when file paths invalid (wrap in try/except, surface message, continue execution).

