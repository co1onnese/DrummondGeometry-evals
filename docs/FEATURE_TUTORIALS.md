# DGAS Dashboard Feature Tutorials

## Table of Contents
1. [Getting Started Tutorial](#getting-started-tutorial)
2. [Real-time Features Tutorial](#real-time-features-tutorial)
3. [Notification System Tutorial](#notification-system-tutorial)
4. [Custom Dashboard Builder Tutorial](#custom-dashboard-builder-tutorial)
5. [Filter Presets Tutorial](#filter-presets-tutorial)
6. [Export Data Tutorial](#export-data-tutorial)
7. [Performance Monitoring Tutorial](#performance-monitoring-tutorial)

---

## Getting Started Tutorial

### What You'll Learn
- How to start the dashboard
- Navigate between pages
- Understand the interface
- View basic system information

### Step 1: Start the Dashboard

```bash
# Navigate to project directory
cd /opt/DrummondGeometry-evals

# Start the dashboard
python run_dashboard.py
```

The dashboard will open at `http://localhost:8501`

### Step 2: Explore the Interface

**Sidebar Navigation:**
- 6 main pages: Overview, Data, Predictions, Backtests, System Status, Custom Dashboard
- Real-time status indicator
- Connection status (WebSocket)
- Live message count

**Main Content Area:**
- Each page has unique content and functionality
- Filter panels on the left
- Data tables/charts in center
- Export options on the right

### Step 3: Check System Status

1. Click "System Status" in sidebar
2. Review:
   - Database stats (symbols, data bars, size)
   - Recent activity (24h metrics)
   - Performance metrics
3. Note cache statistics

### Step 4: View Overview

1. Click "Overview" in sidebar
2. See:
   - Key metrics summary
   - Recent notifications
   - System health indicators

### Next Steps
Now that you're familiar with the interface, explore the specific feature tutorials!

---

## Real-time Features Tutorial

### What You'll Learn
- How real-time updates work
- Monitor connection status
- View live events
- Understand WebSocket vs polling

### Understanding Real-time Updates

The dashboard receives live data via WebSocket connection:

**Connection Methods:**
1. **WebSocket** (Primary): Persistent connection on port 8765
2. **Polling** (Fallback): Periodic HTTP requests if WebSocket unavailable

### Step 1: Check Connection Status

**Sidebar Indicators:**
- **Green Dot**: Connected
- **Red Dot**: Disconnected
- **Yellow Dot**: Reconnecting
- **Gray Dot**: Polling mode

**Connection Info in Sidebar:**
- Connection type (WebSocket/Polling)
- Reconnect attempts
- Last update time

### Step 2: View Live Events

**Real-time Events:**
- New predictions generated
- Trading signals created
- Backtest completions
- System status changes

**Where to See:**
- Notification toasts (bottom-right)
- Notification panel (Overview page bottom)
- Live message count in sidebar

### Step 3: Simulate Live Data

**Manual Refresh:**
1. Click "Refresh Data" in sidebar
2. All pages update with latest data

**Automatic Updates:**
- WebSocket connection sends events automatically
- No manual refresh needed
- Toasts appear for new events

### Step 4: Connection Troubleshooting

**If Disconnected:**
1. Check if port 8765 is available
2. Restart dashboard
3. Firewall may block WebSocket
4. Dashboard will auto-fallback to polling

**To Force Polling Mode:**
- Close port 8765
- Dashboard detects and switches
- "Polling" shown in status

### Step 5: Monitor Performance

**Real-time Metrics:**
- Message count
- Update frequency
- Connection quality

**View Metrics:**
1. Go to System Status page
2. Check "Performance" section
3. See query times and cache stats

### Best Practices

1. **Keep Connection Open**: WebSocket is more efficient
2. **Monitor Status**: Watch for disconnection
3. **Use Notifications**: Enable alerts for important events
4. **Check Logs**: If issues persist, check server logs

---

## Notification System Tutorial

### What You'll Learn
- How to view notifications
- Configure alert rules
- Set notification preferences
- Manage notification history

### Understanding Notifications

**8 Notification Types:**
- Prediction: New AI prediction
- Signal: Trading signal generated
- Backtest: Backtest completed
- System Status: System events
- Data Update: New data available
- Error: System errors
- Warning: System warnings
- Info: Informational messages

**4 Priority Levels:**
- Low: Blue (informational)
- Medium: Yellow (important)
- High: Orange (action recommended)
- Urgent: Red (immediate attention)

### Step 1: View Notifications

**Notification Toasts:**
- Appear bottom-right corner
- Auto-dismiss after 5 seconds
- Color-coded by priority
- Click to mark as read

**Notification Panel:**
1. Go to Overview page
2. Scroll to bottom
3. See all notifications
4. Filter by type/priority
5. Mark as read/unread

### Step 2: Configure Settings

1. Go to Overview page
2. Scroll to "Settings" tab
3. Configure:
   - **Enabled Types**: Check boxes for each type
   - **Minimum Priority**: Dropdown selection
   - **Quiet Hours**: Start/end times
   - **Auto-dismiss**: Seconds to show toast

**Example Configuration:**
- Enable: Prediction, Signal, Backtest, Error
- Min Priority: Medium
- Quiet Hours: 10 PM - 7 AM
- Auto-dismiss: 7 seconds

### Step 3: Create Alert Rule

**Default Rules (Pre-configured):**
1. High Confidence Predictions (confidence > 0.8)
2. Recent Signals (5+ signals in 1 hour)
3. Backtest Completed
4. System Errors

**Create Custom Rule:**
1. Go to Settings tab
2. Click "Add Alert Rule"
3. Fill form:
   - **Name**: "High Return Backtests"
   - **Condition**: Return greater than
   - **Threshold**: 10%
   - **Notification Type**: Backtest
   - **Priority**: High
   - **Enabled**: Yes
4. Click "Save Rule"

**Rule Conditions:**
- Confidence greater than X
- Signal count greater than X in Y hours
- Backtest return greater than X%
- New data for specific symbol
- Any system error
- Database size exceeds X GB

### Step 4: Test Notifications

**Simulate High Confidence Prediction:**
1. Configure rule (confidence > 0.8)
2. Generate prediction with 0.9 confidence
3. Observe:
   - Toast notification appears
   - Added to notification panel
   - Count in sidebar increases

**Simulate System Error:**
1. Create rule for "System Error"
2. Trigger system error
3. Check notification panel

### Step 5: Manage Notifications

**Mark as Read:**
- Click notification in panel
- Or use "Mark All as Read" button

**Filter View:**
- Use dropdown to filter by type
- Use dropdown to filter by priority
- Search by title/message

**Export History:**
1. Click "Export" in notification panel
2. Downloads JSON file
3. Contains all notifications and metadata

**Delete Notifications:**
- Click "X" on notification
- Or "Clear All" button

### Step 6: Notification Best Practices

1. **Set Quiet Hours**: Avoid nighttime alerts
2. **Use Priorities**: Reserve urgent for critical issues
3. **Review Rules**: Periodically check and update
4. **Export Regularly**: Backup notification history
5. **Test Rules**: Verify they trigger as expected

### Advanced: Alert Rule Templates

**Template 1: Daily Summary**
- Condition: Signal count > 10 in 24 hours
- Type: Info
- Priority: Low
- Sends once per day

**Template 2: Risk Alert**
- Condition: Backtest drawdown > 20%
- Type: Warning
- Priority: High
- Immediate alert

**Template 3: Data Gap**
- Condition: No data for symbol in 24 hours
- Type: Warning
- Priority: Medium
- Helps identify data issues

---

## Custom Dashboard Builder Tutorial

### What You'll Learn
- Create custom dashboards
- Add and configure widgets
- Arrange layout with grid system
- Save, load, and share dashboards

### Understanding the Builder

**Access:** Navigate to "Custom Dashboard" page

**Three Tabs:**
1. **Gallery**: Browse available widgets
2. **Dashboard**: Configure and arrange widgets
3. **Manage**: Save/load/export/import

### Step 1: Explore Widget Gallery

**Widget Types:**

**Metric Widget:**
- Single value display
- Formats: Number, Currency, Percentage
- Good for: Totals, averages, ratios
- Example: "Total Predictions Today", "Average Confidence"

**Chart Widget:**
- Visual data representation
- Types: Line, Bar, Scatter, Pie, Histogram
- Good for: Trends, distributions, comparisons
- Example: "Price Trend", "Confidence Distribution"

**Table Widget:**
- Tabular data display
- Configurable columns
- Pagination support
- Good for: Lists, detailed data
- Example: "Recent Signals", "Backtest Results"

### Step 2: Add Your First Widget

1. Go to "Gallery" tab
2. Click on a widget type (e.g., Metric)
3. Click "Add to Dashboard"
4. Configure:
   - **Title**: "Total Predictions"
   - **Data Source**: "Predictions"
   - **Format**: "Number"
   - **Position**: Row 0, Col 0, Width 3, Height 2
5. Click "Add Widget"

### Step 3: Configure Widget Settings

**Metric Widget Configuration:**
- Title: Widget name displayed
- Data Source: Where to get data
  - Predictions
  - Signals
  - Backtests
  - Market Data
  - System Status
- Format Options:
  - Number: Decimal places
  - Currency: Prefix ($, €, £)
  - Percentage: Decimal places, suffix (%)
- Grid Position:
  - Width: 1-12 columns
  - Height: 1-10 rows

**Chart Widget Configuration:**
- Title: Widget name
- Data Source: Select data table
- Chart Type: Line, Bar, Scatter, Pie, Histogram
- X Column: Horizontal axis
- Y Column: Vertical axis
- Color: Line/bar color
- Width: 1-12 columns
- Height: 1-10 rows

**Table Widget Configuration:**
- Title: Widget name
- Data Source: Select data table
- Columns: Select which columns to show
- Paginate: Yes/No
- Page Size: Number of rows per page
- Width: 1-12 columns
- Height: 1-10 rows

### Step 4: Arrange Layout

**Grid System:**
- 12-column grid
- Snap to grid automatically
- Drag to reposition
- Drag edges to resize

**Auto-Positioning:**
1. In Dashboard tab
2. Click "Auto-Position"
3. Choose mode:
   - **Pack Left to Right**: Fill rows left to right
   - **Pack Top to Bottom**: Fill columns top to bottom
   - **Grid Auto Arrange**: Balanced grid

**Manual Positioning:**
1. Click and drag widget
2. Drop in desired position
3. Drag edges to resize
4. Prevents overlaps

**Layout Tips:**
- Use consistent widths
- Align edges
- Group related widgets
- Leave whitespace
- Consider reading flow

### Step 5: Add Multiple Widgets

**Example Dashboard Layout:**

**Row 1:**
- Widget 1: Total Predictions (Metric, width 3)
- Widget 2: Recent Signals Chart (Chart, width 6)
- Widget 3: Success Rate (Metric, width 3)

**Row 2:**
- Widget 4: Signals Table (Table, width 12)

**Steps:**
1. Add each widget from Gallery
2. Configure individually
3. Arrange with auto-positioning
4. Fine-tune manually

### Step 6: Save Dashboard

1. Go to "Manage" tab
2. Click "Save"
3. Enter:
   - **Name**: "Trading Dashboard"
   - **Description**: "My custom trading metrics"
4. Click "Save Dashboard"

**Dashboard saved to:** `~/.dgas/dashboards/`

### Step 7: Load Dashboard

1. Go to "Manage" tab
2. Select dashboard from list
3. Click "Load"
4. Dashboard widgets appear

### Step 8: Export/Import

**Export Dashboard:**
1. In "Manage" tab
2. Select dashboard
3. Click "Export"
4. Downloads JSON file
5. Share with others

**Import Dashboard:**
1. In "Manage" tab
2. Click "Import"
3. Select JSON file
4. Dashboard imported

**Use Case:** Share dashboards with team members

### Step 9: Manage Dashboards

**List All:**
- See all saved dashboards
- View creation date
- See description

**Duplicate:**
1. Select dashboard
2. Click "Duplicate"
3. Enter new name
4. Create copy

**Delete:**
1. Select dashboard
2. Click "Delete"
3. Confirm

### Step 10: Advanced Features

**Widget Data Refresh:**
- Widgets auto-refresh with real-time data
- WebSocket updates apply automatically
- Manual refresh available

**Widget Actions:**
- Most widgets have context menu
- Options: Edit, Duplicate, Remove
- Right-click widget to access

**Dashboard Templates:**
- Start with sample layouts
- Available in Gallery
- Customize to your needs

### Best Practices

1. **Start Simple**: Add widgets gradually
2. **Consistent Naming**: Clear, descriptive titles
3. **Logical Grouping**: Related widgets near each other
4. **Mobile Considerations**: Dashboard is desktop-focused
5. **Regular Updates**: Save changes frequently
6. **Version Control**: Export before major changes

### Example Dashboard: Trading Overview

**Purpose:** Monitor all trading activity

**Widgets:**
1. Total Predictions (Metric) - Top left
2. Active Signals (Metric) - Top center
3. Success Rate % (Metric) - Top right
4. Recent Predictions Chart (Chart) - Middle left
5. Signal Distribution Chart (Chart) - Middle right
6. Recent Signals Table (Table) - Bottom (full width)

---

## Filter Presets Tutorial

### What You'll Learn
- Save filter configurations
- Load saved presets
- Search and organize presets
- Share presets with others

### Understanding Filter Presets

**What Are They:**
- Saved filter configurations
- One-click application
- Reusable across sessions
- Shareable between users

**When to Use:**
- Frequently used filters
- Standard analysis views
- Team-shared filters
- Quick data access

### Step 1: Configure Filters

1. Go to any page with filters (e.g., Predictions)
2. Set filter values:
   - **Date Range**: Last 7 days
   - **Symbol**: AAPL
   - **Min Confidence**: 0.8
   - **Signal Type**: BUY

### Step 2: Save as Preset

1. Scroll to "Filter Presets" panel
2. Click "Save" tab
3. Enter details:
   - **Name**: "High Confidence AAPL Buys"
   - **Description**: "AAPL BUY signals with >80% confidence from last week"
   - **Tags**: "AAPL, BUY, high-confidence"
4. Click "Save Preset"

**Preset saved to:** `~/.dgas/filter_presets/`

### Step 3: Load Preset

**Quick Load:**
1. Go to "Filter Presets" panel
2. Click "Load" tab
3. Select preset from list
4. Filters auto-applied

**Filter Applied:**
- Date range set to last 7 days
- Symbol set to AAPL
- Min confidence set to 0.8
- Signal type set to BUY

### Step 4: Search Presets

**Search Options:**
- By name
- By description
- By tags
- Case-insensitive

**Example Searches:**
- "AAPL" - finds all AAPL-related presets
- "high-confidence" - finds presets with this tag
- "weekly" - finds weekly reports

**Filter by Page:**
- Show only Predictions page presets
- Show only Signals page presets
- Show only Backtests presets

### Step 5: Organize with Tags

**Tagging Best Practices:**
- Use consistent naming
- Include symbol names
- Include strategy names
- Include time periods

**Example Tags:**
- "AAPL,high-confidence"
- "daily,report"
- "backtest,profitable"
- "NASDAQ,large-cap"

### Step 6: Manage Presets

**Edit Preset:**
1. Load preset
2. Modify filters
3. Save with same name (updates) or new name

**Delete Preset:**
1. Go to "Manage" tab
2. Select preset
3. Click "Delete"

**Duplicate Preset:**
1. Load preset
2. Modify
3. Save with new name

### Step 7: Export/Import Presets

**Export All:**
1. Go to "Manage" tab
2. Click "Export All"
3. Downloads JSON file
4. Contains all presets

**Export Single:**
1. In Load tab
2. Select preset
3. Click "Export"

**Import:**
1. Go to "Manage" tab
2. Click "Import"
3. Select JSON file
4. Presets imported

**Share with Team:**
1. Export presets
2. Send JSON file to colleagues
3. They import to their dashboard
4. Shared workflow

### Step 8: Filter History

**Automatic Tracking:**
- Last 10 configurations saved
- Automatic timestamps
- Quick reapply

**Access History:**
1. Go to "Filter Presets" panel
2. Click "History" tab
3. See recent filters
4. Click to reapply

**Use Case:**
- Quick access to filters you just used
- No need to save permanently
- Automatic cleanup after 10

### Example Presets

**Preset 1: Daily Trading**
- Page: Predictions
- Filters: Last 1 day, All symbols, Min confidence 0.7
- Tags: "daily,trading"
- Use: Morning check of overnight signals

**Preset 2: AAPL Deep Dive**
- Page: Predictions
- Filters: Last 30 days, Symbol AAPL, All confidences
- Tags: "AAPL,analysis"
- Use: Detailed AAPL analysis

**Preset 3: Profitable Backtests**
- Page: Backtests
- Filters: Last 90 days, Min return 10%
- Tags: "profitable,backtest"
- Use: Review successful strategies

**Preset 4: Recent Signals**
- Page: Signals
- Filters: Last 7 days, All symbols
- Tags: "recent,monitoring"
- Use: Daily signal review

**Preset 5: High Confidence Portfolio**
- Page: Predictions
- Filters: Last 14 days, Min confidence 0.9
- Tags: "high-confidence,portfolio"
- Use: Select high-conviction trades

### Step 9: Advanced Usage

**Combine with Custom Dashboard:**
- Save dashboard layout
- Save filter preset
- Load both for complete view

**Batch Operations:**
- Export all presets
- Backup before changes
- Share with team

**Naming Conventions:**
- Use descriptive names
- Include page name
- Include filter purpose
- Example: "[Predictions] AAPL High Conf"

### Best Practices

1. **Save Early**: Create presets for filters you use twice
2. **Descriptive Names**: Make purpose clear
3. **Use Tags**: Essential for search
4. **Export Regularly**: Backup your presets
5. **Share Standards**: Use common tags with team
6. **Document**: Include descriptions

---

## Export Data Tutorial

### What You'll Learn
- Export data in multiple formats
- Configure export options
- Create comprehensive reports
- Use exports for analysis

### Understanding Export Formats

**CSV (Comma-Separated Values):**
- Simple, universal format
- Open in Excel, Google Sheets
- Good for: Simple analysis, data manipulation
- Size: Small

**Excel (.xlsx):**
- Microsoft Excel format
- Formatting preserved
- Multi-sheet support
- Good for: Reports, presentations
- Size: Medium

**JSON (JavaScript Object Notation):**
- Structured data format
- API integration
- Programmatic access
- Good for: Developers, data pipelines
- Size: Medium

**PDF Reports:**
- Formatted reports
- Print-ready
- Charts and tables
- Good for: Sharing, documentation
- Size: Medium

**Comprehensive Report:**
- All formats together
- Complete data package
- Includes summary
- Good for: Complete analysis
- Size: Large

### Step 1: Basic CSV Export

1. Navigate to page with data (e.g., Predictions)
2. Configure filters
3. Scroll to "Export Data" section
4. Select "CSV" format
5. Enter filename: "predictions_2024_11_07"
6. Click "Download"

**File created:** `~/exports/predictions_2024_11_07.csv`

**Open in Excel:**
- Double-click file
- Or open Excel → File → Open

### Step 2: Excel Export with Multiple Sheets

1. Select "Excel" format
2. Enter filename: "trading_data"
3. Choose sheets:
   - Sheet 1: Predictions
   - Sheet 2: Signals
   - Sheet 3: Backtests
4. Click "Download"

**File created:** `~/exports/trading_data.xlsx`

**Sheets contain:**
- Sheet 1: Filtered predictions data
- Sheet 2: Filtered signals data
- Sheet 3: Filtered backtests data

### Step 3: JSON Export for Developers

1. Select "JSON" format
2. Enter filename: "api_export"
3. Check "Pretty Print" (formatted for readability)
4. Click "Download"

**File created:** `~/exports/api_export.json`

**Use in Code:**
```python
import json

with open('api_export.json', 'r') as f:
    data = json.load(f)

print(data['predictions'][0]['symbol'])
```

### Step 4: PDF Report

1. Select "PDF" format
2. Enter filename: "weekly_report"
3. Include charts (if available)
4. Click "Download"

**File created:** `~/exports/weekly_report.pdf`

**Contains:**
- Formatted tables
- Charts (if selected)
- Professional layout
- Print-ready

### Step 5: Comprehensive Report

1. Select "Comprehensive Report"
2. Enter base filename: "monthly_analysis"
3. Click "Generate Report"

**Downloads 4 files:**
- `monthly_analysis_summary.json`
- `monthly_analysis_data.xlsx`
- `monthly_analysis_report.pdf`
- `monthly_analysis_export.csv`

**Complete package for:**
- Sharing with stakeholders
- Archival
- Complete analysis

### Step 6: Configure Export Options

**Timestamp in Filename:**
- Yes: `predictions_2024-11-07_14-30-00.csv`
- No: `predictions.csv`
- Default: Yes

**CSV Options:**
- **Separator**: Comma, semicolon, tab
- **Encoding**: UTF-8, UTF-16
- **Include Index**: Yes/No (row numbers)
- **Date Format**: Various options

**Excel Options:**
- **Sheet Name**: Custom name
- **Index Column**: Include row numbers
- **Date Format**: Cell formatting

**JSON Options:**
- **Pretty Print**: Formatted for readability
- **Include Metadata**: Export info, timestamps

**PDF Options:**
- **Include Charts**: Embed visualizations
- **Page Orientation**: Portrait/Landscape
- **Include Summary**: Executive summary

### Step 7: Export from Custom Dashboard

**Per-Widget Export:**
1. In Custom Dashboard
2. Hover over widget
3. Click export button
4. Choose format
5. Download

**Entire Dashboard:**
1. Go to "Manage" tab
2. Click "Export Dashboard Data"
3. Choose formats
4. Downloads multiple files

### Step 8: Automated Exports

**Scheduled Exports** (via external tools):
- Use cron job to run export script
- Automate daily/weekly reports
- Email to distribution list

**Example Script:**
```bash
#!/bin/bash
# Daily export script
cd /opt/DrummondGeometry-evals
python -c "
from src.dgas.dashboard.export.enhanced_exporter import EnhancedExporter
import pandas as pd

exporter = EnhancedExporter()
data = pd.read_csv('daily_data.csv')
exporter.export_to_excel(data, f'daily_export_{date}')
"
```

### Step 9: Export Large Datasets

**Best Practices:**
- Use date filters to limit data
- Export in chunks if very large
- Use CSV for large datasets (fastest)
- Consider database queries directly

**Performance Tips:**
- Smaller date ranges export faster
- Fewer columns = faster export
- CSV is fastest format
- Compress large files

### Step 10: Use Exports for Analysis

**Excel Analysis:**
- Create pivot tables
- Build charts
- Calculate metrics
- Share with team

**CSV Analysis:**
- Import to Python/R
- Statistical analysis
- Machine learning
- Custom calculations

**JSON Integration:**
- API consumption
- Web dashboards
- Data pipelines
- Automated systems

**PDF Reporting:**
- Executive summaries
- Client reports
- Compliance documentation
- Presentations

### Example Workflows

**Workflow 1: Weekly Trading Report**
1. Set date filter: Last 7 days
2. Export to Excel
3. Add charts in Excel
4. Export to PDF
5. Email to team

**Workflow 2: Data Analysis**
1. Export predictions to CSV
2. Import to Python
3. Analyze confidence distribution
4. Identify patterns
5. Create visualizations

**Workflow 3: Compliance Archive**
1. Export comprehensive report
2. Add metadata (date, analyst)
3. Compress to ZIP
4. Store in archive
5. Retain for 7 years

### Best Practices

1. **Include Timestamps**: Track when exported
2. **Use Descriptive Names**: Make files identifiable
3. **Filter First**: Export only needed data
4. **Choose Right Format**: Match use case
5. **Document Exports**: Keep export log
6. **Version Control**: Track export changes
7. **Regular Backups**: Archive important exports

---

## Performance Monitoring Tutorial

### What You'll Learn
- Monitor query performance
- Understand cache metrics
- Identify slow queries
- Optimize dashboard speed

### Understanding Performance Monitoring

**Why Monitor Performance:**
- Identify bottlenecks
- Optimize database queries
- Improve user experience
- Plan capacity

**What We Track:**
- Query execution times
- Cache hit/miss rates
- Memory usage
- Slow query identification

### Step 1: View System Performance

1. Go to "System Status" page
2. Scroll to "Performance" section
3. Review metrics:

**Query Metrics:**
- Total Queries: Number executed
- Average Time: Mean execution time
- Min/Max Time: Range
- Total Time: Cumulative

**Cache Metrics:**
- Total Keys: Cached entries
- Hits: Successful cache lookups
- Misses: Cache misses
- Hit Rate: Percentage of hits
- Evictions: Entries removed

### Step 2: Identify Slow Queries

**Slow Query Threshold:**
- Default: 1.0 seconds
- Queries above threshold highlighted
- Configurable in code

**Find Slow Queries:**
1. In Performance section
2. Look for queries > 1.0 sec
3. Note query text
4. Check frequency

**Example Slow Queries:**
- `SELECT * FROM large_table` (2.5s)
- Complex JOIN with no index (3.2s)
- Aggregation over millions of rows (5.1s)

### Step 3: Check Cache Performance

**Cache Hit Rate:**
- **Good**: > 80%
- **Fair**: 60-80%
- **Poor**: < 60%

**Improving Hit Rate:**
- Increase cache size
- Extend TTL
- Cache more queries
- Review cache keys

**Cache Statistics:**
- Current entries
- Memory usage
- Eviction count
- Average entry size

### Step 4: Clear Cache

**When to Clear:**
- After data updates
- If cache seems stale
- Troubleshooting issues
- Performance problems

**How to Clear:**
1. In Performance section
2. Click "Clear Cache" button
3. Confirm action
4. Cache cleared

**After Clearing:**
- Queries hit database fresh
- Cache rebuilds automatically
- Hit rate starts at 0%
- Performance may temporarily decrease

### Step 5: Monitor Query Patterns

**Common Patterns:**
- Same query multiple times
- Predictable access patterns
- Time-based queries
- User-specific filters

**Optimize Patterns:**
- Cache frequent queries
- Add database indexes
- Simplify complex queries
- Use pagination

### Step 6: Performance Best Practices

**For Users:**
1. Use filter presets (reduces queries)
2. Limit date ranges
3. Avoid very large datasets
4. Use exports for big data
5. Clear cache if performance degrades

**For Developers:**
1. Review slow queries
2. Add database indexes
3. Optimize query structure
4. Implement caching
5. Monitor regularly

### Step 7: Use Lazy Loading

**What Is Lazy Loading:**
- Defer loading expensive data
- Load only when needed
- Improves initial page load
- Reduces memory usage

**Where Used:**
- Large charts
- Complex tables
- Historical data
- Heavy calculations

**How It Works:**
1. Page loads with placeholders
2. Data loads asynchronously
3. Progress indicator shown
4. Content appears when ready

### Step 8: Performance Tips by Page

**Overview Page:**
- Use date filters wisely
- Avoid 30-day ranges if not needed
- Cache improves with use

**Data Page:**
- Filter by symbol first
- Then by date range
- Export instead of viewing massive datasets

**Predictions Page:**
- Set minimum confidence filter
- Limit to specific symbols
- Use recent date ranges

**Backtests Page:**
- Filter by strategy
- Limit date range
- Export for detailed analysis

**System Status Page:**
- Auto-refreshes every 30 seconds
- Cache helps performance
- Clear cache if metrics seem wrong

### Step 9: Troubleshooting Performance

**Slow Dashboard:**

1. **Check System Status**
   - See if queries are slow
   - Check cache hit rate
   - Note any errors

2. **Clear Cache**
   - Removes stale data
   - Forces fresh queries
   - May temporarily slow down

3. **Reduce Data**
   - Narrow date ranges
   - Filter by symbol
   - Export instead of view

4. **Check Database**
   - Verify database size
   - Check for locks
   - Monitor resource usage

**High Memory Usage:**

1. **Limit Displayed Data**
   - Use pagination
   - Reduce columns
   - Shorter date ranges

2. **Close Unused Tabs**
   - Multiple pages use memory
   - Streamlit reloads page data

3. **Export Large Datasets**
   - Don't view, export instead
   - External tools handle better

### Step 10: Performance Metrics Reference

**Query Times:**
- Excellent: < 100ms
- Good: 100-500ms
- Fair: 500ms-1s
- Poor: > 1s
- Critical: > 5s

**Cache Hit Rate:**
- Excellent: > 90%
- Good: 80-90%
- Fair: 60-80%
- Poor: < 60%

**Database Size:**
- Small: < 1GB
- Medium: 1-10GB
- Large: 10-100GB
- Very Large: > 100GB

**Dashboard Load Time:**
- Excellent: < 2s
- Good: 2-5s
- Fair: 5-10s
- Poor: > 10s

### Advanced: Performance API

**Query Cache Directly:**
```python
from dgas.dashboard.performance.optimizer import get_cache

cache = get_cache()
stats = cache.get_stats()
print(f"Hit rate: {stats['hit_rate']}")
```

**Record Custom Metrics:**
```python
from dgas.dashboard.performance.optimizer import get_monitor

monitor = get_monitor()
monitor.record_query_time("custom_query", 0.5)
```

**Get Performance Summary:**
```python
summary = monitor.get_performance_summary()
print(summary)
```

### Best Practices Summary

1. **Monitor Regularly**: Check System Status daily
2. **Address Slow Queries**: Optimize or add indexes
3. **Maintain Cache**: Clear when stale, aim for >80% hit rate
4. **Filter Wisely**: Narrow queries perform better
5. **Export Large Data**: Don't view massive datasets
6. **Use Presets**: Reduce query complexity
7. **Document Issues**: Track performance problems

---

## Summary

### What You've Learned

**Week 4 Features Tutorial Series:**

1. ✅ **Getting Started**: Navigate and understand interface
2. ✅ **Real-time Features**: WebSocket, live updates, connection management
3. ✅ **Notification System**: Alerts, rules, settings, management
4. ✅ **Custom Dashboard**: Widgets, layout, save/load
5. ✅ **Filter Presets**: Save, load, search, share filters
6. ✅ **Export Data**: CSV, Excel, JSON, PDF, comprehensive reports
7. ✅ **Performance**: Monitoring, caching, optimization

### Next Steps

1. **Practice**: Try each tutorial with your own data
2. **Customize**: Create your own dashboard layouts
3. **Optimize**: Monitor and improve performance
4. **Share**: Export dashboards and presets
5. **Explore**: Check API documentation for advanced usage

### Additional Resources

- **User Guide**: `docs/DASHBOARD_USER_GUIDE.md`
- **API Documentation**: `docs/API_DOCUMENTATION.md`
- **System Documentation**: Project README

### Need Help?

- Check user guide
- Review API docs
- Examine example code
- Test with sample data

---

**Last Updated**: November 7, 2024
**Tutorial Version**: 1.0.0
