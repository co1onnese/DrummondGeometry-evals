# Drummond Geometry Analysis System (DGAS)

A production-ready, enterprise-grade implementation of the Drummond Geometry Analysis System for algorithmic trading. DGAS provides comprehensive market analysis, signal generation, portfolio backtesting, and real-time monitoring capabilities with a sophisticated multi-timeframe coordination engine.

## Architecture Overview

DGAS is built on a modular, type-safe architecture with clear separation of concerns:

- **Data Layer**: REST API and WebSocket ingestion with tick aggregation, quality validation, and continuous collection service
- **Calculation Engine**: Drummond Geometry indicators (PLdot, envelopes, states, patterns) with multi-timeframe coordination and intelligent caching
- **Backtesting**: Single-symbol and portfolio-level backtesting with shared capital management, signal ranking, and position sizing
- **Prediction System**: Automated signal generation with confidence scoring, calibration tracking, and notification routing
- **Dashboard**: Real-time Streamlit-based monitoring with WebSocket updates and custom widget system
- **Configuration**: Unified YAML/JSON configuration with environment variable expansion and validation

**Technology Stack**: Python 3.11+, PostgreSQL, EODHD API, pandas/numpy, Rich (CLI), Streamlit (dashboard), APScheduler (scheduling), WebSockets (real-time data)

## Core Features

### Market Data Collection

- **24/7 Continuous Collection**: Automated service with dynamic intervals (market hours: 5m, after hours: 15m, weekends: 30m)
- **Dual-Mode Ingestion**: WebSocket for real-time tick data during market hours, REST API for historical gaps and after-hours
- **Tick Aggregation**: Real-time tick-to-bar aggregation via `TickAggregator` for efficient storage
- **Batch Processing**: Configurable batch sizes with rate limiting, retry logic, and exponential backoff
- **Data Quality**: Comprehensive validation (completeness, chronology, duplicates) with quality reporting
- **Exchange Calendar**: Trading day detection and market hours awareness via EODHD exchange API

### Drummond Geometry Calculations

- **PLdot Series**: 3-period moving average of (high+low+close)/3 with forward projection
- **Envelope Bands**: Multiple methods (Drummond 3-period std, ATR-based, percentage-based)
- **Market State Classification**: 5-state model (TREND, CONGESTION_ENTRANCE, CONGESTION_ACTION, CONGESTION_EXIT, REVERSAL)
- **Pattern Detection**: PLdot Push, PLdot Refresh, Exhaust, C-Wave, Congestion Oscillation
- **Multi-Timeframe Coordination**: HTF trend filtering, trading timeframe signals, confluence zone detection
- **Performance Optimizations**: Calculation caching, query result caching, binary search lookups, profiling

### Backtesting Engine

- **Single-Symbol Backtesting**: Historical strategy testing with comprehensive performance metrics
- **Portfolio Backtesting**: Multi-symbol backtesting with shared capital pool, signal ranking, and position management
- **Signal Ranking**: Composite scoring based on signal strength, risk/reward ratio, confluence, trend alignment, volatility
- **Position Management**: Portfolio-level risk management with max positions, portfolio risk limits, confidence-based sizing
- **Strategy Framework**: Extensible `BaseStrategy` interface with strategy registry
- **On-the-Fly Indicators**: HTF data pre-loading and indicator calculation during backtest execution
- **Signal Evaluation**: Built-in tracking of predicted signals vs actual trade outcomes

### Prediction System

- **Signal Generation**: Multi-timeframe analysis with confidence scoring and signal strength calculation
- **Signal Aggregation**: De-duplication, ranking, and filtering with configurable thresholds
- **Automated Scheduling**: APScheduler-based prediction cycles with market hours awareness
- **Notification System**: Discord and console adapters with configurable routing
- **Performance Monitoring**: Latency tracking, throughput metrics, SLA compliance checking
- **Calibration Engine**: Signal accuracy validation with win rate by confidence bucket

### Dashboard System

- **Real-Time Updates**: WebSocket streaming for live data updates
- **Core Pages**: Overview, Data, Predictions, Backtests, System Status, Custom Dashboard
- **Custom Widgets**: Metric, Chart, and Table widgets with layout persistence
- **Filter Presets**: Save and reuse filter configurations
- **Multi-Format Export**: CSV, Excel, JSON, PDF report generation
- **Performance Optimization**: Query result caching, lazy loading, query monitoring

### Configuration System

- **Unified Configuration**: YAML/JSON configuration files with environment variable expansion
- **Multiple Sources**: Config file search paths (`/etc/dgas`, `~/.config/dgas`, `./`)
- **Legacy Compatibility**: `UnifiedSettings` adapter bridges new config system with legacy environment variables
- **Validation**: Comprehensive schema validation with helpful error messages
- **Interactive Setup**: `dgas configure init` wizard for initial configuration

## Installation

### Prerequisites

- Python 3.11+ (managed via [uv](https://github.com/astral-sh/uv))
- PostgreSQL 12+ (local or remote instance)
- Valid EODHD ALL-IN-ONE API token

### Setup

```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install core dependencies
uv pip install -e .[dev]

# Install dashboard dependencies (optional, requires cmake for pyarrow)
uv pip install -e .[dev,dashboard]

# Verify installation
dgas --version
dgas-dashboard --help
```

### Database Setup

1. Provision PostgreSQL database and user (see `docs/setup_postgres.md`)
2. Set environment variables in `.env`:
   ```bash
   EODHD_API_TOKEN=your_token_here
   DGAS_DATABASE_URL=postgresql://user:password@localhost:5432/dgas
   DGAS_DATA_DIR=/path/to/data/directory
   ```
3. Run database migrations:
   ```bash
   uv run python -m dgas.db.migrations
   ```

## Quick Start

### Basic Usage

```bash
# 1. Configure system (interactive wizard)
dgas configure init

# 2. Check system status
dgas status

# 3. Ingest historical data
dgas data ingest AAPL --start-date 2024-01-01 --end-date 2024-12-31 --interval 30min

# 4. Analyze market data
dgas analyze AAPL --htf 1d --trading 30m

# 5. Generate trading signals
dgas predict AAPL MSFT --config config/production.yaml

# 6. Run backtest
dgas backtest AAPL --interval 30m --start 2024-01-01 --end 2024-06-30 \
  --initial-capital 100000 --strategy multi_timeframe

# 7. Start dashboard
dgas-dashboard --port 8501
# Open http://localhost:8501
```

### Production Deployment

```bash
# Start data collection service (24/7)
dgas data-collection start --daemon --config config/production.yaml

# Start prediction scheduler (runs every 15 minutes)
dgas scheduler start --daemon --config config/production.yaml

# Check service status
dgas data-collection status
dgas scheduler status
dgas status
```

## CLI Reference

### Configuration

- `dgas configure init` - Interactive configuration wizard
- `dgas configure show` - Display current configuration
- `dgas configure validate [--config PATH]` - Validate configuration file
- `dgas configure sample [--output PATH] [--template TEMPLATE]` - Generate sample configuration
- `dgas configure edit [--config PATH]` - Edit configuration with $EDITOR

### Data Management

- `dgas data ingest SYMBOL [SYMBOL ...] --start-date DATE [--end-date DATE] [--interval INTERVAL] [--incremental]` - Ingest historical data
- `dgas data list [--interval INTERVAL] [--format FORMAT]` - List stored symbols and data ranges
- `dgas data stats [--interval INTERVAL] [--output PATH] [--format FORMAT]` - Show data quality statistics
- `dgas data clean [--symbol SYMBOL] [--interval INTERVAL] [--older-than DAYS] [--duplicates] [--dry-run]` - Clean duplicate or invalid data

### Data Collection Service

- `dgas data-collection start [--daemon] [--config PATH]` - Start continuous data collection service
- `dgas data-collection stop` - Stop data collection service
- `dgas data-collection status` - Check service status
- `dgas data-collection run-once [--config PATH]` - Execute single collection cycle
- `dgas data-collection stats [--config PATH]` - Show collection statistics

### Analysis

- `dgas analyze SYMBOL [--htf INTERVAL] [--trading INTERVAL] [--lookback BARS] [--save]` - Perform Drummond Geometry analysis

### Prediction

- `dgas predict SYMBOL [SYMBOL ...] [--config PATH] [--output-format FORMAT]` - Generate trading signals

### Backtesting

- `dgas backtest SYMBOL [--interval INTERVAL] [--start DATE] [--end DATE] [--strategy NAME] [--initial-capital AMOUNT]` - Run single-symbol backtest
- Portfolio backtesting available via Python API (see `src/dgas/backtesting/portfolio_engine.py`)

### Reporting

- `dgas report backtest [--run-id ID] [--symbol SYMBOL] [--limit N] [--output PATH]` - Generate backtest performance report
- `dgas report prediction [--days N] [--symbol SYMBOL] [--min-confidence FLOAT] [--output PATH]` - Generate prediction performance report
- `dgas report data-quality [--interval INTERVAL] [--output PATH]` - Generate data quality and coverage report
- `dgas data-report [--interval INTERVAL] [--output PATH]` - Generate data ingestion completeness report

### Scheduler

- `dgas scheduler start [--daemon] [--config PATH]` - Start prediction scheduler
- `dgas scheduler stop` - Stop scheduler
- `dgas scheduler status` - Check scheduler status
- `dgas scheduler run-once [--config PATH]` - Execute single prediction cycle

### Monitoring

- `dgas status [--verbose] [--check-all]` - System health check
- `dgas monitor performance [--lookback HOURS] [--format FORMAT]` - View performance metrics
- `dgas monitor calibration [--days N] [--format FORMAT]` - View signal calibration report
- `dgas monitor signals [--limit N] [--min-confidence FLOAT] [--format FORMAT]` - View recent generated signals
- `dgas monitor dashboard [--refresh SECONDS]` - Live updating dashboard

### Dashboard

- `dgas-dashboard [--port PORT] [--host HOST]` - Start Streamlit dashboard server

## Configuration

DGAS uses a unified configuration system supporting YAML/JSON files with environment variable expansion. Configuration is loaded from multiple search paths:

1. Command-line `--config` argument
2. `./config/production.yaml` (or `development.yaml`)
3. `~/.config/dgas/config.yaml`
4. `/etc/dgas/config.yaml`

### Configuration Structure

```yaml
database:
  url: ${DGAS_DATABASE_URL}
  pool_size: 10
  echo: false

data_collection:
  enabled: true
  use_websocket: true
  websocket_interval: "30m"
  interval_market_hours: "5m"
  interval_after_hours: "15m"
  interval_weekends: "30m"
  batch_size: 50
  requests_per_minute: 80
  max_retries: 3

prediction:
  min_confidence: 0.65
  min_signal_strength: 0.60
  stop_loss_atr_multiplier: 2.0
  target_atr_multiplier: 3.0

scheduler:
  symbols: []  # Empty = load from database
  cron_expression: "*/15 * * * *"  # Every 15 minutes
  timezone: "America/New_York"
  market_hours_only: false

notifications:
  discord:
    enabled: true
    webhook_url: ${DGAS_DISCORD_WEBHOOK_URL}
  console:
    enabled: true

monitoring:
  sla_p95_latency_ms: 200
  sla_error_rate_pct: 1.0
  sla_uptime_pct: 99.5

dashboard:
  port: 8501
  theme: "dark"
  auto_refresh_seconds: 30
```

See `docs/CONFIGURE_COMMAND_GUIDE.md` for detailed configuration documentation.

## Database Status

**✅ Production Ready** - Full historical data backfill completed

- **520+ symbols** from S&P 500 and Nasdaq 100 indices
- **6.6M+ bars** of historical market data (30m + 1d intervals)
- **22+ months** coverage (Jan 2024 - Nov 2025)
- **99.9% success rate** with excellent data quality
- **Multi-timeframe ready** for HTF trend analysis and trading signals

## Architecture Highlights

### Performance Optimizations

- **Connection Pooling**: PostgreSQL connection pool with configurable size
- **Query Caching**: In-memory query result cache with TTL and intelligent invalidation
- **Calculation Caching**: Specialized cache for expensive calculations with pattern-based invalidation
- **Binary Search**: Optimized timestamp lookups in time-series data
- **Parallel Processing**: Support for parallel batch processing in backtesting
- **Memory Management**: Memory monitoring and GC optimization

### Design Patterns

- **Repository Pattern**: Data access abstraction via `data/repository.py`
- **Strategy Pattern**: Extensible strategy framework for backtesting
- **Adapter Pattern**: `UnifiedSettings` bridges new config system with legacy environment variables
- **Factory Pattern**: `IntervalData.from_api_record`, `EODHDConfig.from_settings`
- **Observer Pattern**: Data update listeners for cache invalidation
- **Template Method**: `BaseTradeExecutor` provides shared execution logic

### Type Safety

- Comprehensive type hints (enforced by mypy `--disallow-untyped-defs`)
- Pydantic models for validation (`Settings`, `DGASConfig`, `IntervalData`)
- `Decimal` for prices (avoid float rounding), `datetime` with `timezone.utc`
- Frozen dataclasses for immutable calculation results

## Documentation

### Getting Started

- **[Dashboard User Guide](docs/DASHBOARD_USER_GUIDE.md)** - Complete dashboard usage guide
- **[Feature Tutorials](docs/FEATURE_TUTORIALS.md)** - Step-by-step tutorials for all features
- **[CLI Usage](docs/CLI_USAGE.md)** - Complete command documentation
- **[Configuration Guide](docs/CONFIGURE_COMMAND_GUIDE.md)** - System configuration

### Reference Documentation

- **[API Reference](docs/API_DOCUMENTATION.md)** - Complete API documentation
- **[Drummond Geometry Reference](docs/DRUMMOND_GEOMETRY_REFERENCE.md)** - Methodology and concepts
- **[Pattern Detection Reference](docs/PATTERN_DETECTION_REFERENCE.md)** - Pattern detection guide
- **[Indicator Reference](docs/INDICATOR_REFERENCE.md)** - Technical indicators

### Operations

- **[Operational Runbook](docs/OPERATIONAL_RUNBOOK.md)** - System operations and troubleshooting
- **[Production Quick Reference](docs/PRODUCTION_QUICK_REFERENCE.md)** - Production deployment guide
- **[Production Deployment Complete](docs/PRODUCTION_DEPLOYMENT_COMPLETE.md)** - Deployment status
- **[Database Setup](docs/setup_postgres.md)** - PostgreSQL configuration

## Development

### Code Quality

```bash
# Linting and formatting
ruff check src tests
ruff format src tests

# Type checking
mypy src

# Testing
pytest
```

### Project Structure

```
src/dgas/
├── calculations/     # Drummond Geometry calculations
├── data/            # Data ingestion and quality
├── backtesting/     # Backtesting engine
├── prediction/      # Signal generation and scheduling
├── dashboard/       # Streamlit dashboard
├── cli/            # Command-line interface
├── config/         # Configuration system
├── db/             # Database layer
└── core/           # Core utilities

tests/              # Test suite
docs/               # Documentation
config/             # Configuration files
scripts/            # Utility scripts
```

## License

MIT License

## Contributing

This is a production system. For contributions, please ensure:

1. All tests pass (`pytest`)
2. Type checking passes (`mypy src`)
3. Code is formatted (`ruff format`)
4. Documentation is updated

---

**Version**: 0.1.0  
**Last Updated**: 2025-01-27
