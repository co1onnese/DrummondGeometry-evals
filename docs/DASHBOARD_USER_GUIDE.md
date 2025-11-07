# DGAS Dashboard User Guide

## Table of Contents
1. [Introduction](#introduction)
2. [Getting Started](#getting-started)
3. [Dashboard Pages](#dashboard-pages)
4. [Real-time Features](#real-time-features)
5. [Notifications & Alerts](#notifications--alerts)
6. [Custom Dashboard Builder](#custom-dashboard-builder)
7. [Filter Presets](#filter-presets)
8. [Export Data](#export-data)
9. [Performance Monitoring](#performance-monitoring)
10. [Troubleshooting](#troubleshooting)

---

## Introduction

The DGAS (Drummond Geometry Analysis System) Dashboard is a comprehensive web-based interface for monitoring predictions, signals, backtests, and system performance in real-time. This guide covers all features introduced in Week 4, including real-time streaming, notification system, custom dashboard builder, and advanced features.

### Key Features

- **Real-time Data Streaming**: Live updates via WebSocket
- **Smart Notifications**: Alert system with configurable rules
- **Custom Dashboard Builder**: Create personalized dashboards
- **Filter Presets**: Save and reuse filter configurations
- **Multi-format Export**: Export data as CSV, Excel, JSON, or PDF
- **Performance Monitoring**: Track query times and cache performance

---

## Getting Started

### Starting the Dashboard

```bash
# Navigate to the project directory
cd /opt/DrummondGeometry-evals

# Start the dashboard
python run_dashboard.py
# or
streamlit run src/dgas/dashboard/app.py
```

The dashboard will open at `http://localhost:8501`

### Navigation

The dashboard has 6 main pages:
1. **Overview**: System summary and recent activity
2. **Data**: Market data inventory and quality
3. **Predictions**: Prediction signals and confidence scores
4. **Backtests**: Backtesting results and performance
5. **System Status**: System health and performance metrics
6. **Custom Dashboard**: Build your own dashboard with widgets

---

## Dashboard Pages

### Overview Page

The Overview page provides a high-level view of your system:

**Key Metrics:**
- Total symbols in database
- Total data bars
- Predictions in last 24 hours
- Signals in last 24 hours
- Latest backtest results
- Symbols with recent data

**Real-time Notifications:**
- Scroll to the bottom to see recent notifications
- Configure alert thresholds in Settings
- Set quiet hours to mute notifications
- Mark notifications as read/unread

### Data Page

View and analyze market data inventory:

**Features:**
- Filter by symbol or exchange
- Sort by bar count, date range
- Export data in multiple formats
- Save filter presets for quick access
- Monitor data quality metrics

**Data Quality Stats:**
- Estimated missing bars
- Data coverage by interval
- Gaps in time series

### Predictions Page

Monitor prediction signals and their performance:

**Filters:**
- Time range (days)
- Symbol
- Minimum confidence
- Signal type (BUY/SELL)

**Display:**
- Signal table with all details
- Confidence scores
- Risk/reward ratios
- Entry and target prices

**Actions:**
- Export to CSV/Excel/JSON/PDF
- Save filters as presets
- Create custom dashboard widgets

### Backtests Page

Review backtesting results:

**Filters:**
- Time range
- Symbol
- Strategy name
- Minimum return

**Metrics:**
- Total return
- Sharpe ratio
- Max drawdown
- Win rate
- Total trades

### System Status Page

Monitor system health and performance:

**Database Status:**
- Total symbols and data bars
- Database size
- Recent activity (24h)

**Performance Metrics:**
- Query execution times
- Cache hit rate
- Cache utilization
- Slow query identification

**Actions:**
- Clear cache
- Export performance report
- View detailed statistics

---

## Real-time Features

### WebSocket Connection

The dashboard supports real-time data streaming via WebSocket:

**Connection Status:**
- Check the sidebar for connection indicator
- Status: Connected/Disconnected/Reconnecting
- Automatic polling fallback if WebSocket unavailable

**Live Updates:**
- Real-time message count in sidebar
- Live notification toasts
- Automatic data refresh

**How It Works:**
1. WebSocket server runs on port 8765
2. Dashboard connects automatically
3. Events broadcasted in real-time:
   - Predictions
   - Signals
   - Backtest completions
   - System status changes

### Connection Management

**Automatic Reconnection:**
- If connection drops, dashboard attempts reconnection
- Fallback to polling mode
- Status displayed in sidebar

**Manual Refresh:**
- Click "Refresh Data" button in sidebar
- Forces update of all data

---

## Notifications & Alerts

### Notification System

The dashboard includes a comprehensive notification system with 8 types and 4 priority levels:

**Notification Types:**
- Prediction: New prediction generated
- Signal: New trading signal
- Backtest: Backtest completed
- System Status: System events
- Data Update: New data available
- Error: System errors
- Warning: System warnings
- Info: Informational messages

**Priority Levels:**
- Low: Informational
- Medium: Important
- High: Action recommended
- Urgent: Immediate attention required

### Viewing Notifications

**Notification Toast:**
- Appears in bottom-right corner
- Auto-dismisses after 5 seconds
- Color-coded by priority

**Notification Panel:**
- Scroll to bottom of Overview page
- Shows all notifications
- Mark as read/unread
- Filter by type or priority

### Alert Rules

Configure automatic alerts based on conditions:

**Default Rules:**
1. High Confidence Predictions (confidence > 0.8)
2. Recent Signals (signals in last hour)
3. Backtest Completed (new results)
4. System Errors (any error)

**Creating Custom Rules:**
1. Go to Overview page
2. Scroll to Settings tab
3. Click "Add Alert Rule"
4. Configure:
   - Name
   - Condition (confidence, signal count, etc.)
   - Threshold
   - Notification type
   - Priority
   - Enabled/Disabled

**Rule Conditions:**
- Confidence greater than X
- Signal count greater than X in Y hours
- Backtest return greater than X%
- New data for symbol
- System error

### Settings

**Notification Settings:**
1. Navigate to Overview page
2. Scroll to Settings tab
3. Configure:
   - **Enabled Types**: Select which notification types to show
   - **Minimum Priority**: Only show notifications at or above this level
   - **Quiet Hours**: Mute notifications during specified times
   - **Auto-dismiss**: How long to show toast notifications

**Export Notifications:**
- Click "Export" in notification panel
- Downloads JSON file with all notifications
- Includes metadata (timestamp, priority, etc.)

---

## Custom Dashboard Builder

Create personalized dashboards with custom widgets:

### Accessing Custom Dashboard

1. Navigate to "Custom Dashboard" page
2. Three main tabs:
   - **Gallery**: Browse available widgets
   - **Dashboard**: Configure and arrange widgets
   - **Manage**: Save/load/export/import dashboards

### Widget Types

**1. Metric Widget**
- Displays single value with formatting
- Formats: Number, Currency, Percentage
- Good for: Total counts, averages, ratios
- Example: "Total Predictions", "Average Confidence"

**2. Chart Widget**
- Displays data as charts
- Types: Line, Bar, Scatter, Pie, Histogram
- Configure X and Y columns
- Good for: Trends, distributions, comparisons
- Example: "Price Chart", "Confidence Distribution"

**3. Table Widget**
- Displays tabular data
- Configure columns to show
- Pagination support
- CSV export built-in
- Good for: Lists, detailed data
- Example: "Recent Signals", "Backtest Results"

### Adding Widgets

**From Gallery:**
1. Go to "Gallery" tab
2. Select widget type
3. Click "Add to Dashboard"
4. Configure widget settings

**Widget Configuration:**
- **Title**: Widget name
- **Data Source**: Where to get data
  - Predictions
  - Signals
  - Backtests
  - Market Data
  - System Status
  - Custom Query
- **Grid Position**: Size and location
  - Width: 1-12 columns
  - Height: 1-10 rows
- **Type-specific options**:
  - Metric: Format, precision
  - Chart: Chart type, columns
  - Table: Columns, pagination

### Layout Management

**Grid System:**
- 12-column grid layout
- Auto-positioning available
- Snap to grid
- Overlap detection

**Auto-Positioning Modes:**
1. **Pack Left to Right**: Fill rows left to right
2. **Pack Top to Bottom**: Fill columns top to bottom
3. **Grid Auto Arrange**: Balanced grid layout

**Positioning Widgets:**
1. Drag widgets to reposition
2. Resize by dragging edges
3. Snap to grid automatically
4. Prevent overlaps

### Saving Dashboards

**Save:**
1. Configure widgets in Dashboard tab
2. Click "Save" in Manage tab
3. Enter name and description
4. Click "Save Dashboard"

**Load:**
1. Go to Manage tab
2. Select dashboard from list
3. Click "Load"

**Export:**
1. Go to Manage tab
2. Select dashboard
3. Click "Export"
4. Downloads JSON file for sharing

**Import:**
1. Go to Manage tab
2. Click "Import"
3. Select JSON file
4. Dashboard imported

### Managing Multiple Dashboards

**List Dashboards:**
- View all saved dashboards
- See creation date and description
- Search by name

**Delete:**
1. Select dashboard
2. Click "Delete"
3. Confirm

**Duplicate:**
1. Select dashboard
2. Click "Duplicate"
3. Enter new name

---

## Filter Presets

Save and reuse filter configurations for quick access:

### Creating Presets

**Save Current Filters:**
1. Configure filters on any page
2. Scroll to "Filter Presets" panel
3. Click "Save" tab
4. Enter:
   - **Name**: Descriptive name
   - **Description**: What it filters
   - **Tags**: For search (e.g., "AAPL", "high-confidence")
5. Click "Save Preset"

**Example Presets:**
- "High Confidence AAPL" (min_confidence: 0.8, symbol: AAPL)
- "Recent Signals" (days: 7, min_confidence: 0.7)
- "Profitable Backtests" (min_return: 10%)

### Loading Presets

**Quick Load:**
1. Go to "Filter Presets" panel
2. Click "Load" tab
3. Select preset
4. Filters applied automatically

**Search Presets:**
- Search by name, description, or tags
- Filter by page (predictions, signals, etc.)
- Sort by name or date

### Managing Presets

**Edit:**
1. Load preset
2. Modify filters
3. Save with same or new name

**Delete:**
1. Go to "Manage" tab
2. Select preset
3. Click "Delete"

**Export/Import:**
- Export all presets as JSON
- Import presets from file
- Share presets between users

### Filter History

**Automatic Tracking:**
- Last 10 filter configurations saved
- Quick reapply
- View what you used recently

**Access:**
1. Go to "Filter Presets" panel
2. Click "History" tab
3. Select from recent filters

---

## Export Data

Export data in multiple formats for external analysis:

### Export Formats

**CSV (Comma-Separated Values)**
- Simple, universal format
- Open in Excel, Google Sheets
- Good for simple data
- Customizable separator

**Excel (.xlsx)**
- Multi-sheet workbooks
- Formatting preserved
- Good for reports
- Multiple data sources

**JSON (JavaScript Object Notation)**
- Structured data format
- Programmatic access
- API integration
- Pretty-printed

**PDF Reports**
- Formatted reports
- Tables and charts
- Print-ready
- Professional presentation

**Comprehensive Report**
- All formats in one
- Complete data package
- Includes summary
- Best for sharing

### Export Process

**Basic Export:**
1. Navigate to page with data
2. Scroll to "Export Data" section
3. Select format
4. Enter filename
5. Click "Download"

**Options:**
- **Include Timestamp**: Add date/time to filename
- **Custom Separator** (CSV): Comma, semicolon, tab
- **Encoding** (CSV): UTF-8, UTF-16
- **Date Format**: How to format dates
- **Include Index**: Add row numbers
- **Compression**: Gzip, zip

**Multi-Sheet Excel:**
1. Select "Excel" format
2. Choose sheet names
3. Configure each sheet's data
4. Download

### Exporting from Custom Dashboard

**Widget-Level Export:**
- Most widgets have export button
- Export just that widget's data
- Same formats available

**Dashboard Export:**
- Export entire dashboard data
- Multiple worksheets
- Comprehensive report

### Export Locations

Exports saved to:
- `~/exports/` directory (default)
- Custom path configurable
- Filename format: `export_{timestamp}.{ext}`

---

## Performance Monitoring

Track and optimize dashboard performance:

### Query Performance

**Metrics Tracked:**
- Total queries executed
- Average query time
- Min/Max query times
- Total execution time
- Slow query identification

**View Metrics:**
1. Go to System Status page
2. Scroll to "Performance" section
3. View metrics table

**Slow Query Threshold:**
- Default: 1.0 seconds
- Configurable
- Queries above threshold highlighted

### Caching

**Cache Manager:**
- Reduces database load
- Improves response times
- TTL-based expiration
- LRU eviction

**Cache Statistics:**
- Total cache entries
- Cache hits
- Cache misses
- Hit rate percentage
- Evictions

**Cache Operations:**
- **Get**: Retrieve cached value
- **Set**: Store value with TTL
- **Clear**: Remove all entries
- **Get Stats**: View statistics

**View Cache Stats:**
1. Go to System Status page
2. See "Cache Statistics"
3. Monitor hit rate
4. Track utilization

**Clear Cache:**
- Click "Clear Cache" button
- Removes all cached data
- Forces fresh database queries
- Use when troubleshooting

### Lazy Loading

**What It Is:**
- Defer loading expensive data
- Load only when needed
- Improves initial page load
- Reduces memory usage

**Implementation:**
- Automatic for heavy components
- Manual via decorators
- Toggle for specific widgets

### Performance Tips

**Optimize Queries:**
- Use filters to reduce data
- Limit date ranges
- Avoid SELECT *
- Index frequently queried columns

**Use Caching:**
- Cache stable data
- Set appropriate TTL
- Monitor hit rates
- Clear cache periodically

**Filter Presets:**
- Reuse common filters
- Reduce query complexity
- Save time

**Export Instead of View:**
- Large datasets: export
- Reduces memory usage
- Faster processing

---

## Troubleshooting

### Connection Issues

**WebSocket Not Connected:**
1. Check if port 8765 is available
2. Restart dashboard
3. Check firewall settings
4. Fallback to polling mode

**Data Not Updating:**
1. Click "Refresh Data" in sidebar
2. Check connection status
3. Verify database connectivity
4. Check logs for errors

### Performance Issues

**Slow Page Loads:**
1. Check System Status for slow queries
2. Clear cache
3. Reduce date range filters
4. Check database size

**High Memory Usage:**
1. Limit data displayed
2. Use pagination
3. Export large datasets
4. Clear browser cache

### Notification Issues

**Not Receiving Alerts:**
1. Check notification settings
2. Verify alert rules enabled
3. Check minimum priority
4. Verify quiet hours

**Too Many Notifications:**
1. Increase minimum priority
2. Configure quiet hours
3. Disable notification types
4. Review alert rules

### Export Issues

**Export Fails:**
1. Check file permissions
2. Verify disk space
3. Reduce data size
4. Try different format

**File Not Downloading:**
1. Check browser downloads
2. Disable popup blocker
3. Try different browser
4. Check file path

### Widget Issues

**Widget Not Loading:**
1. Check data source
2. Verify permissions
3. Refresh dashboard
4. Recreate widget

**Layout Problems:**
1. Check for overlaps
2. Use auto-positioning
3. Reset layout
4. Reload dashboard

### Getting Help

**Check Logs:**
- Dashboard logs in terminal
- Browser console (F12)
- Database logs

**System Information:**
- Version info in sidebar
- Performance metrics
- Database stats

**Report Issues:**
1. Note error messages
2. Record steps to reproduce
3. Include screenshots
4. Export system info

---

## Tips & Best Practices

### Dashboard Usage

1. **Use Filter Presets**: Save time on common filters
2. **Create Custom Dashboards**: Focus on your key metrics
3. **Monitor Performance**: Keep an eye on System Status
4. **Export Regularly**: Back up important data
5. **Configure Alerts**: Stay informed of important events

### Performance

1. **Avoid Large Date Ranges**: Use specific time windows
2. **Use Caching**: Enable for frequently accessed data
3. **Clear Cache Periodically**: Especially after data changes
4. **Monitor Slow Queries**: Identify and optimize
5. **Limit Data Displayed**: Use pagination for large datasets

### Data Management

1. **Export Before Analysis**: Get clean, formatted data
2. **Use Appropriate Formats**:
   - CSV for simple analysis
   - Excel for reports
   - JSON for programmatic access
   - PDF for presentations
3. **Version Control Dashboards**: Export before major changes
4. **Share Filter Presets**: Standardize team workflows

---

## Appendix

### Keyboard Shortcuts

- `Ctrl+R`: Refresh data
- `Ctrl+S`: Save current dashboard
- `Ctrl+E`: Export data
- `Ctrl+F`: Search in current page

### File Locations

- **Dashboard**: `src/dgas/dashboard/`
- **Exports**: `~/exports/`
- **Dashboards**: `~/.dgas/dashboards/`
- **Filter Presets**: `~/.dgas/filter_presets/`
- **Cache**: In-memory (cleared on restart)

### Configuration Files

- `~/.dgas/dashboard.yaml`: Dashboard settings
- `~/.dgas/notifications.yaml`: Notification settings
- `~/.dgas/alerts.yaml`: Alert rules

### Data Sources

1. **Market Symbols**: All tracked symbols
2. **Market Data**: OHLCV data
3. **Predictions**: AI-generated predictions
4. **Signals**: Trading signals
5. **Backtests**: Strategy backtesting results
6. **System Status**: Database and system metrics

---

## Changelog

### Week 4 Features (Current)

**Day 1: Real-time Data Streaming**
- WebSocket server implementation
- Real-time client integration
- Connection management
- Event broadcasting

**Day 2: Notification & Alert System**
- 8 notification types
- 4 priority levels
- Alert rules engine
- Configurable settings
- Quiet hours

**Day 3: Custom Dashboard Builder**
- 3 widget types (Metric, Chart, Table)
- 12-column grid layout
- Auto-positioning
- Save/load/export/import

**Day 4: Advanced Features**
- Filter preset system
- Enhanced exports (CSV, Excel, JSON, PDF)
- Performance optimization
- Caching and monitoring

### Previous Weeks

**Weeks 1-3: Foundation**
- Basic dashboard structure
- Data pages
- Database integration
- Initial UI components

---

## Support

For issues, questions, or feature requests:
1. Check this user guide
2. Review troubleshooting section
3. Check system status
4. Contact support team

---

**Last Updated**: November 7, 2024
**Version**: Week 4 Complete
**Dashboard Version**: 1.0.0
