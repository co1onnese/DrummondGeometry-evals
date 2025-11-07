# DGAS Configure Command - Quick Reference Guide

## Overview

The `dgas configure` command provides an easy way to create, edit, validate, and view DGAS configuration files without needing to manually edit YAML files.

## Commands

### 1. Interactive Wizard - `dgas configure init`

Create a new configuration file using an interactive wizard.

**Usage:**
```bash
dgas configure init [--output PATH] [--template TEMPLATE] [--force]
```

**Options:**
- `--output PATH` - Output path for config file (default: `~/.config/dgas/config.yaml`)
- `--template {minimal,standard,advanced}` - Configuration template (default: standard)
- `--force` - Overwrite existing configuration file without prompting

**Templates:**

1. **Minimal** - Only essential settings
   - Database URL

2. **Standard** - Common settings for typical usage (default)
   - Database configuration
   - Scheduler (symbols, cron expression, timezone)
   - Notifications (Discord, console)

3. **Advanced** - All available settings
   - All standard settings plus:
   - Prediction engine parameters
   - Monitoring & SLA settings
   - Dashboard configuration

**Example:**
```bash
# Create config with standard template
dgas configure init

# Create config with advanced template
dgas configure init --template advanced --output dgas.yaml
```

### 2. Display Configuration - `dgas configure show`

Display the current configuration file with syntax highlighting.

**Usage:**
```bash
dgas configure show [--config PATH] [--format FORMAT]
```

**Options:**
- `--config PATH` - Path to config file (default: auto-detect)
- `--format {yaml,json}` - Output format (default: yaml)

**Example:**
```bash
# Show config in YAML format
dgas configure show

# Show specific config file in JSON format
dgas configure show --config dgas.yaml --format json
```

### 3. Validate Configuration - `dgas configure validate`

Validate a configuration file and display validation results.

**Usage:**
```bash
dgas configure validate [CONFIG_FILE]
```

**Arguments:**
- `CONFIG_FILE` - Path to config file (default: auto-detect)

**Example:**
```bash
# Validate default config
dgas configure validate

# Validate specific config file
dgas configure validate dgas.yaml
```

**Output:**
- Shows validation summary table
- Lists all configuration sections
- Displays validation errors if any
- Exit code 0 for valid, 1 for invalid

### 4. Generate Sample - `dgas configure sample`

Generate a sample configuration file with comments and placeholders.

**Usage:**
```bash
dgas configure sample [--output PATH] [--template TEMPLATE]
```

**Options:**
- `--output PATH` - Output path for sample config (default: `dgas-sample.yaml`)
- `--template {minimal,standard,advanced}` - Sample template (default: standard)

**Example:**
```bash
# Generate standard sample
dgas configure sample

# Generate advanced sample
dgas configure sample --output config.yaml --template advanced
```

### 5. Edit Configuration - `dgas configure edit`

Edit configuration file with your preferred text editor.

**Usage:**
```bash
dgas configure edit [--config PATH]
```

**Options:**
- `--config PATH` - Path to config file (default: auto-detect)

**Example:**
```bash
# Edit default config
dgas configure edit

# Edit specific config file
dgas configure edit --config dgas.yaml
```

**Notes:**
- Uses `$EDITOR` environment variable (defaults to nano)
- Validates configuration after editing
- Shows validation errors if any

## Configuration File Locations

DGAS searches for configuration files in the following order:

1. **Local directory**: `./dgas.yaml` or `./dgas.yml`
2. **User config**: `~/.config/dgas/config.yaml`
3. **System-wide**: `/etc/dgas/config.yaml`

The first file found is used.

## Environment Variables

Configuration files support environment variable expansion:

**Syntax:**
- `${VARIABLE_NAME}` - Braces syntax (recommended)
- `$VARIABLE_NAME` - Dollar syntax

**Common Variables:**
- `${DATABASE_URL}` - PostgreSQL connection URL
- `${DISCORD_WEBHOOK_URL}` - Discord webhook for notifications

**Example:**
```yaml
database:
  url: ${DATABASE_URL}

notifications:
  discord:
    webhook_url: ${DISCORD_WEBHOOK_URL}
```

## Configuration Templates

### Minimal Template

```yaml
database:
  url: ${DATABASE_URL}
```

### Standard Template

```yaml
database:
  url: ${DATABASE_URL}
  pool_size: 5

scheduler:
  symbols:
    - AAPL
    - MSFT
    - GOOGL
  cron_expression: "0 9,15 * * 1-5"
  timezone: America/New_York
  market_hours_only: true

notifications:
  discord:
    enabled: true
    webhook_url: ${DISCORD_WEBHOOK_URL}
  console:
    enabled: true
```

### Advanced Template

Includes all sections from standard template plus:

```yaml
prediction:
  min_confidence: 0.6
  min_signal_strength: 0.5
  stop_loss_atr_multiplier: 1.5
  target_atr_multiplier: 2.5

monitoring:
  sla_p95_latency_ms: 60000
  sla_error_rate_pct: 1.0
  sla_uptime_pct: 99.0

dashboard:
  port: 8501
  theme: light
  auto_refresh_seconds: 30
```

## Common Workflows

### First-Time Setup

```bash
# 1. Generate sample configuration
dgas configure sample --output dgas.yaml

# 2. Edit the file (set environment variables)
export DATABASE_URL="postgresql://user:pass@localhost/dgas"
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."

# 3. Validate configuration
dgas configure validate dgas.yaml

# 4. Move to user config directory
mkdir -p ~/.config/dgas
mv dgas.yaml ~/.config/dgas/config.yaml
```

### Using Interactive Wizard

```bash
# 1. Run wizard
dgas configure init

# 2. Follow prompts to configure:
#    - Database connection
#    - Symbols to track
#    - Schedule (cron expression)
#    - Timezone
#    - Notifications

# 3. Validate result
dgas configure validate
```

### Modifying Existing Configuration

```bash
# 1. Edit configuration
dgas configure edit

# 2. Make changes in your editor

# 3. Save and exit (validation happens automatically)

# 4. View updated configuration
dgas configure show
```

### Checking Configuration

```bash
# Display current configuration
dgas configure show

# Validate configuration
dgas configure validate

# Check which file is being used
dgas configure show | head -1
```

## Validation Rules

### Database
- `url` - Required, must be valid PostgreSQL URL
- `pool_size` - Optional, range: 1-50, default: 5

### Scheduler
- `symbols` - Required, list of stock symbols
- `cron_expression` - Optional, valid cron format
- `timezone` - Optional, valid timezone name
- `market_hours_only` - Optional, boolean

### Prediction
- `min_confidence` - Range: 0.0-1.0, default: 0.6
- `min_signal_strength` - Range: 0.0-1.0, default: 0.5
- `stop_loss_atr_multiplier` - Positive number, default: 1.5
- `target_atr_multiplier` - Positive number, default: 2.5

### Monitoring
- `sla_p95_latency_ms` - Positive integer, default: 60000
- `sla_error_rate_pct` - Range: 0.0-100.0, default: 1.0
- `sla_uptime_pct` - Range: 0.0-100.0, default: 99.0

### Dashboard
- `port` - Range: 1024-65535, default: 8501
- `theme` - Values: "light" or "dark", default: "light"
- `auto_refresh_seconds` - Range: 5-300, default: 30

## Error Messages

### Validation Errors

```
✗ Configuration validation failed:

  • database → url: field required
  • scheduler → symbols: field required
  • prediction → min_confidence: ensure this value is less than or equal to 1.0
```

### Missing File

```
No configuration file found.
Create one first: dgas configure init
```

### Environment Variable Not Found

```
Environment variable 'DATABASE_URL' not found
```

## Tips

1. **Start with a sample**: Use `dgas configure sample` to see all available options
2. **Use environment variables**: Keep secrets out of config files
3. **Validate often**: Run `dgas configure validate` after making changes
4. **Version control**: Commit config files (without secrets) to version control
5. **Use templates**: Choose the right template for your use case

## See Also

- Configuration Schema: `src/dgas/config/schema.py`
- Environment Variables: `.env.example`
- Full Documentation: `docs/PHASE5_WEEK1_DAYS3-4_SUMMARY.md`
