# Phase 5 Week 3: Streamlit Dashboard Foundation - Detailed Plan

## Overview

Create a comprehensive local Streamlit dashboard showing charts, signals, performance metrics, and system status. The dashboard will provide a web-based UI for the DGAS system with real-time monitoring and data visualization.

## Architecture Design

### 1. Project Structure

```
src/dgas/dashboard/
├── __init__.py
├── app.py                  # Main Streamlit application
├── pages/
│   ├── __init__.py
│   ├── 01_Overview.py      # System overview
│   ├── 02_Data.py          # Data management
│   ├── 03_Predictions.py   # Prediction signals
│   ├── 04_Backtests.py     # Backtest performance
│   └── 05_System_Status.py # System health
├── components/
│   ├── __init__.py
│   ├── charts.py           # Chart utilities
│   ├── database.py         # Database queries
│   └── utils.py            # Helper functions
└── config/
    ├── __init__.py
    └── dashboard_config.py # Dashboard-specific config
```

### 2. Technology Stack

- **Framework**: Streamlit (web UI)
- **Charts**: Plotly (interactive charts)
- **Database**: psycopg (PostgreSQL)
- **Configuration**: Pydantic (unified settings)
- **Data Processing**: pandas, numpy
- **Styling**: Streamlit themes, custom CSS

### 3. Key Features

#### Universal Features (All Pages):
- **Config file support**: Load settings from YAML
- **Real-time updates**: Auto-refresh capability
- **Data caching**: Cache database queries
- **Error handling**: User-friendly error messages
- **Responsive design**: Mobile-friendly layouts
- **Export**: Download data/charts

## Page-by-Page Implementation Plan

### Page 1: Overview (Day 1-2)

**Purpose**: System summary and key metrics at a glance

**Components**:
1. **System Health Panel**
   - Database status
   - Total symbols
   - Data coverage
   - Prediction runs (24h)
   - Signals generated (24h)

2. **Quick Stats Cards**
   - Latest backtest return
   - Best performing symbol
   - Scheduler status
   - Uptime

3. **Mini Charts**
   - Predictions over time (line chart)
   - Signal distribution (pie chart)
   - Data freshness (bar chart)

4. **Recent Activity Feed**
   - Latest predictions
   - Recent backtests
   - System events

**Database Queries**:
- Total symbols count
- Data coverage by interval
- Prediction runs last 24h
- Signal counts by type
- Recent backtest results

### Page 2: Data (Day 1-2)

**Purpose**: Data management and visualization

**Components**:
1. **Data Inventory Table**
   - All symbols with data ranges
   - Bar counts per symbol
   - Coverage percentage
   - Last updated timestamp
   - Search and filter

2. **Data Coverage Charts**
   - Coverage heatmap by symbol/date
   - Missing data visualization
   - Data distribution by interval

3. **Data Quality Metrics**
   - Duplicate bars
   - Gap analysis
   - Outlier detection

4. **Data Management Actions**
   - Trigger ingestion (via CLI integration)
   - Clean old data
   - Export data

**Database Queries**:
- Market symbols with data stats
- Data coverage by date range
- Quality metrics per symbol
- Missing data estimation

### Page 3: Predictions (Day 3-4)

**Purpose**: Prediction signals visualization and analysis

**Components**:
1. **Signal Timeline**
   - Interactive timeline of all signals
   - Filter by symbol, date, confidence
   - Zoom and pan capabilities

2. **Signal Details Table**
   - Symbol, type, confidence
   - Entry, target, stop prices
   - Risk/reward ratio
   - Pattern context

3. **Performance Charts**
   - Confidence distribution (histogram)
   - Signal success rate (bar chart)
   - Average returns by symbol (bar chart)
   - Signals over time (area chart)

4. **Symbol Analysis**
   - Per-symbol signal statistics
   - Best performing patterns
   - Win rate trends

**Database Queries**:
- Prediction signals with run info
- Signal performance metrics
- Symbol-wise statistics
- Time-series data for charts

### Page 4: Backtests (Day 3-4)

**Purpose**: Backtest performance visualization

**Components**:
1. **Performance Summary Cards**
   - Total return
   - Sharpe ratio
   - Max drawdown
   - Win rate
   - Total trades

2. **Equity Curve Chart**
   - Interactive line chart
   - Benchmark comparison
   - Drawdown periods highlighted
   - Trade markers

3. **Trade Analysis**
   - Win/loss distribution
   - Average trade duration
   - Profit factor
   - Best/worst trades table

4. **Performance Metrics Table**
   - All backtests with metrics
   - Sortable by any column
   - Filter by symbol, strategy
   - Export capability

**Database Queries**:
- Backtest results with symbol names
- Trade details
- Performance metrics comparison
- Time-series equity data

### Page 5: System Status (Day 5)

**Purpose**: Real-time system monitoring

**Components**:
1. **System Health Dashboard**
   - Connection status indicators
   - CPU/memory usage (if available)
   - Database size and growth
   - Last successful prediction

2. **Scheduler Monitoring**
   - Daemon status (running/stopped)
   - Next scheduled run
   - Run history
   - Error logs

3. **Performance Metrics**
   - Prediction latency
   - API response times
   - Database query performance
   - Error rates

4. **Configuration View**
   - Current configuration
   - Environment variables
   - Database settings
   - Edit config (opens editor)

**Database Queries**:
- Database statistics
- Prediction run history
- System metrics
- Configuration settings

## Technical Implementation Details

### 1. Database Connection

```python
# components/database.py
@st.cache_resource
def get_db_connection():
    """Get cached database connection."""
    return get_connection()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def execute_query(query, params):
    """Execute query with caching."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
```

### 2. Chart Utilities

```python
# components/charts.py
def create_line_chart(df, x_col, y_col, title):
    """Create a Plotly line chart."""
    fig = px.line(df, x=x_col, y=y_col, title=title)
    return st.plotly_chart(fig, use_container_width=True)

def create_signal_timeline(signals_df):
    """Create interactive signal timeline."""
    fig = px.scatter(
        signals_df,
        x='timestamp',
        y='symbol',
        color='confidence',
        size='signal_strength',
        title='Signal Timeline'
    )
    return fig
```

### 3. Configuration Integration

```python
# Load unified settings
from dgas.config import load_settings

@st.cache_resource
def load_dashboard_config(config_file=None):
    """Load configuration for dashboard."""
    return load_settings(config_file=config_file)

# Use in pages
settings = load_dashboard_config()
symbols = settings.scheduler_symbols
```

### 4. Real-Time Updates

```python
# Auto-refresh every 60 seconds
st_autorefresh = st.experimental_rerun  # For older versions
# OR
st.sidebar.checkbox("Auto-refresh", value=True, key="auto_refresh")
if st.session_state.auto_refresh:
    st.experimental_set_query_params(ts=int(time.time()))
```

### 5. Navigation

```python
# Sidebar navigation
st.sidebar.title("DGAS Dashboard")
page = st.sidebar.selectbox(
    "Navigate",
    ["Overview", "Data", "Predictions", "Backtests", "System Status"]
)

# Show page based on selection
if page == "Overview":
    overview_page()
elif page == "Data":
    data_page()
# etc.
```

## Development Phases

### Phase 1: Setup (Day 1)
1. Create project structure
2. Add dependencies to pyproject.toml
3. Create base app.py with navigation
4. Set up database utilities

### Phase 2: Core Pages (Day 1-2)
1. Implement Overview page
2. Implement Data page
3. Add basic charts
4. Test database integration

### Phase 3: Advanced Pages (Day 3-4)
1. Implement Predictions page
2. Implement Backtests page
3. Add interactive charts
4. Implement caching

### Phase 4: System Monitoring (Day 5)
1. Implement System Status page
2. Add real-time monitoring
3. Add configuration support
4. Final testing and documentation

## Key Decisions

### 1. Chart Library
**Choice**: Plotly
**Reason**:
- Interactive (zoom, pan, hover)
- Works well with Streamlit
- Rich chart types
- Easy to export

### 2. Caching Strategy
**Choice**: st.cache_data with TTL
**Reason**:
- Reduces database load
- Faster page loads
- TTL ensures data freshness

### 3. Database Queries
**Choice**: Direct SQL via psycopg
**Reason**:
- Performance
- Control over queries
- Consistent with CLI

### 4. Real-Time Updates
**Choice**: Configurable auto-refresh
**Reason**:
- User control over refresh rate
- Balance between real-time and performance
- Works without websockets

### 5. Configuration
**Choice**: Reuse unified settings
**Reason**:
- Consistency with CLI
- Single source of truth
- Easy to maintain

## Testing Strategy

### 1. Unit Tests
- Database query functions
- Chart generation utilities
- Configuration loading

### 2. Integration Tests
- Page rendering
- Database connectivity
- Chart display

### 3. Manual Testing
- All pages load correctly
- Charts are interactive
- Data is accurate
- Performance is acceptable

## Dependencies to Add

```toml
[project.optional-dependencies]
dashboard = [
    "streamlit>=1.31",
    "plotly>=5.17",
    "pandas>=2.2",
    "numpy>=1.26",
]
```

## Performance Considerations

1. **Caching**: Cache all database queries
2. **Lazy Loading**: Load data only when needed
3. **Pagination**: Limit rows in tables
4. **Sampling**: Sample large datasets for charts
5. **Connection Pooling**: Reuse database connections

## Security Considerations

1. **Config Files**: Don't expose secrets in UI
2. **Database**: Use connection pooling
3. **Input Validation**: Sanitize all inputs
4. **Error Handling**: Don't expose stack traces

## Deployment Notes

- Local deployment via `streamlit run`
- Can be containerized with Docker
- Accessible via http://localhost:8501
- Can be made production-ready with proper reverse proxy

## Success Criteria

1. All 5 pages render correctly
2. Charts are interactive and informative
3. Database queries are cached and performant
4. Configuration integration works
5. Real-time updates function
6. UI is responsive and user-friendly
7. No performance issues with moderate data sizes

## Next Steps After Week 3

Week 4: Dashboard Advanced Features
- Custom themes
- Advanced filters
- Data export features
- User preferences
- Dark/light mode

Week 5: Testing & Documentation
- Unit tests
- Integration tests
- User guide
- API documentation
