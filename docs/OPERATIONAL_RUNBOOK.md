# DGAS Operational Runbook

**Version**: 1.0
**Last Updated**: November 7, 2025
**Audience**: Operations Team, DevOps Engineers, System Administrators

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Quick Reference](#quick-reference)
4. [Daily Operations](#daily-operations)
5. [System Startup/Shutdown](#system-startupshutdown)
6. [Troubleshooting Guide](#troubleshooting-guide)
7. [Performance Monitoring](#performance-monitoring)
8. [Backup and Recovery](#backup-and-recovery)
9. [Maintenance Schedule](#maintenance-schedule)
10. [Incident Response](#incident-response)
11. [Configuration Reference](#configuration-reference)
12. [Contact Information](#contact-information)

---

## System Overview

### What is DGAS?

The Drummond Geometry Analysis System (DGAS) is a production-ready trading signal generation and analysis platform that implements Charles Drummond's geometric market analysis methodology. The system provides:

- **Real-time market data ingestion** from EODHD API
- **Drummond geometry calculations** (PLdot, envelopes, patterns)
- **Multi-timeframe coordination** for signal confluence
- **Automated prediction scheduling** (30-minute intervals)
- **Smart notifications** (Discord, email, console)
- **Web-based dashboard** with real-time updates
- **Performance monitoring** and SLA tracking

### Key Components

1. **Data Ingestion Layer**: Fetches market data from EODHD
2. **Calculation Engine**: Computes Drummond geometry indicators
3. **Prediction System**: Generates trading signals
4. **Database**: PostgreSQL for data persistence
5. **Dashboard**: Streamlit-based web interface
6. **Scheduler**: Automated prediction cycles
7. **Notification System**: Multi-channel alerts

### System Requirements

- **Python**: 3.11+
- **Database**: PostgreSQL 13+
- **Memory**: 4GB minimum, 8GB recommended
- **Disk**: 50GB minimum for data
- **Network**: Internet connection for EODHD API

---

## Architecture

```
┌─────────────────┐
│   EODHD API     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│         DGAS System                      │
│  ┌──────────┐  ┌──────────┐  ┌────────┐ │
│  │  Data    │  │Calc Engine│  │Predict │ │
│  │Ingestion │  │           │  │System  │ │
│  └──────────┘  └──────────┘  └────────┘ │
│         │            │           │       │
│         └────────────┼───────────┘       │
│                      │                   │
│  ┌──────────┐  ┌─────▼──────┐  ┌────────┐ │
│  │PostgreSQL│  │ Dashboard  │  │Notifier│ │
│  │ Database │  │   (Web)    │  │ System │ │
│  └──────────┘  └────────────┘  └────────┘ │
└─────────────────────────────────────────┘
```

### Data Flow

1. **Ingestion**: Market data fetched from EODHD every 30 minutes
2. **Storage**: Data stored in PostgreSQL with optimized indexes
3. **Calculation**: Drummond geometry indicators computed
4. **Analysis**: Multi-timeframe coordination performed
5. **Signal Generation**: Trading signals created based on confluence
6. **Notification**: Alerts sent via configured channels
7. **Monitoring**: Performance metrics tracked and reported

---

## Quick Reference

### Essential Commands

```bash
# Check system status
dgas status

# View recent signals
dgas report recent-signals

# Start the dashboard
dgas-dashboard --port 8501

# Check scheduler status
dgas scheduler status

# View performance metrics
dgas monitor

# Run a manual prediction
dgas predict AAPL MSFT

# Check data quality
dgas data quality-report
```

### Log Locations

- **Application logs**: `~/.dgas/logs/`
- **Database logs**: PostgreSQL logs (system-dependent)
- **Scheduler logs**: `~/.dgas/logs/scheduler.log`
- **Dashboard logs**: Streamlit logs (console output)

### Important Files

- **Configuration**: `~/.dgas/config.yaml`
- **Environment**: `~/.dgas/.env`
- **Cache**: `~/.dgas/cache/`
- **Reports**: `~/.dgas/reports/`

---

## Daily Operations

### Morning Checklist (9:00 AM EST)

1. **Check System Health**
   ```bash
   dgas status
   ```
   - Verify all components are running
   - Check for any error indicators
   - Review overnight prediction runs

2. **Review Performance Metrics**
   ```bash
   dgas monitor --summary --hours 24
   ```
   - Check P95 latency (<60s target)
   - Verify error rate (<1% target)
   - Review uptime (>99% target)

3. **Check Data Quality**
   ```bash
   dgas data quality-report --symbol AAPL
   ```
   - Verify latest bars received
   - Check for data gaps
   - Review data completeness

4. **Review Signals**
   ```bash
   dgas report recent-signals --hours 24
   ```
   - Count signals generated
   - Review signal distribution
   - Check for anomalies

5. **Check Dashboard**
   - Open dashboard: `dgas-dashboard --port 8501`
   - Navigate to System Status page
   - Verify all charts and metrics are loading

### Midday Check (1:00 PM EST)

1. **Monitor Prediction Cycle**
   - Check if 30-minute cycle completed
   - Review execution time
   - Verify signal generation

2. **Check Notifications**
   - Review Discord notifications
   - Check email alerts
   - Verify all channels working

3. **Review Database Performance**
   ```bash
   dgas monitor database --stats
   ```
   - Check query performance
   - Review cache hit rates
   - Monitor connection pool

### Evening Wrap-up (5:00 PM EST)

1. **Review Daily Summary**
   ```bash
   dgas report daily-summary
   ```

2. **Check Scheduler Status**
   ```bash
   dgas scheduler status
   ```

3. **Verify Next-Day Scheduling**
   - Confirm next run is scheduled
   - Check for any issues

4. **Archive Reports**
   - Daily reports are auto-archived
   - Location: `~/.dgas/reports/daily/`

---

## System Startup/Shutdown

### Starting the System

#### Start PostgreSQL Database
```bash
# Linux (systemd)
sudo systemctl start postgresql

# Check status
sudo systemctl status postgresql
```

#### Initialize DGAS Environment
```bash
# Activate virtual environment
source ~/.dgas/venv/bin/activate

# Verify configuration
dgas configure verify

# Run database migrations if needed
dgas migrate
```

#### Start the Scheduler
```bash
# Start scheduler daemon
dgas scheduler start

# Verify it's running
dgas scheduler status
```

#### Start the Dashboard
```bash
# Start dashboard in background
dgas-dashboard --port 8501 --no-browser &

# Or with browser
dgas-dashboard --port 8501
```

#### Verify All Components
```bash
# Full system check
dgas status --verbose

# Check all services
dgas status --check-all
```

### Shutting Down the System

#### Graceful Shutdown

1. **Stop the Dashboard**
   ```bash
   # Find dashboard process
   ps aux | grep streamlit

   # Kill gracefully
   kill <streamlit_pid>
   ```

2. **Stop the Scheduler**
   ```bash
   dgas scheduler stop

   # Verify stopped
   dgas scheduler status
   ```

3. **Optional: Stop Database**
   ```bash
   sudo systemctl stop postgresql
   ```

#### Emergency Shutdown
```bash
# Kill all DGAS processes
pkill -f "dgas"

# Stop database
sudo systemctl stop postgresql
```

### Restart Procedures

#### Restart Scheduler Only
```bash
dgas scheduler stop
dgas scheduler start
dgas scheduler status
```

#### Restart Dashboard Only
```bash
# Kill old process
pkill -f streamlit

# Start new instance
dgas-dashboard --port 8501 --no-browser &
```

#### Full System Restart
```bash
# Complete restart sequence
dgas scheduler stop
pkill -f streamlit
dgas status --check-all
dgas scheduler start
dgas-dashboard --port 8501 --no-browser &
dgas status --verbose
```

---

## Troubleshooting Guide

### Common Issues

#### Issue: Scheduler Not Running

**Symptoms**:
- No new predictions generated
- `dgas scheduler status` shows "STOPPED"
- Dashboard shows stale data

**Diagnosis**:
```bash
dgas scheduler status --verbose
dgas scheduler logs --tail 50
```

**Solutions**:
```bash
# Start scheduler
dgas scheduler start

# Check configuration
dgas configure verify

# Review logs
tail -f ~/.dgas/logs/scheduler.log
```

**Root Causes**:
- Configuration error
- Database connection issue
- Missing environment variables

---

#### Issue: High Prediction Latency

**Symptoms**:
- `dgas monitor` shows P95 > 60s
- Slow dashboard updates
- Backlog of pending predictions

**Diagnosis**:
```bash
dgas monitor performance --hours 1
dgas monitor breakdown --run latest
```

**Solutions**:
1. **Enable optimizations** (Week 1 & 2 features):
   ```bash
   # These are automatic in optimized version
   # Verify connection pool is active
   dgas db-optimizer stats
   ```

2. **Check database performance**:
   ```bash
   dgas db-optimizer analyze-slow-queries
   ```

3. **Clear cache if corrupted**:
   ```bash
   dgas cache clear
   ```

**Root Causes**:
- Database query bottlenecks
- Missing indexes
- Insufficient connection pool size
- Cache issues

---

#### Issue: Dashboard Not Loading

**Symptoms**:
- Browser shows "This site can't be reached"
- Streamlit error in console
- Empty dashboard

**Diagnosis**:
```bash
# Check if dashboard is running
ps aux | grep streamlit

# Check port
netstat -tuln | grep 8501

# Check logs
streamlit --version
```

**Solutions**:
```bash
# Restart dashboard
pkill -f streamlit
dgas-dashboard --port 8501 --no-browser &

# Check configuration
dgas configure verify

# Verify port is not in use
lsof -i :8501
```

**Root Causes**:
- Dashboard process stopped
- Port conflict
- Streamlit not installed
- Configuration error

---

#### Issue: No Data for Symbols

**Symptoms**:
- `dgas data fetch` fails
- `dgas data quality-report` shows gaps
- Empty prediction results

**Diagnosis**:
```bash
# Check EODHD connection
dgas data test-connection

# Check API token
dgas configure show-api-token

# Check recent data
dgas data latest --symbol AAPL
```

**Solutions**:
1. **Verify API token**:
   ```bash
   # Edit .env file
   nano ~/.dgas/.env
   # Ensure EODHD_API_TOKEN is set
   ```

2. **Check API limits**:
   - Verify subscription status
   - Check rate limiting

3. **Test manual fetch**:
   ```bash
   dgas data fetch AAPL --interval 1d --days 5
   ```

**Root Causes**:
- Invalid or expired API token
- API rate limit exceeded
- Network connectivity issue
- Symbol not available

---

#### Issue: High Database CPU Usage

**Symptoms**:
- System slow response
- High CPU in PostgreSQL
- Query timeouts

**Diagnosis**:
```bash
# Check slow queries
dgas db-optimizer slow-queries

# Check index usage
dgas db-optimizer index-stats

# Check database size
dgas db-optimizer db-stats
```

**Solutions**:
```bash
# Add missing indexes
dgas db-optimizer add-indexes

# Run VACUUM ANALYZE
dgas db-optimizer vacuum

# Check for unused indexes
dgas db-optimizer unused-indexes
```

**Root Causes**:
- Missing indexes
- Outdated statistics
- Unused indexes consuming resources
- Large table scans

---

#### Issue: Notification Failures

**Symptoms**:
- Discord notifications not working
- Missing email alerts
- Console errors

**Diagnosis**:
```bash
# Check notification config
dgas configure show-notifications

# Test notification
dgas notify test --channel discord
dgas notify test --channel email
```

**Solutions**:
1. **Discord**:
   - Verify webhook URL in config
   - Check Discord server permissions

2. **Email**:
   - Verify SMTP settings
   - Check email server credentials

**Root Causes**:
- Invalid webhook URL
- SMTP authentication failure
- Network blocked
- Wrong channel configuration

---

### Log Analysis

#### Where to Find Logs

- **Application**: `~/.dgas/logs/`
- **Scheduler**: `~/.dgas/logs/scheduler.log`
- **Database**: `/var/log/postgresql/`
- **Dashboard**: Console output (streamlit)

#### How to Search Logs

```bash
# Search for errors
grep ERROR ~/.dgas/logs/*.log

# Search for specific symbol
grep "AAPL" ~/.dgas/logs/scheduler.log

# Search recent errors
tail -100 ~/.dgas/logs/scheduler.log | grep ERROR

# Search by date
grep "2025-11-07" ~/.dgas/logs/scheduler.log
```

#### Log Levels

- **DEBUG**: Detailed information for debugging
- **INFO**: General operational information
- **WARNING**: Potential issues that don't stop operation
- **ERROR**: Errors that require attention
- **CRITICAL**: System-breaking errors

---

## Performance Monitoring

### Key Metrics

#### Database Metrics
- **Query latency**: P95 < 500ms
- **Cache hit rate**: >80%
- **Connection pool**: 5-20 connections
- **Database size**: Monitor growth

#### Calculation Metrics
- **PLdot calculation**: <50ms (cold), <10ms (cached)
- **Envelope calculation**: <60ms (cold), <10ms (cached)
- **Multi-timeframe analysis**: <150ms (cold), <40ms (cached)
- **Full pipeline**: <200ms (TARGET)

#### System Metrics
- **Prediction cycle time**: <60s for 100 symbols
- **Error rate**: <1%
- **Uptime**: >99%
- **Signal generation**: Track volume

### Monitoring Commands

```bash
# Overall performance summary
dgas monitor summary

# Database performance
dgas monitor database

# Calculation performance
dgas monitor calculations

# Recent runs
dgas monitor recent-runs --hours 24

# Performance report
dgas monitor performance-report --output report.pdf
```

### Setting Up Alerts

#### Email Alerts
Edit `~/.dgas/config.yaml`:
```yaml
alerts:
  email:
    enabled: true
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "alerts@company.com"
    recipients: ["ops@company.com"]
    thresholds:
      latency_p95_ms: 60000
      error_rate_pct: 1.0
      uptime_pct: 99.0
```

#### Discord Alerts
```yaml
alerts:
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/..."
    thresholds:
      latency_p95_ms: 60000
      error_rate_pct: 1.0
```

#### Health Check Endpoint
```bash
# Create health check script
cat > ~/dgas/healthcheck.sh << 'EOF'
#!/bin/bash
STATUS=$(dgas status --quiet)
if [ "$STATUS" != "healthy" ]; then
    echo "DGAS unhealthy: $STATUS"
    exit 1
fi
echo "DGAS healthy"
exit 0
EOF

chmod +x ~/dgas/healthcheck.sh
```

### Performance Reports

#### Generate Daily Report
```bash
dgas report daily --output /tmp/daily-$(date +%Y%m%d).pdf
```

#### Generate Weekly Report
```bash
dgas report weekly --output /tmp/weekly-$(date +%Y%U).pdf
```

#### Generate SLA Report
```bash
dgas report sla --period month --output /tmp/sla-$(date +%Y%m).pdf
```

---

## Backup and Recovery

### Database Backup

#### Automated Daily Backup
```bash
# Add to crontab
# Run daily at 2 AM
0 2 * * * /home/user/.dgas/venv/bin/python -m dgas.cli.backup
```

#### Manual Backup
```bash
# Create backup
dgas backup create --output /tmp/dgas-backup-$(date +%Y%m%d).sql

# Verify backup
dgas backup verify /tmp/dgas-backup-20251107.sql
```

#### Backup Contents
- All market data
- Calculation results
- Prediction history
- Configuration data
- Performance metrics

### Database Restore

```bash
# Restore from backup
dgas backup restore /tmp/dgas-backup-20251107.sql

# Verify restore
dgas status --check-database
```

### Configuration Backup

```bash
# Backup configuration
tar -czf ~/dgas-config-$(date +%Y%m%d).tar.gz ~/.dgas/config.yaml ~/.dgas/.env

# Restore configuration
tar -xzf ~/dgas-config-20251107.tar.gz -C ~/
```

### Recovery Procedures

#### Complete System Recovery
1. **Stop all services**:
   ```bash
   dgas scheduler stop
   pkill -f streamlit
   ```

2. **Restore database**:
   ```bash
   dgas backup restore /path/to/backup.sql
   ```

3. **Restore configuration**:
   ```bash
   tar -xzf ~/dgas-config-20251107.tar.gz -C ~/
   ```

4. **Restart services**:
   ```bash
   dgas scheduler start
   dgas-dashboard --port 8501 --no-browser &
   ```

5. **Verify recovery**:
   ```bash
   dgas status --verbose
   ```

---

## Maintenance Schedule

### Daily (Automated)

- **2:00 AM**: Database backup
- **3:00 AM**: Log rotation
- **4:00 AM**: Cache cleanup
- **5:00 AM**: Report generation

### Weekly (Manual - Sunday)

1. **Review Performance**
   - Generate weekly report
   - Analyze trends
   - Identify issues

2. **Check Database**
   - Run VACUUM ANALYZE
   - Check index usage
   - Review table sizes

3. **Review Logs**
   - Archive old logs
   - Search for recurring errors
   - Clean up temporary files

4. **Update Documentation**
   - Note any process changes
   - Update runbook if needed

**Commands**:
```bash
# Weekly maintenance
dgas maintenance weekly
```

### Monthly (Manual - First Sunday)

1. **Database Maintenance**
   - Full VACUUM
   - Reindex if needed
   - Update statistics

2. **Performance Review**
   - Analyze monthly trends
   - Compare to SLAs
   - Plan optimizations

3. **Configuration Review**
   - Check for outdated settings
   - Review thresholds
   - Update if needed

4. **Security Review**
   - Check API tokens
   - Review access logs
   - Update if needed

**Commands**:
```bash
# Monthly maintenance
dgas maintenance monthly
```

### Quarterly (Manual)

1. **Full System Review**
   - Architecture review
   - Performance optimization
   - Capacity planning

2. **Disaster Recovery Test**
   - Test backup restore
   - Verify procedures
   - Update documentation

3. **Upgrade Planning**
   - Check for updates
   - Plan upgrades
   - Test in staging

---

## Incident Response

### Severity Levels

#### Severity 1 (Critical)
- **Definition**: Complete system outage
- **Response Time**: 15 minutes
- **Escalation**: Immediate
- **Examples**:
  - Database down
  - All predictions failing
  - Complete data loss

**Response**:
1. Acknowledge incident
2. Activate incident commander
3. Implement workaround if available
4. Execute recovery procedures
5. Communicate updates every 30 minutes
6. Complete post-incident review

#### Severity 2 (High)
- **Definition**: Major functionality impaired
- **Response Time**: 1 hour
- **Escalation**: 1 hour
- **Examples**:
  - Scheduler stopped
  - High latency (>2x target)
  - Dashboard unavailable

**Response**:
1. Acknowledge within 30 minutes
2. Investigate root cause
3. Implement fix
4. Monitor for recurrence
5. Document incident

#### Severity 3 (Medium)
- **Definition**: Minor functionality issue
- **Response Time**: 4 hours
- **Escalation**: 4 hours
- **Examples**:
  - Notification failures
  - Performance degradation (<2x)
  - Data quality issues

**Response**:
1. Investigate during next business day
2. Fix or create workaround
3. Monitor
4. Document

#### Severity 4 (Low)
- **Definition**: Informational or cosmetic
- **Response Time**: Next business day
- **Escalation**: Not applicable
- **Examples**:
  - Documentation errors
  - Minor UI issues
  - Feature requests

**Response**:
1. Log issue
2. Address in regular sprint
3. Communicate resolution timeline

### Incident Response Procedures

#### Step 1: Detect and Report
- Monitoring alerts trigger
- User reports issue
- Automated health check fails

**Actions**:
1. Confirm incident
2. Assign severity
3. Create incident ticket
4. Notify stakeholders

#### Step 2: Initial Response
1. **Acknowledge** incident
2. **Assign** incident commander
3. **Gather** initial information
4. **Communicate** to stakeholders

**Template**:
```
Incident: [ID]
Severity: [1-4]
Description: [Brief description]
Status: Investigating
ETA: [Initial estimate]
Next Update: [Time]
```

#### Step 3: Investigate
1. **Gather** diagnostics
2. **Identify** root cause
3. **Determine** impact
4. **Develop** solution

**Investigation Commands**:
```bash
dgas status --verbose
dgas monitor summary
dgas logs --tail 100
dgas db-optimizer analyze
```

#### Step 4: Resolve
1. **Implement** fix
2. **Verify** resolution
3. **Monitor** for recurrence
4. **Document** fix

#### Step 5: Post-Incident
1. **Complete** incident report
2. **Conduct** post-mortem
3. **Identify** improvements
4. **Update** procedures

### Communication Templates

#### Initial Notification
```
Subject: [SEV-X] DGAS Incident - [Brief Description]

Incident ID: INC-20251107-001
Severity: [1-4]
Status: Investigating
Start Time: [Time]
Affected: [What is impacted]

We are investigating an incident affecting [system]. Next update in 30 minutes.

Incident Commander: [Name]
Contact: [Phone/Email]
```

#### Update Notification
```
Subject: [SEV-X] DGAS Incident Update - [Brief Description]

Incident ID: INC-20251107-001
Status: [Investigating/Identified/Resolved]
Progress: [What has been done]
Next Steps: [What will be done]
ETA: [Estimated resolution time]
```

#### Resolution Notification
```
Subject: [SEV-X] DGAS Incident Resolved - [Brief Description]

Incident ID: INC-20251107-001
Status: Resolved
Resolution Time: [Time]
Duration: [Total time]

Root Cause: [Brief description]
Fix Applied: [What was done]
Prevention: [What will be done to prevent recurrence]

Post-incident review scheduled: [Date/Time]
```

---

## Configuration Reference

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `EODHD_API_TOKEN` | EODHD API authentication token | Yes | - |
| `DGAS_DATABASE_URL` | PostgreSQL connection string | Yes | `postgresql://...` |
| `DGAS_DATA_DIR` | Local data directory | No | `~/.dgas/data` |
| `DGAS_LOG_LEVEL` | Logging level | No | `INFO` |
| `DGAS_CACHE_DIR` | Cache directory | No | `~/.dgas/cache` |

### Configuration File

Location: `~/.dgas/config.yaml`

```yaml
# System Configuration
system:
  timezone: "America/New_York"
  trading_session:
    market_open: "09:30"
    market_close: "16:00"
    trading_days: ["MON", "TUE", "WED", "THU", "FRI"]

# Prediction Configuration
prediction:
  interval: "30min"
  min_confidence: 0.6
  min_signal_strength: 0.5
  enabled_timeframes: ["4h", "1h", "30min"]
  symbols:
    - "AAPL"
    - "MSFT"
    - "GOOGL"
    - "AMZN"
    - "TSLA"

# Database Configuration
database:
  url: "${DGAS_DATABASE_URL}"
  pool_size: 10
  max_overflow: 20
  pool_timeout: 30

# Cache Configuration
cache:
  enabled: true
  ttl_seconds: 300
  max_size: 2000

# Notifications
notifications:
  discord:
    enabled: true
    webhook_url: "https://discord.com/api/webhooks/..."
  email:
    enabled: true
    smtp_server: "smtp.gmail.com"
    smtp_port: 587
    username: "alerts@company.com"
    recipients: ["ops@company.com"]

# Monitoring
monitoring:
  enabled: true
  performance_tracking: true
  slow_query_threshold_ms: 500
  sla:
    latency_p95_ms: 60000
    error_rate_pct: 1.0
    uptime_pct: 99.0
```

---

## Contact Information

### Primary Contacts

**On-Call Engineer**:
- Name: [Name]
- Phone: [Phone]
- Email: [Email]
- PagerDuty: [Link]

**Operations Manager**:
- Name: [Name]
- Phone: [Phone]
- Email: [Email]

**Engineering Manager**:
- Name: [Name]
- Phone: [Phone]
- Email: [Email]

### External Contacts

**EODHD Support**:
- Website: https://eodhd.com/support
- Email: support@eodhd.com

**PostgreSQL Support**:
- Documentation: https://postgresql.org/docs/
- Community: https://postgresql.org/community/

### Escalation Path

1. **On-Call Engineer** (0-15 minutes)
2. **Operations Manager** (15-30 minutes)
3. **Engineering Manager** (30-60 minutes)
4. **Director of Engineering** (1+ hours)

### After-Hours Protocol

1. **Contact on-call engineer** via PagerDuty
2. **Include severity level** in alert
3. **Provide incident ID** and description
4. **Await acknowledgment** (15 minutes for Sev 1)
5. **Escalate** if no response

---

## Appendix

### Command Reference

See `dgas --help` for all available commands.

### Additional Resources

- **User Guide**: `docs/DASHBOARD_USER_GUIDE.md`
- **API Documentation**: `docs/API_DOCUMENTATION.md`
- **Feature Tutorials**: `docs/FEATURE_TUTORIALS.md`
- **Pattern Detection**: `docs/pattern_detection_reference.md`

### Change Log

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-07 | Initial version |

---

**Document Owner**: Operations Team
**Next Review**: December 7, 2025
**Distribution**: Operations Team, DevOps, Management
