# Drummond Geometry Analysis System

A comprehensive, production-ready implementation of the Drummond Geometry Analysis System with advanced prediction capabilities, real-time dashboard, and complete CLI.

## Features

### 🚀 Core Capabilities
- **AI-Powered Predictions**: Generate trading signals with confidence scores
- **Real-Time Dashboard**: Web-based monitoring with live updates via WebSocket
- **Smart Notifications**: Alert system with customizable rules
- **Custom Dashboards**: Build personalized dashboards with widgets
- **Backtesting Engine**: Historical strategy testing and validation
- **Multi-Timeframe Analysis**: HTF and trading timeframe confluence
- **Performance Monitoring**: Real-time system metrics and optimization

### 📊 Dashboard Features
- **5 Core Pages**: Overview, Data, Predictions, Backtests, System Status
- **Real-Time Updates**: WebSocket streaming for live data
- **Custom Widgets**: Metric, Chart, and Table widgets
- **Filter Presets**: Save and reuse filter configurations
- **Multi-Format Export**: CSV, Excel, JSON, PDF reports
- **Performance Optimization**: Caching, lazy loading, query monitoring

### 💻 CLI Commands
- `dgas configure` - Interactive configuration wizard
- `dgas data` - Data management and quality reporting
- `dgas predict` - Generate trading signals
- `dgas report` - Comprehensive report generation
- `dgas scheduler` - Manage prediction scheduler
- `dgas status` - System health monitoring
- `dgas monitor` - Performance tracking
- `dgas analyze` - Market analysis
- `dgas backtest` - Strategy backtesting
- `dgas-dashboard` - Start web dashboard

## Quick Start

### Installation

```bash
# create and activate a uv-managed virtual environment
uv venv
source .venv/bin/activate

# install core dependencies
uv pip install -e .[dev]

# install dashboard dependencies (requires cmake for pyarrow)
# uv pip install -e .[dev,dashboard]

# verify installation
dgas --version
dgas-dashboard --help
```

### Start Using DGAS

```bash
# 1. Configure DGAS (interactive wizard)
dgas configure init

# 2. Check system status
dgas status

# 3. Start the dashboard (requires streamlit)
# dgas-dashboard --port 8501
# Open http://localhost:8501

# 4. Run predictions
dgas predict AAPL MSFT

# 5. Generate a backtest
dgas backtest AAPL --interval 1h --start 2023-01-01 --end 2023-06-30 \
  --initial-capital 100000

# 6. Generate comprehensive reports
dgas report performance --output reports/performance.md

# 7. Start the scheduler (background daemon)
dgas scheduler start

# 8. Monitor system performance
dgas monitor --live
```

## Prerequisites

- Python 3.11 managed via [uv](https://github.com/astral-sh/uv)
- Local PostgreSQL instance (required from Phase 1 onward)
- Valid EODHD ALL-IN-ONE API token

## Database Status

**✅ Production Ready** - Full historical data backfill completed on 2025-11-07

- **518 symbols** from S&P 500 and Nasdaq 100 indices
- **6.5M bars** of historical market data (30m + 1d intervals)
- **~22 months** coverage (Jan 2024 - Nov 2025)
- **99.9% success rate** with excellent data quality
- **Multi-timeframe ready** for HTF trend analysis and trading signals

See [Full Universe Backfill Summary](docs/FULL_UNIVERSE_BACKFILL_SUMMARY.md) for detailed metrics and quality analysis.

## Environment Configuration

1. Duplicate `.env.example` to `.env` and keep it outside version control:

   ```bash
   cp .env.example .env
   ```

2. Populate the following variables:

   - `EODHD_API_TOKEN` - API key issued by EODHD
   - `DGAS_DATABASE_URL` - PostgreSQL connection string (defaults to `postgresql://fireworks_app:changeme_secure_password@localhost:5432/dgas`)
   - `DGAS_DATA_DIR` - Local path used for cached market data and generated reports

3. Additional secrets can be appended as the project evolves. The `.env` file is ignored by Git.

4. Provision the database user and permissions using the SQL snippets in `docs/setup_postgres.md` before running migrations.

## Documentation

### User Guide
- **[User Guide](docs/DASHBOARD_USER_GUIDE.md)** - Complete dashboard usage guide
- **[Feature Tutorials](docs/FEATURE_TUTORIALS.md)** - Step-by-step tutorials for all features
- **[CLI Reference](docs/CLI_USAGE.md)** - Complete command documentation

### API Documentation
- **[API Reference](docs/API_DOCUMENTATION.md)** - Complete API documentation
- **[Dashboard Architecture](docs/PHASE5_WEEK3_DASHBOARD_PLAN.md)** - Dashboard design
- **[Real-time Features](docs/PHASE5_WEEK4_DAYS1-4_COMPLETE.md)** - Week 4 implementation details

### Implementation Reports
- **[Week 3 - Dashboard Foundation](docs/PHASE5_WEEK3_COMPLETION_SUMMARY.md)**
- **[Week 4 - Real-time Features](docs/PHASE5_WEEK4_DAYS1-4_COMPLETE.md)**
- **[Week 5 - Testing & Docs](docs/PHASE5_WEEK5_COMPLETION_SUMMARY.md)**
- **[Final Status Report](docs/PHASE5_FINAL_STATUS_REPORT.md)**

## Dependency Management with uv

- Install runtime and development dependencies:

  ```bash
  uv pip install -e .[dev]
  ```

- Add a new dependency:

  ```bash
  uv pip install <package>
  ```

- Run quality checks:

  ```bash
  ruff check src tests
  ruff format src tests
  mypy src
  pytest
  ```

## Repository Layout

- `implementation_plan.md` - phased delivery roadmap
- `prd/` - product requirement and design documents
- `src/dgas/` - Python package source code (currently scaffolded)
- `tests/` - automated tests
- `.env.example` - template for local configuration
- `docs/pattern_detection_reference.md` - narrative guide to Drummond Geometry pattern detectors
- `docs/drummond_geometry_enhancement_plan.md` - upcoming refinement plan and detailed TODOs

Reference `docs/CLI_USAGE.md` for complete command documentation (analyze, backtest, data-report) and `docs/PHASE3_BACKTESTING_PLAN.md` for the Phase 3 architecture summary.

Further setup and credential guidance will be refined as Phase 0 progresses.

## Upcoming Enhancements

The enhancement plan captured in `docs/drummond_geometry_enhancement_plan.md`
details the next wave of improvements, including:

- Clear documentation of why the PLdot volatility-based envelopes are the recommended default.
- Refinements to Exhaust, C-Wave, and PLdot Refresh pattern detectors with richer confirmation.
- Upgrades to multi-timeframe confluence, trading strategies, and prediction signals.
- Benchmarking and calibration assets to quantify Drummond Geometry's edge versus traditional indicators.

Analyst-facing documentation (see `docs/pattern_detection_reference.md`) will be
kept current as each milestone lands.
