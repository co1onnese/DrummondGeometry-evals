# Phase 5: End-User Interfaces - Implementation Plan

**Status:** 📋 PLANNING
**Timeline:** Weeks 16-22 (estimated 4-6 weeks actual implementation)
**Objective:** Provide comprehensive CLI consolidation and local Streamlit dashboard for visualization and monitoring

---

## 1. Executive Summary

Phase 5 focuses on delivering production-ready end-user interfaces for the DGAS prediction system:

1. **CLI Consolidation** - Clean up, enhance, and complete the command-line interface
2. **Streamlit Dashboard** - Build an interactive local web dashboard for visualization and monitoring
3. **Integration Testing** - Comprehensive end-to-end tests for complete workflows
4. **Documentation** - User guides, tutorials, and reference documentation

**Current State:**
- ✅ Phase 4 CLI commands implemented: `predict`, `scheduler`, `monitor`
- ✅ Existing CLI commands: `analyze`, `backtest`, `data-report`
- ❌ No configuration file support
- ❌ No visual dashboard
- ❌ No integration tests
- ❌ Limited user documentation

---

## 2. Scope & Requirements

### 2.1 CLI Consolidation Goals

**Missing Commands per Original Plan:**
- `dgas configure` - Interactive configuration wizard
- `dgas data` - Data management commands (status, refresh, validate)
- `dgas report` - Generate comprehensive reports (backtesting, performance, calibration)
- `dgas status` - System health and status overview

**Enhancement Needs:**
- Configuration file support (YAML/JSON)
- Environment variable expansion
- Better help text and examples
- Command aliases and shortcuts
- Tab completion support (bash/zsh)
- Logging configuration
- Output format standardization

**Integration Needs:**
- All commands should use consistent patterns
- Shared configuration system
- Consistent error handling
- Unified output formatting

### 2.2 Streamlit Dashboard Requirements

**Core Features:**
1. **Overview Dashboard**
   - System health status
   - Recent signals summary
   - Performance metrics at a glance
   - Market hours indicator
   - Scheduler status

2. **Signals View**
   - Interactive table of recent signals
   - Filtering by symbol, type, confidence, outcome
   - Signal details modal/sidebar
   - Charts showing entry/target/stop levels
   - Historical signal performance

3. **Performance Analytics**
   - Latency charts (P50/P95/P99 over time)
   - Throughput metrics
   - Error rate trends
   - SLA compliance history
   - System resource usage

4. **Calibration Dashboard**
   - Win rate by confidence bucket
   - P&L distribution
   - Hit rate analysis (target vs stop)
   - Performance by signal type
   - Time-series calibration trends

5. **Charts & Visualization**
   - Price charts with Drummond Geometry overlays
   - Signal entry/exit markers
   - Multi-timeframe view
   - Pattern highlighting
   - Confluence zone visualization

6. **Configuration & Control**
   - Scheduler start/stop controls
   - Configuration editor
   - Watchlist management
   - Notification settings
   - System logs viewer

### 2.3 Integration Testing Requirements

**Test Coverage:**
- End-to-end prediction workflow
- Scheduler lifecycle (start, run, stop)
- Database persistence and retrieval
- Notification delivery
- Configuration loading and validation
- Error scenarios and recovery
- Multi-user concurrent access (dashboard)

### 2.4 Documentation Requirements

**User Documentation:**
- Getting Started guide
- Installation instructions
- CLI command reference
- Dashboard user guide
- Configuration reference
- Troubleshooting guide
- FAQ

**Developer Documentation:**
- Architecture overview
- API reference
- Extension guide
- Contributing guidelines

---

## 3. Implementation Plan

### Week 1: CLI Configuration System (Days 1-5)

#### Day 1-2: Configuration Framework
**Goal:** Implement YAML/JSON configuration file support with environment variable expansion

**Tasks:**
1. Create `src/dgas/config/` module structure
2. Implement `ConfigLoader` class
   - YAML and JSON parsing
   - Environment variable expansion (`${VAR_NAME}`)
   - Validation using Pydantic models
   - Merge strategy (file → env vars → CLI args)
3. Define configuration schema
   - Scheduler configuration
   - Database configuration
   - Notification configuration
   - Watchlist configuration
   - Monitoring thresholds
4. Add configuration search paths
   - `./dgas.yaml` (current directory)
   - `~/.config/dgas/config.yaml` (user config)
   - `/etc/dgas/config.yaml` (system config)

**Files to Create:**
- `src/dgas/config/__init__.py`
- `src/dgas/config/loader.py`
- `src/dgas/config/schema.py`
- `src/dgas/config/validators.py`
- `tests/config/test_loader.py`
- `tests/config/test_schema.py`

**Success Criteria:**
- Config files can be loaded from standard locations
- Environment variables are expanded correctly
- Invalid configs are caught with helpful error messages
- CLI args override config file values
- 20+ unit tests passing

#### Day 3-4: `dgas configure` Command
**Goal:** Interactive configuration wizard

**Tasks:**
1. Implement interactive prompts using `questionary` or `rich.prompt`
2. Validate inputs in real-time
3. Generate config file with comments
4. Support existing config modification
5. Configuration templates (minimal, standard, advanced)

**Features:**
- Interactive wizard mode
- Direct edit mode with validation
- Show current configuration
- Generate sample configuration
- Validate existing configuration

**Commands:**
```bash
dgas configure init          # Interactive wizard
dgas configure edit          # Edit with $EDITOR
dgas configure show          # Display current config
dgas configure validate      # Validate config file
dgas configure sample        # Generate sample config
```

**Success Criteria:**
- Wizard creates valid config files
- All configuration options accessible
- Config validation catches errors
- Generated configs have helpful comments
- 15+ unit tests passing

#### Day 5: CLI Enhancement & Cleanup
**Goal:** Improve existing CLI commands with config support

**Tasks:**
1. Update all commands to use ConfigLoader
2. Add `--config` flag to all commands
3. Standardize output formatting
4. Add command examples to help text
5. Implement command aliases
6. Add shell completion scripts

**Enhancements:**
- Consistent `--format` option (table/json/yaml)
- Consistent `--verbose` and `--quiet` flags
- Progress bars for long operations
- Better error messages with suggestions
- Color-coded output (errors, warnings, success)

**Success Criteria:**
- All commands support config files
- Help text is comprehensive
- Output is consistent across commands
- Completion scripts work in bash/zsh
- 10+ tests for config integration

---

### Week 2: Missing CLI Commands (Days 6-10)

#### Day 6-7: `dgas data` Command
**Goal:** Data management and status reporting

**Subcommands:**
```bash
dgas data status [SYMBOLS...]      # Show data completeness
dgas data refresh [SYMBOLS...]     # Force data refresh
dgas data validate [SYMBOLS...]    # Validate data quality
dgas data gaps [SYMBOLS...]        # Find data gaps
dgas data summary                  # Overall data summary
```

**Features:**
- Show data completeness percentages
- Identify missing bars/gaps
- Validate OHLCV data quality (no nulls, valid ranges)
- Force refresh for specific symbols
- Summary statistics (total bars, date ranges)

**Implementation:**
- Create `src/dgas/cli/data.py`
- Integrate with existing data fetcher
- Rich table output with color coding
- JSON output for automation

**Success Criteria:**
- All subcommands functional
- Accurate gap detection
- Helpful error messages
- 15+ unit tests passing

#### Day 8-9: `dgas report` Command
**Goal:** Generate comprehensive reports

**Subcommands:**
```bash
dgas report performance [OPTIONS]  # Performance report
dgas report calibration [OPTIONS]  # Calibration report
dgas report backtest [OPTIONS]     # Backtest report
dgas report signals [OPTIONS]      # Signals report
dgas report system                 # System health report
```

**Features:**
- Multiple output formats (Markdown, HTML, PDF, JSON)
- Date range filtering
- Symbol filtering
- Customizable sections
- Email delivery option
- Scheduled reports

**Implementation:**
- Create `src/dgas/cli/report.py`
- Use Jinja2 templates for reports
- Generate charts with matplotlib/plotly
- Export to various formats

**Success Criteria:**
- All report types generate correctly
- Reports include relevant visualizations
- Multiple output formats work
- 20+ unit tests passing

#### Day 10: `dgas status` Command
**Goal:** Unified system status overview

**Features:**
- Scheduler status (running/stopped)
- Database connectivity
- Last prediction run info
- Recent signal count
- Performance metrics summary
- SLA compliance status
- Disk space usage
- Error summary

**Implementation:**
```bash
dgas status                  # Full status
dgas status --quick          # Quick check only
dgas status --watch          # Live monitoring mode
dgas status --format json    # JSON output
```

**Success Criteria:**
- Comprehensive status overview
- Quick health check mode
- Live monitoring mode
- 10+ unit tests passing

---

### Week 3: Streamlit Dashboard - Foundation (Days 11-15)

#### Day 11-12: Dashboard Framework Setup

**Tasks:**
1. Add Streamlit to dependencies
2. Create dashboard entry point
3. Set up multi-page app structure
4. Implement authentication (optional)
5. Create shared utilities

**Project Structure:**
```
src/dgas/dashboard/
├── __init__.py
├── app.py                    # Main entry point
├── pages/
│   ├── 01_overview.py
│   ├── 02_signals.py
│   ├── 03_performance.py
│   ├── 04_calibration.py
│   ├── 05_charts.py
│   └── 06_settings.py
├── components/
│   ├── __init__.py
│   ├── metrics.py           # Metric cards
│   ├── tables.py            # Data tables
│   ├── charts.py            # Chart components
│   └── controls.py          # Control widgets
└── utils/
    ├── __init__.py
    ├── data.py              # Data loading
    ├── cache.py             # Caching utilities
    └── formatters.py        # Display formatting
```

**Configuration:**
- Port configuration (default: 8501)
- Theme customization
- Authentication settings
- Refresh intervals
- Default date ranges

**Launch Command:**
```bash
dgas dashboard             # Start dashboard
dgas dashboard --port 8080 # Custom port
dgas dashboard --no-browser # Don't open browser
```

**Success Criteria:**
- Dashboard launches successfully
- Multi-page navigation works
- Basic layout established
- Theme applied
- CLI command functional

#### Day 13: Overview Page
**Goal:** System health and quick metrics

**Components:**
1. **Header**
   - System title and logo
   - Current time
   - Market hours indicator (green/red)
   - Scheduler status badge

2. **Key Metrics Row**
   - Total signals today
   - Win rate (last 7 days)
   - P95 latency
   - SLA compliance

3. **Recent Signals Table**
   - Last 10 signals
   - Symbol, type, confidence, timestamp
   - Outcome with color coding
   - Click to expand details

4. **Activity Timeline**
   - Last 24 hours of prediction runs
   - Success/failure indicators
   - Execution times

5. **Alerts Section**
   - SLA violations
   - High error rates
   - System warnings

**Implementation:**
- Use st.columns for layout
- st.metric for KPIs
- st.dataframe for signals table
- st.line_chart for timeline
- Auto-refresh every 30 seconds

**Success Criteria:**
- All components render correctly
- Data loads from database
- Auto-refresh works
- Responsive layout

#### Day 14: Signals Page
**Goal:** Detailed signal exploration

**Components:**
1. **Filters Sidebar**
   - Date range picker
   - Symbol multi-select
   - Signal type filter
   - Confidence slider
   - Outcome filter

2. **Signals Table**
   - Sortable columns
   - Pagination
   - Row selection
   - Export to CSV

3. **Signal Details Panel**
   - Price chart with entry/target/stop
   - Signal metadata
   - Pattern context
   - Outcome analysis (if completed)

4. **Summary Statistics**
   - Total signals
   - Average confidence
   - Win/loss breakdown
   - P&L summary

**Implementation:**
- Use st.sidebar for filters
- st.dataframe with column_config
- Plotly for interactive charts
- Session state for row selection

**Success Criteria:**
- Filters work correctly
- Charts display price levels
- Export functionality works
- Details panel shows on selection

#### Day 15: Performance Page
**Goal:** System performance analytics

**Components:**
1. **Time Range Selector**
   - Last 24h / 7d / 30d / Custom

2. **Latency Charts**
   - Line chart: P50/P95/P99 over time
   - Bar chart: Latency breakdown (fetch/calc/signal/notify)
   - Histogram: Latency distribution

3. **Throughput Metrics**
   - Symbols per second trend
   - Total symbols processed
   - Signals generated over time

4. **Error Analytics**
   - Error rate trend line
   - Error types breakdown
   - Recent error log

5. **SLA Dashboard**
   - SLA compliance percentage
   - Violations timeline
   - Target vs actual comparison

**Implementation:**
- Plotly for interactive charts
- st.line_chart for trends
- st.area_chart for distributions
- st.expander for error details

**Success Criteria:**
- All charts render correctly
- Time range filtering works
- Data aggregation accurate
- Performance is acceptable

---

### Week 4: Streamlit Dashboard - Advanced Features (Days 16-20)

#### Day 16: Calibration Page
**Goal:** Signal accuracy analytics

**Components:**
1. **Overall Metrics**
   - Win rate gauge
   - Average P&L
   - Target hit rate
   - Stop hit rate

2. **Confidence Analysis**
   - Win rate by confidence bucket (bar chart)
   - P&L by confidence bucket
   - Signal count by bucket

3. **Signal Type Comparison**
   - LONG vs SHORT performance
   - Side-by-side metrics
   - Win rate comparison

4. **Time Series Analysis**
   - Win rate over time
   - P&L trend
   - Hit rate trends

5. **Detailed Statistics**
   - Outcome distribution (pie chart)
   - Average hold time
   - Risk/reward analysis

**Implementation:**
- Use plotly.graph_objects for gauges
- st.columns for metric comparison
- Animated transitions
- Color coding (green/red)

**Success Criteria:**
- All calibration metrics accurate
- Charts are visually appealing
- Analysis is actionable
- Performance is good

#### Day 17-18: Charts Page
**Goal:** Price charts with Drummond Geometry overlays

**Components:**
1. **Symbol Selector**
   - Search/autocomplete
   - Recent symbols quick access
   - Watchlist shortcuts

2. **Timeframe Controls**
   - HTF selector (4h, 1d)
   - Trading TF selector (15m, 30m, 1h)
   - Date range

3. **Interactive Price Chart**
   - Candlestick chart
   - Drummond lines (PLdot, envelopes)
   - Confluence zones highlighted
   - Pattern markers
   - Signal entry/exit markers

4. **Multi-Timeframe View**
   - Side-by-side HTF and Trading TF
   - Alignment visualization
   - Linked cursors

5. **Indicator Panel**
   - Current market state
   - Alignment score
   - Active patterns
   - Recent signals

**Implementation:**
- Use plotly for candlestick charts
- Custom annotations for Drummond lines
- Shapes for confluence zones
- Markers for signals
- Synchronized charts

**Technical Challenges:**
- Loading large OHLCV datasets efficiently
- Rendering complex overlays
- Real-time updates
- Performance optimization

**Success Criteria:**
- Charts render correctly
- Drummond geometry overlays accurate
- Interactive features work
- Acceptable performance (<2s load)

#### Day 19: Settings Page
**Goal:** Dashboard configuration and controls

**Components:**
1. **Scheduler Controls**
   - Start/stop buttons
   - Current status
   - Configuration display
   - Logs viewer

2. **Watchlist Management**
   - Add/remove symbols
   - Upload from file
   - Default watchlist
   - Symbol validation

3. **Notification Settings**
   - Discord webhook config
   - Console output toggle
   - Alert thresholds

4. **Dashboard Preferences**
   - Theme selection
   - Default views
   - Refresh intervals
   - Chart preferences

5. **System Logs**
   - Real-time log viewer
   - Filter by level
   - Search functionality
   - Export logs

**Implementation:**
- st.button for controls
- st.text_area for config editing
- st.file_uploader for watchlist
- WebSocket for real-time logs (optional)

**Success Criteria:**
- Scheduler controls work
- Configuration changes persist
- Logs display correctly
- Settings save properly

#### Day 20: Dashboard Polish & Testing

**Tasks:**
1. **UI/UX Refinement**
   - Consistent styling
   - Loading states
   - Error states
   - Empty states
   - Tooltips and help text

2. **Performance Optimization**
   - Query optimization
   - Caching strategy (@st.cache_data)
   - Lazy loading
   - Pagination
   - Data sampling for large datasets

3. **Responsive Design**
   - Mobile-friendly layouts
   - Sidebar behavior
   - Chart responsiveness

4. **Testing**
   - Manual testing all pages
   - Edge case testing
   - Performance testing
   - Cross-browser testing (Chrome, Firefox, Safari)

**Success Criteria:**
- Dashboard is polished
- No major bugs
- Good performance
- Responsive on different screens

---

### Week 5: Integration Testing & Documentation (Days 21-25)

#### Day 21-22: Integration Tests

**Test Scenarios:**

1. **End-to-End Prediction Workflow**
   ```python
   # Test: Complete prediction cycle
   - Start scheduler
   - Wait for prediction run
   - Verify signals generated
   - Check database persistence
   - Verify notifications sent
   - Stop scheduler
   ```

2. **Configuration Loading**
   ```python
   # Test: Config file cascade
   - Create system config
   - Create user config
   - Pass CLI args
   - Verify correct precedence
   - Test env var expansion
   ```

3. **Multi-Command Workflow**
   ```python
   # Test: Typical user workflow
   - dgas configure init
   - dgas data status
   - dgas scheduler start
   - dgas predict AAPL
   - dgas monitor performance
   - dgas report calibration
   - dgas scheduler stop
   ```

4. **Error Recovery**
   ```python
   # Test: System resilience
   - Database connection failure
   - API rate limit hit
   - Invalid configuration
   - Scheduler crash and restart
   - Notification failure
   ```

5. **Dashboard Integration**
   ```python
   # Test: Dashboard with real data
   - Launch dashboard
   - Navigate all pages
   - Trigger scheduler actions
   - Verify data updates
   - Test filters and controls
   ```

**Test Framework:**
- Use pytest for integration tests
- Docker Compose for isolated environment
- Fixtures for test data
- Cleanup after tests
- Parallel test execution

**Files:**
- `tests/integration/test_prediction_workflow.py`
- `tests/integration/test_configuration.py`
- `tests/integration/test_cli_commands.py`
- `tests/integration/test_error_recovery.py`
- `tests/integration/test_dashboard.py`
- `tests/integration/conftest.py` (shared fixtures)
- `tests/integration/docker-compose.yml`

**Success Criteria:**
- 30+ integration tests passing
- All critical workflows tested
- Error scenarios covered
- Dashboard tested end-to-end

#### Day 23-24: User Documentation

**Documentation Structure:**
```
docs/user/
├── getting-started.md
│   ├── Installation
│   ├── Quick Start
│   ├── First Prediction
│   └── Configuration
├── cli-reference.md
│   ├── dgas configure
│   ├── dgas data
│   ├── dgas predict
│   ├── dgas scheduler
│   ├── dgas monitor
│   ├── dgas report
│   ├── dgas status
│   ├── dgas analyze
│   ├── dgas backtest
│   └── dgas dashboard
├── dashboard-guide.md
│   ├── Overview Page
│   ├── Signals Page
│   ├── Performance Page
│   ├── Calibration Page
│   ├── Charts Page
│   └── Settings Page
├── configuration-reference.md
│   ├── Configuration File Format
│   ├── Scheduler Settings
│   ├── Database Settings
│   ├── Notification Settings
│   ├── Watchlist Settings
│   └── Environment Variables
├── troubleshooting.md
│   ├── Common Issues
│   ├── Error Messages
│   ├── Performance Problems
│   └── Getting Help
└── faq.md
```

**Content Requirements:**
- Clear, beginner-friendly language
- Code examples for all commands
- Screenshots of dashboard
- Configuration examples
- Common use cases
- Troubleshooting steps

**Success Criteria:**
- All commands documented
- Examples tested and working
- Screenshots current
- Easy to follow for new users

#### Day 25: Developer Documentation

**Documentation Structure:**
```
docs/developer/
├── architecture.md
│   ├── System Overview
│   ├── Component Diagram
│   ├── Data Flow
│   └── Technology Stack
├── api-reference.md
│   ├── Core Modules
│   ├── CLI Commands
│   ├── Dashboard Components
│   └── Utilities
├── extension-guide.md
│   ├── Adding CLI Commands
│   ├── Creating Dashboard Pages
│   ├── Custom Notifications
│   └── Strategy Plugins
├── contributing.md
│   ├── Development Setup
│   ├── Code Style
│   ├── Testing Guidelines
│   └── Pull Request Process
└── deployment.md
    ├── Production Setup
    ├── Environment Variables
    ├── Monitoring
    └── Backup/Recovery
```

**Success Criteria:**
- Architecture is well-documented
- API reference complete
- Extension examples provided
- Contribution guidelines clear

---

## 4. Technical Specifications

### 4.1 Configuration System

**Config File Format (YAML):**
```yaml
# ~/.config/dgas/config.yaml

# Database Configuration
database:
  url: "${DATABASE_URL}"  # From environment
  pool_size: 5
  echo: false

# Scheduler Configuration
scheduler:
  symbols:
    - AAPL
    - MSFT
    - GOOGL
  cron_expression: "0 9,15 * * 1-5"
  timezone: "America/New_York"
  market_hours_only: true

# Prediction Engine
prediction:
  min_confidence: 0.6
  min_signal_strength: 0.5
  stop_loss_atr_multiplier: 1.5
  target_atr_multiplier: 2.5

# Notifications
notifications:
  discord:
    enabled: true
    webhook_url: "${DISCORD_WEBHOOK_URL}"
  console:
    enabled: true

# Monitoring
monitoring:
  sla_p95_latency_ms: 60000
  sla_error_rate_pct: 1.0
  sla_uptime_pct: 99.0

# Dashboard
dashboard:
  port: 8501
  theme: "light"
  auto_refresh_seconds: 30
```

**Pydantic Schema:**
```python
from pydantic import BaseModel, Field
from typing import Optional, List

class DatabaseConfig(BaseModel):
    url: str
    pool_size: int = 5
    echo: bool = False

class SchedulerConfig(BaseModel):
    symbols: List[str]
    cron_expression: str
    timezone: str = "America/New_York"
    market_hours_only: bool = True

class PredictionConfig(BaseModel):
    min_confidence: float = Field(ge=0.0, le=1.0, default=0.6)
    min_signal_strength: float = Field(ge=0.0, le=1.0, default=0.5)
    stop_loss_atr_multiplier: float = 1.5
    target_atr_multiplier: float = 2.5

class NotificationConfig(BaseModel):
    discord: Optional[DiscordConfig] = None
    console: Optional[ConsoleConfig] = None

class MonitoringConfig(BaseModel):
    sla_p95_latency_ms: int = 60000
    sla_error_rate_pct: float = 1.0
    sla_uptime_pct: float = 99.0

class DashboardConfig(BaseModel):
    port: int = 8501
    theme: str = "light"
    auto_refresh_seconds: int = 30

class DGASConfig(BaseModel):
    database: DatabaseConfig
    scheduler: SchedulerConfig
    prediction: PredictionConfig
    notifications: NotificationConfig
    monitoring: MonitoringConfig
    dashboard: DashboardConfig
```

### 4.2 Dashboard Technology Stack

**Core Framework:**
- Streamlit 1.30+ for web framework
- Plotly 5.18+ for interactive charts
- Pandas 2.2+ for data manipulation
- SQLAlchemy 2.0+ for database queries

**Additional Libraries:**
- streamlit-aggrid for advanced tables
- streamlit-extras for custom components
- plotly.express for quick charts
- matplotlib for static charts (optional)

**Caching Strategy:**
```python
import streamlit as st

@st.cache_data(ttl=300)  # 5 minute cache
def load_recent_signals(limit: int = 20):
    """Load recent signals from database."""
    # Query database
    return signals

@st.cache_resource
def get_database_connection():
    """Get cached database connection."""
    return create_engine(...)
```

**Session State Management:**
```python
# Initialize session state
if 'selected_symbol' not in st.session_state:
    st.session_state.selected_symbol = None

if 'date_range' not in st.session_state:
    st.session_state.date_range = (
        datetime.now() - timedelta(days=7),
        datetime.now()
    )
```

### 4.3 Performance Targets

**CLI Performance:**
- Command startup time: <500ms
- Config file loading: <100ms
- Simple queries (status): <1s
- Complex reports: <10s
- Tab completion: <50ms

**Dashboard Performance:**
- Initial page load: <3s
- Page navigation: <1s
- Chart rendering: <2s
- Data refresh: <1s
- Auto-refresh overhead: <500ms

**Memory Usage:**
- CLI: <100MB
- Dashboard: <500MB
- Database connections: <50MB

---

## 5. Dependencies

### 5.1 New Dependencies

**Required:**
```toml
[project.dependencies]
# ... existing dependencies ...
"streamlit>=1.30",
"plotly>=5.18",
"pyyaml>=6.0",
"jinja2>=3.1",
"questionary>=2.0",  # For interactive prompts
```

**Optional:**
```toml
[project.optional-dependencies]
dashboard = [
  "streamlit-aggrid>=0.3",
  "streamlit-extras>=0.3",
  "watchdog>=3.0",  # For file watching
]
```

### 5.2 Upstream Dependencies

**Must Work With:**
- ✅ PredictionEngine
- ✅ PredictionPersistence
- ✅ PredictionScheduler
- ✅ PerformanceTracker
- ✅ CalibrationEngine
- ✅ NotificationRouter
- ✅ Settings

**Integration Points:**
- Database (PostgreSQL)
- EODHD API (data fetcher)
- File system (config files)
- Process management (scheduler daemon)

---

## 6. Risks & Mitigation

### 6.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Streamlit performance with large datasets** | High | Medium | Implement pagination, sampling, caching |
| **Chart rendering complexity** | Medium | Medium | Use Plotly efficiently, limit data points, lazy loading |
| **Configuration migration** | Medium | Low | Provide migration tool, backward compatibility |
| **Dashboard resource usage** | Medium | Medium | Monitor memory, optimize queries, implement limits |
| **Browser compatibility** | Low | Low | Test major browsers, use standard features |

### 6.2 UX Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Complex configuration** | Medium | Medium | Interactive wizard, templates, validation |
| **Dashboard learning curve** | Medium | Low | Clear documentation, tooltips, tutorials |
| **Information overload** | Medium | Medium | Progressive disclosure, sensible defaults |
| **Mobile usability** | Low | Medium | Responsive design, test on tablets |

---

## 7. Success Criteria

### 7.1 CLI Consolidation
- [x] All planned commands implemented
- [x] Configuration file support working
- [x] Help text comprehensive and accurate
- [x] Tab completion functional
- [x] Integration tests passing (30+)
- [x] User documentation complete

### 7.2 Streamlit Dashboard
- [x] All 6 pages functional
- [x] Charts render correctly
- [x] Data loading performant
- [x] Auto-refresh working
- [x] Responsive design
- [x] No critical bugs

### 7.3 Testing & Quality
- [x] 30+ integration tests passing
- [x] Dashboard manually tested
- [x] Performance targets met
- [x] Error handling robust
- [x] Logging comprehensive

### 7.4 Documentation
- [x] User guide complete
- [x] CLI reference accurate
- [x] Dashboard guide with screenshots
- [x] Troubleshooting guide helpful
- [x] Developer docs complete

### 7.5 Overall Phase 5
- [x] System is production-ready
- [x] User experience is excellent
- [x] Documentation is comprehensive
- [x] All integration tests pass
- [x] Performance targets achieved

---

## 8. Deferred Items (Post-Phase 5)

### 8.1 Advanced Dashboard Features
- Real-time WebSocket updates
- User authentication and multi-user support
- Advanced charting (heatmaps, 3D visualizations)
- Custom dashboard layouts
- Export all data to Excel
- PDF report generation from dashboard
- Mobile app (React Native)

### 8.2 CLI Enhancements
- Plugin system for custom commands
- Scripting language (DSL) for automation
- Remote CLI (control scheduler on remote server)
- Advanced completion (fish shell, PowerShell)
- Command history and favorites

### 8.3 Integration & Deployment
- Docker images for easy deployment
- Kubernetes manifests
- CI/CD pipeline
- Automated testing in CI
- Performance benchmarking suite

---

## 9. Timeline Summary

**Week 1 (Days 1-5):** CLI Configuration System
- Day 1-2: Config framework
- Day 3-4: `configure` command
- Day 5: CLI enhancements

**Week 2 (Days 6-10):** Missing CLI Commands
- Day 6-7: `data` command
- Day 8-9: `report` command
- Day 10: `status` command

**Week 3 (Days 11-15):** Dashboard Foundation
- Day 11-12: Framework setup
- Day 13: Overview page
- Day 14: Signals page
- Day 15: Performance page

**Week 4 (Days 16-20):** Dashboard Advanced
- Day 16: Calibration page
- Day 17-18: Charts page
- Day 19: Settings page
- Day 20: Polish & testing

**Week 5 (Days 21-25):** Testing & Docs
- Day 21-22: Integration tests
- Day 23-24: User documentation
- Day 25: Developer documentation

**Total Estimated Effort:** 25 days (5 weeks)

---

## 10. Questions for Review

Before proceeding with implementation, please consider:

1. **Configuration Approach**
   - Is YAML the preferred format, or should we support TOML/JSON equally?
   - Should we support multiple config files with merging?
   - Environment variable naming convention?

2. **Dashboard Scope**
   - Are all 6 pages needed initially, or can we start with 3-4?
   - Should we include editing capabilities (watchlist, config) or read-only?
   - Local-only or should we plan for remote deployment?

3. **CLI Commands**
   - Priority order for missing commands (`data`, `report`, `status`)?
   - Should `configure` be fully interactive or also support direct editing?
   - Any commands to deprecate or rename?

4. **Testing Strategy**
   - Integration test environment: Docker Compose or local DB?
   - Dashboard testing: Manual only or automated (Selenium/Playwright)?
   - Performance benchmarking needed?

5. **Documentation**
   - Video tutorials needed?
   - API documentation format (Sphinx, MkDocs)?
   - Translation to other languages?

---

**Ready for Approval:**
This plan provides a comprehensive roadmap for Phase 5 implementation. Upon approval, I will proceed with Week 1 Day 1-2: Configuration Framework implementation.
