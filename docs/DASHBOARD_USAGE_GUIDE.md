# DGAS Dashboard - Quick Start Guide

## Overview
The DGAS Dashboard is a web-based interface for monitoring and analyzing market data, predictions, and backtest results.

## Quick Start

### 1. Install Dependencies
```bash
# Install build dependencies (Ubuntu/Debian)
sudo apt-get update
sudo apt-get install -y cmake build-essential

# Install Python dependencies
pip install streamlit plotly pandas psycopg pyarrow
```

### 2. Configure Database
Ensure your database is running and accessible:
```bash
# Check database connection
psql -h localhost -U dgas_user -d dgas_db

# Or use the CLI
dgas status
```

### 3. Start the Dashboard
```bash
# Using the launcher script
python run_dashboard.py

# Or directly with streamlit
streamlit run src/dgas/dashboard/app.py
```

### 4. Access the Dashboard
Open your browser to: **http://localhost:8501**

## Dashboard Pages

### 1. Overview
- **Purpose**: System summary and key metrics
- **What you'll see**:
  - Total symbols and data bars
  - Recent predictions (24h)
  - Recent signals (24h)
  - Data coverage by symbol
  - Recent backtests summary

**Key Features**:
- Key metrics at a glance
- Interactive data coverage charts
- Signal type distribution
- Performance summary

### 2. Data
- **Purpose**: Market data inventory and quality
- **Tabs**:
  - **Data Inventory**: All market data overview
  - **Quality Statistics**: Data completeness metrics
  - **Coverage Analysis**: Visual coverage analysis

**What you'll see**:
- Bar charts of data distribution
- Quality statistics by interval
- Coverage heatmaps
- Missing data estimates
- Data by exchange breakdown

**Key Features**:
- Multi-interval analysis (30min, 1h, 4h, 1d)
- Data completeness metrics
- Export data to CSV
- Interactive filters

### 3. Predictions
- **Purpose**: Trading signal analysis
- **Tabs**:
  - **Signal Analysis**: Confidence and risk-reward
  - **Timeline**: Temporal signal visualization
  - **Performance**: Signal characteristics
  - **Raw Data**: Complete signal dataset

**What you'll see**:
- Confidence distribution
- Risk-reward ratio analysis
- Signal timeline scatter plot
- Signal volume over time
- Price target metrics

**Key Features**:
- Filter by time period (1-90 days)
- Filter by symbol(s)
- Filter by minimum confidence
- Filter by signal type (BUY/SELL)
- Export signals to CSV
- Signal strength visualization

### 4. Backtests
- **Purpose**: Strategy performance analysis
- **Tabs**:
  - **Performance Overview**: Returns and Sharpe ratios
  - **Returns Analysis**: Top performers
  - **Risk Metrics**: Drawdown and win rate
  - **Strategy Comparison**: Strategy-level metrics
  - **Raw Data**: Complete backtest results

**What you'll see**:
- Performance comparison charts
- Return distributions
- Risk-return scatter plots
- Strategy comparison tables
- Top 10 performers

**Key Features**:
- Filter by symbol
- Filter by strategy
- Performance statistics
- Risk metrics analysis
- Export results to CSV

### 5. System Status
- **Purpose**: Real-time system monitoring
- **Tabs**:
  - **Database Metrics**: Database statistics
  - **Activity Timeline**: System activity
  - **System Diagnostics**: Health checks

**What you'll see**:
- System health status
- Database metrics (symbols, bars, size)
- Data coverage indicators
- Prediction activity (24h)
- Backtest activity (7 days)
- Health check results

**Key Features**:
- Auto-refresh (10-300 seconds)
- Real-time status updates
- Health check dashboard
- System information

## Navigation

### Sidebar
The sidebar provides:
- **Navigation menu**: Select any page
- **Settings**:
  - Auto-refresh toggle
  - Refresh interval (10-300 seconds)
- **Configuration info**:
  - Number of symbols
  - Configuration status

### Page Controls
Each page has:
- **Filters**: Customize data display
- **Tabs**: Organize information
- **Charts**: Interactive Plotly charts
- **Export**: Download data as CSV
- **Auto-refresh**: Real-time updates

## Interactive Features

### Filters
- **Date range**: Select time periods
- **Symbols**: Choose specific symbols
- **Confidence**: Set minimum confidence
- **Signal type**: Filter BUY/SELL
- **Strategies**: Filter by strategy name

### Charts
- **Zoom**: Click and drag to zoom
- **Pan**: Hold and drag to pan
- **Hover**: See detailed tooltips
- **Legend**: Click to hide/show series
- **Reset**: Double-click to reset view

### Data Tables
- **Sorting**: Click column headers
- **Pagination**: Navigate through pages
- **Search**: Use browser search (Ctrl+F)
- **Download**: Export to CSV

### Export
All data can be exported to CSV:
1. Navigate to the data you want
2. Use filters as needed
3. Click "Download" button
4. File saved automatically

## Customization

### Configuration File
Create or edit your config file:
```yaml
database:
  host: localhost
  port: 5432
  name: dgas_db
  user: dgas_user
  password: your_password

scheduler:
  symbols:
    - BTC/USD
    - ETH/USD
    - AAPL
    - TSLA
```

### Environment Variables
```bash
# Set config file path
export DGAS_CONFIG=/path/to/config.yaml

# Set database credentials
export DGAS_DB_HOST=localhost
export DGAS_DB_NAME=dgas_db
export DGAS_DB_USER=dgas_user
export DGAS_DB_PASSWORD=your_password
```

### Query Parameters
```
# Start with specific config
http://localhost:8501?config=/path/to/config.yaml
```

## Troubleshooting

### Dashboard Won't Start
```bash
# Check dependencies
pip list | grep streamlit
pip list | grep plotly

# Reinstall if needed
pip install --upgrade streamlit plotly
```

### Database Connection Error
```bash
# Test database connection
dgas status

# Check credentials
psql -h localhost -U dgas_user -d dgas_db
```

### No Data Displayed
1. Check database has data:
   ```bash
   dgas data list
   ```

2. Verify symbols in config:
   ```bash
   cat ~/.dgas/config.yaml
   ```

3. Check system status:
   ```bash
   dgas status
   ```

### Charts Not Loading
- Check browser console for errors
- Verify JavaScript is enabled
- Try refreshing the page
- Check internet connection (for Plotly CDN)

### Performance Issues
- Enable auto-refresh only when needed
- Reduce date range in filters
- Use pagination for large datasets
- Check database performance

## Tips & Best Practices

### Getting Started
1. Start with **Overview** for system health
2. Check **System Status** for issues
3. Review **Data** for coverage
4. Analyze **Predictions** for signals
5. Study **Backtests** for performance

### Efficient Use
1. Use filters to narrow data
2. Export data for offline analysis
3. Use auto-refresh for monitoring
4. Check multiple time periods
5. Compare strategies in Backtests

### Data Analysis
1. Use confidence filters in Predictions
2. Review risk-reward ratios
3. Check data quality in Data page
4. Monitor system health regularly
5. Track performance trends over time

## Keyboard Shortcuts

### Browser
- `Ctrl+F`: Find in page
- `Ctrl+R`: Refresh page
- `Ctrl+S`: Save page
- `F11`: Full screen

### Streamlit
- `r`: Rerun script
- `c`: Clear cache

## Advanced Usage

### Custom Queries
To add custom queries:
1. Edit `src/dgas/dashboard/components/database.py`
2. Add new function with `@st.cache_data`
3. Import in your page
4. Use in your analysis

### Adding Custom Charts
To add new charts:
1. Edit `src/dgas/dashboard/components/charts.py`
2. Create new function
3. Use Plotly for interactivity
4. Import in your page

### Page Modifications
To modify a page:
1. Edit the page file in `src/dgas/dashboard/pages/`
2. Add new tabs or sections
3. Use existing components
4. Test thoroughly

## API Reference

### Database Functions
```python
# Fetch system overview
system_overview = fetch_system_overview()

# Fetch predictions
predictions = fetch_predictions(days=7, symbol="BTC/USD", min_confidence=0.5)

# Fetch backtests
backtests = fetch_backtest_results(limit=10, symbol="AAPL")
```

### Chart Functions
```python
# Create line chart
fig = create_line_chart(df, x_col="date", y_col="price", title="Price Chart")

# Create bar chart
fig = create_bar_chart(df, x_col="symbol", y_col="return", title="Returns")

# Create scatter plot
fig = create_scatter_chart(df, x_col="confidence", y_col="rr", color_col="type")
```

### Utility Functions
```python
# Filter dataframe
filtered = filter_dataframe(df, {"symbol": "BTC/USD", "confidence": 0.8})

# Download data
download_dataframe(df, "export.csv")

# Format values
formatted = format_currency(1000.50)  # "$1,000.50"
formatted = format_percentage(0.123)  # "12.30%"
```

## Support

### Documentation
- **Dashboard Guide**: This document
- **API Docs**: See inline docstrings
- **Source Code**: Check component files

### Issues
1. Check system status first
2. Review logs for errors
3. Test database connection
4. Check configuration
5. Consult documentation

### Getting Help
- Check `/docs/` directory
- Review error messages
- Test with minimal data
- Check browser console
- Review database logs

## Conclusion

The DGAS Dashboard provides a comprehensive web interface for monitoring and analyzing your trading system. Use the overview to get started, then dive into specific pages based on your needs.

For more information, see:
- `docs/PHASE5_WEEK3_COMPLETION_SUMMARY.md` - Technical details
- `src/dgas/dashboard/components/` - Component documentation
- `src/dgas/dashboard/pages/` - Page implementations

---

**Last Updated**: 2024-11-07
**Version**: 1.0.0
