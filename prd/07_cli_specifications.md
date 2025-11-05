# Drummond Geometry Analysis System - CLI Specifications

## Table of Contents
1. [Overview](#overview)
2. [Command Structure](#command-structure)
3. [Global Options](#global-options)
4. [Configuration Management](#configuration-management)
5. [Subcommands](#subcommands)
6. [Help System](#help-system)
7. [Error Handling](#error-handling)
8. [Exit Codes](#exit-codes)
9. [Usage Examples](#usage-examples)

## Overview

The Drummond Geometry Analysis System (DGAS) provides a comprehensive command-line interface for geometric analysis of financial markets. The CLI supports backtesting, real-time prediction, data management, and reporting operations.

### Core Features
- **Backtesting Engine**: Historical analysis with configurable parameters
- **Real-time Prediction**: Live market analysis and signal generation
- **Data Management**: Database operations and EODHD integration
- **Multiple Output Formats**: CSV, JSON, PDF reports
- **Flexible Configuration**: YAML config files and environment variables
- **Comprehensive Logging**: Debug and operation logging

## Command Structure

```
dgas <subcommand> [options] [arguments]
```

### Primary Subcommands
- `backtest` - Execute historical backtesting analysis
- `predict` - Real-time market prediction
- `analyze` - Live market analysis
- `configure` - System configuration management
- `data` - Data management operations
- `report` - Generate analysis reports
- `status` - System status and health checks

## Global Options

```bash
# Global options apply to all subcommands
dgas [--config FILE] [--verbose] [--quiet] [--log-level LEVEL] [--help] [--version]

Options:
  --config FILE         Configuration file path (default: ~/.dgas/config.yaml)
  --verbose, -v         Enable verbose output
  --quiet, -q           Suppress all output except errors
  --log-level LEVEL     Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
  --log-file FILE       Custom log file path
  --no-color            Disable colored output
  --timeout SECONDS     Global timeout for operations
  --version             Display version information
  --help, -h            Show help message
```

## Configuration Management

### Configuration File Structure

```yaml
# ~/.dgas/config.yaml
api:
  eodhd:
    api_key: "${EODHD_API_KEY}"
    base_url: "https://eodhd.com/api"
    rate_limit: 100  # requests per minute
  
database:
  url: "postgresql://user:pass@localhost/dgas"
  pool_size: 10
  timeout: 30
  
logging:
  level: "INFO"
  file: "/var/log/dgas/dgas.log"
  max_size: "100MB"
  backup_count: 5
  
analysis:
  timeframe: "1d"
  geometry_tolerance: 0.001
  fibonacci_levels: [0.236, 0.382, 0.5, 0.618, 0.786]
  
reporting:
  default_format: "pdf"
  template_dir: "/usr/share/dgas/templates"
  output_dir: "./reports"
```

### Environment Variables

```bash
# EODHD API Configuration
export EODHD_API_KEY="your_api_key_here"
export EODHD_BASE_URL="https://eodhd.com/api"

# Database Configuration
export DGAS_DB_URL="postgresql://user:pass@localhost/dgas"

# Logging Configuration
export DGAS_LOG_LEVEL="INFO"
export DGAS_LOG_FILE="/var/log/dgas/dgas.log"

# Analysis Configuration
export DGAS_TIMEFRAME="1d"
export DGAS_GEOMETRY_TOLERANCE="0.001"
```

### Configuration Subcommand

```bash
# Show current configuration
dgas configure show

# Set configuration value
dgas configure set database.url "postgresql://user:pass@localhost/dgas"

# Set multiple values
dgas configure set \
  api.eodhd.api_key "your_key" \
  analysis.timeframe "1h"

# Generate default config file
dgas configure init

# Validate configuration
dgas configure validate

# Import configuration from file
dgas configure import config.yaml

# Export configuration to file
dgas configure export --output config_backup.yaml
```

## Subcommands

### Backtest Command

```bash
dgas backtest [OPTIONS]

Description:
  Execute historical backtesting analysis for specified symbols and timeframes.

Options:
  --symbols LIST          Comma-separated list of symbols (required)
  --start-date DATE       Start date in YYYY-MM-DD format (required)
  --end-date DATE         End date in YYYY-MM-DD format (required)
  --timeframe TF          Timeframe (1m, 5m, 15m, 1h, 4h, 1d, 1w, 1M)
  --strategy STRATEGY     Strategy name (default: 'geometric_analysis')
  --initial-capital NUM   Initial capital amount (default: 100000)
  --commission NUM        Commission rate (default: 0.001)
  --slippage NUM          Slippage in points (default: 0)
  --geometry-tolerance NUM Geometry tolerance level (default: 0.001)
  --fib-levels LIST       Fibonacci levels (default: 0.236,0.382,0.5,0.618,0.786)
  --min-pattern-confidence NUM Minimum pattern confidence (default: 0.7)
  --output FILE           Output file path (optional)
  --format FORMAT         Output format (csv, json, pdf)
  --save-to-db            Save results to database
  --parallel              Enable parallel processing
  --workers NUM           Number of worker processes (default: 4)
  --progress              Show progress bar
  --verbose, -v           Verbose output
  --help                  Show help message

Examples:
  # Basic backtest
  dgas backtest --symbols "AAPL,MSFT" --start-date 2023-01-01 --end-date 2023-12-31
  
  # Extended backtest with custom parameters
  dgas backtest \
    --symbols "AAPL,MSFT,GOOGL,TSLA" \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --timeframe 1h \
    --geometry-tolerance 0.002 \
    --fib-levels 0.236,0.382,0.5,0.618,0.786,1.0 \
    --output results.json \
    --format json \
    --save-to-db \
    --parallel \
    --workers 8
```

### Predict Command (Real-time Analysis)

```bash
dgas predict [OPTIONS]

Description:
  Real-time market prediction and signal generation.

Options:
  --symbols LIST          Comma-separated list of symbols (required)
  --timeframe TF          Analysis timeframe (1m, 5m, 15m, 1h, 4h, 1d)
  --duration MINUTES      Analysis duration in minutes (default: 60)
  --refresh-rate SECONDS  Data refresh rate (default: 60)
  --alert-threshold NUM   Alert confidence threshold (default: 0.8)
  --output-format FORMAT  Output format (json, csv, table)
  --webhook-url URL       Webhook URL for notifications
  --websocket            Enable WebSocket streaming
  --save-signals         Save signals to database
  --output FILE          Output file path (optional)
  --verbose, -v          Verbose output
  --help                 Show help message

Examples:
  # Basic real-time prediction
  dgas predict --symbols "AAPL,MSFT" --timeframe 1m
  
  # Extended prediction with alerts
  dgas predict \
    --symbols "AAPL,MSFT,GOOGL" \
    --timeframe 5m \
    --duration 120 \
    --refresh-rate 30 \
    --alert-threshold 0.85 \
    --output predictions.json \
    --format json \
    --webhook-url "https://hooks.slack.com/..." \
    --save-signals
```

### Analyze Command (Live Analysis)

```bash
dgas analyze [OPTIONS]

Description:
  Live market analysis with geometric pattern detection.

Options:
  --symbols LIST          Comma-separated list of symbols (required)
  --timeframe TF          Analysis timeframe (1m, 5m, 15m, 1h, 4h, 1d)
  --duration MINUTES      Analysis duration in minutes (default: 60)
  --pattern-types TYPES   Pattern types to detect (support,resistance,trendline,channel,triangle,wedge,flag)
  --min-confidence NUM    Minimum pattern confidence (default: 0.7)
  --show-fibonacci        Show Fibonacci retracement levels
  --show-volume          Show volume analysis
  --output FILE          Output file path (optional)
  --format FORMAT        Output format (json, csv, pdf)
  --plot                 Generate plot images
  --save-patterns        Save detected patterns to database
  --verbose, -v          Verbose output
  --help                 Show help message

Examples:
  # Basic analysis
  dgas analyze --symbols "AAPL" --timeframe 1h
  
  # Comprehensive analysis with plots
  dgas analyze \
    --symbols "AAPL,MSFT" \
    --timeframe 4h \
    --duration 240 \
    --pattern-types support,resistance,trendline,channel \
    --min-confidence 0.8 \
    --show-fibonacci \
    --show-volume \
    --output analysis.pdf \
    --format pdf \
    --plot \
    --save-patterns
```

### Data Management Commands

```bash
# EODHD Data Sync
dgas data sync [OPTIONS]

Options:
  --symbols LIST          Symbols to sync (default: all)
  --start-date DATE       Start date for historical data
  --end-date DATE         End date for historical data
  --timeframe TF          Data timeframe
  --overwrite            Overwrite existing data
  --incremental          Incremental sync (only new data)
  --progress             Show progress bar
  --verbose, -v          Verbose output

Examples:
  # Sync historical data
  dgas data sync --symbols "AAPL,MSFT" --start-date 2023-01-01 --end-date 2023-12-31
  
  # Incremental sync
  dgas data sync --incremental --progress

# Database Operations
dgas data db [COMMAND] [OPTIONS]

Commands:
  init        Initialize database schema
  migrate     Run database migrations
  backup      Create database backup
  restore     Restore from backup
  stats       Show database statistics
  clean       Clean old data

Options:
  --backup-file FILE     Backup file path
  --retention-days DAYS  Data retention period
  --verbose, -v         Verbose output

# Data Export
dgas data export [OPTIONS]

Options:
  --table TABLE          Database table to export
  --format FORMAT        Export format (csv, json, sql)
  --output FILE          Output file path
  --start-date DATE      Start date filter
  --end-date DATE        End date filter
  --symbols LIST         Symbol filter
  --limit NUM            Maximum records to export
  --compress            Compress output file
```

### Report Generation

```bash
dgas report [OPTIONS]

Description:
  Generate comprehensive analysis reports.

Options:
  --type TYPE            Report type (summary, detailed, performance, pattern_analysis)
  --symbols LIST         Symbols to include
  --start-date DATE      Report start date
  --end-date DATE        Report end date
  --timeframe TF         Analysis timeframe
  --template TEMPLATE    Report template name
  --output FILE          Output file path (required)
  --format FORMAT        Output format (pdf, html, docx)
  --include-charts       Include charts and plots
  --include-tables       Include data tables
  --include-summary      Include executive summary
  --branding COMPANY     Company branding for report
  --verbose, -v         Verbose output

Examples:
  # Generate summary report
  dgas report \
    --type summary \
    --symbols "AAPL,MSFT" \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --output monthly_report.pdf \
    --format pdf \
    --include-charts \
    --include-summary

  # Generate performance report
  dgas report \
    --type performance \
    --output performance_analysis.html \
    --format html \
    --include-charts
```

### System Status

```bash
dgas status [OPTIONS]

Description:
  Show system status and health information.

Options:
  --component COMP       Component to check (api, database, data, all)
  --detailed            Show detailed status information
  --json               Output in JSON format
  --monitor            Monitor status continuously
  --interval SECONDS    Monitor interval (default: 5)

Examples:
  # Check overall status
  dgas status
  
  # Check specific component
  dgas status --component database --detailed
  
  # Monitor system continuously
  dgas status --monitor --interval 10
```

## Help System

### Command-Specific Help

```bash
# General help
dgas --help
dgas -h

# Subcommand help
dgas <subcommand> --help
dgas <subcommand> -h

# Detailed help with examples
dgas <subcommand> --help --verbose
```

### Context-Sensitive Help

```bash
# Show help for specific option
dgas backtest --help --option symbols

# Show examples for command
dgas backtest --examples

# Show configuration help
dgas configure --help
```

## Error Handling

### Error Categories

1. **Configuration Errors**
   - Invalid configuration file
   - Missing required settings
   - Invalid parameter values

2. **Data Errors**
   - Network connectivity issues
   - API rate limiting
   - Invalid symbol or timeframe
   - Data availability issues

3. **System Errors**
   - Database connection failures
   - Insufficient disk space
   - Memory limitations
   - Permission denied

4. **Validation Errors**
   - Invalid date ranges
   - Symbol not found
   - Parameter out of range

### Error Output Format

```bash
ERROR [CODE]: Descriptive error message

Details:
  Component: backtest
  Symbol: INVALID_SYMBOL
  Parameter: symbols
  Value: INVALID_SYMBOL
  Suggested: Use valid symbol format (e.g., AAPL)

Help:
  Run 'dgas backtest --help' for usage information
  Check configuration: 'dgas configure validate'
  Documentation: https://docs.dgas.io/errors/INVALID_SYMBOL
```

### Validation Rules

```bash
# Symbol validation
- Must be alphanumeric (A-Z, a-z, 0-9)
- Max length: 10 characters
- Case insensitive
- Examples: AAPL, MSFT, GOOGL

# Date validation
- Format: YYYY-MM-DD
- Must be valid calendar date
- Start date must be before end date
- Cannot be future dates (for historical data)

# Timeframe validation
- Supported: 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d, 1w, 1M
- Must be supported by data provider
- Cannot be finer than data granularity

# Numeric validation
- Must be valid numbers
- Positive values for capital, amounts
- Ranges: 0.0 to 1.0 for probabilities, ratios
```

## Exit Codes

| Code | Description | Action |
|------|-------------|---------|
| 0 | Success | Normal operation |
| 1 | General error | Check error message |
| 2 | Invalid arguments | Review command syntax |
| 3 | Configuration error | Check config file |
| 4 | Data error | Check data source |
| 5 | Network error | Check connectivity |
| 6 | Database error | Check database status |
| 7 | Permission denied | Check file permissions |
| 8 | System resource error | Check system resources |
| 9 | API limit exceeded | Wait and retry |
| 10 | Validation error | Check input parameters |

### Exit Code Usage

```bash
#!/bin/bash
# Example script using exit codes

dgas backtest --symbols "AAPL" --start-date 2023-01-01 --end-date 2023-12-31
EXIT_CODE=$?

case $EXIT_CODE in
    0)
        echo "Backtest completed successfully"
        ;;
    2)
        echo "Invalid arguments provided"
        exit 1
        ;;
    4)
        echo "Data unavailable for specified symbols/dates"
        exit 2
        ;;
    *)
        echo "Unexpected error occurred (code: $EXIT_CODE)"
        exit 3
        ;;
esac
```

## Usage Examples

### Complete Workflow Example

```bash
#!/bin/bash
# Complete analysis workflow

# 1. Check system status
echo "Checking system status..."
dgas status --detailed
if [ $? -ne 0 ]; then
    echo "System check failed"
    exit 1
fi

# 2. Configure system
echo "Initializing configuration..."
dgas configure init
dgas configure set api.eodhd.api_key "$EODHD_API_KEY"

# 3. Sync data
echo "Syncing market data..."
dgas data sync --symbols "AAPL,MSFT,GOOGL,TSLA" --start-date 2023-01-01 --end-date 2023-12-31 --progress

# 4. Run backtest
echo "Running backtest analysis..."
dgas backtest \
    --symbols "AAPL,MSFT,GOOGL,TSLA" \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --timeframe 1h \
    --output backtest_results.json \
    --format json \
    --save-to-db \
    --verbose

# 5. Generate report
echo "Generating analysis report..."
dgas report \
    --type detailed \
    --symbols "AAPL,MSFT,GOOGL,TSLA" \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --output analysis_report.pdf \
    --format pdf \
    --include-charts \
    --include-summary

# 6. Start real-time monitoring
echo "Starting real-time prediction..."
dgas predict \
    --symbols "AAPL,MSFT,GOOGL,TSLA" \
    --timeframe 5m \
    --duration 120 \
    --alert-threshold 0.85 \
    --webhook-url "https://hooks.slack.com/..." \
    --save-signals &

echo "Workflow completed successfully"
```

### Common Use Cases

```bash
# Daily analysis workflow
dgas analyze --symbols "SPY,QQQ" --timeframe 1d --duration 1440 --show-fibonacci --plot

# Quick prediction for watchlist
dgas predict --symbols "AAPL,MSFT,GOOGL" --timeframe 15m --duration 60 --format table

# Portfolio backtesting
dgas backtest \
    --symbols "AAPL,MSFT,GOOGL,TSLA,AMZN,META,NVDA" \
    --start-date 2023-01-01 \
    --end-date 2023-12-31 \
    --timeframe 4h \
    --initial-capital 1000000 \
    --commission 0.0005 \
    --output portfolio_backtest.pdf \
    --format pdf

# Data maintenance
dgas data sync --incremental --progress
dgas data db stats
dgas data db clean --retention-days 90

# System monitoring
dgas status --monitor --interval 30

# Configuration management
dgas configure show
dgas configure validate
dgas configure export --output backup_config.yaml
```

### Batch Processing Example

```bash
#!/bin/bash
# Batch processing for multiple symbols

SYMBOLS=("AAPL" "MSFT" "GOOGL" "TSLA" "AMZN" "META" "NVDA")
START_DATE="2023-01-01"
END_DATE="2023-12-31"

for symbol in "${SYMBOLS[@]}"; do
    echo "Processing $symbol..."
    
    # Run backtest
    dgas backtest \
        --symbols "$symbol" \
        --start-date "$START_DATE" \
        --end-date "$END_DATE" \
        --timeframe 1h \
        --output "backtest_${symbol}.json" \
        --format json \
        --verbose
    
    if [ $? -eq 0 ]; then
        echo "Backtest completed for $symbol"
        
        # Generate individual report
        dgas report \
            --type summary \
            --symbols "$symbol" \
            --start-date "$START_DATE" \
            --end-date "$END_DATE" \
            --output "report_${symbol}.pdf" \
            --format pdf \
            --include-charts
    else
        echo "Backtest failed for $symbol"
    fi
done

echo "Batch processing completed"
```

### Real-time Monitoring Setup

```bash
#!/bin/bash
# Real-time monitoring and alerting

# Configuration
SYMBOLS="AAPL,MSFT,GOOGL,TSLA"
WEBHOOK_URL="https://hooks.slack.com/your-webhook"
LOG_FILE="/var/log/dgas/monitor.log"

# Start monitoring service
nohup dgas predict \
    --symbols "$SYMBOLS" \
    --timeframe 1m \
    --duration 1440 \
    --refresh-rate 60 \
    --alert-threshold 0.9 \
    --webhook-url "$WEBHOOK_URL" \
    --save-signals \
    --output "live_predictions.json" \
    --verbose > "$LOG_FILE" 2>&1 &

echo "Monitoring service started (PID: $!)"
echo "Logs: $LOG_FILE"
```

This comprehensive CLI specification provides a robust foundation for the Drummond Geometry Analysis System, covering all operational aspects from configuration to execution and reporting.