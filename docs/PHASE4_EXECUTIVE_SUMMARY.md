# Phase 4: Scheduled Prediction & Alerting
## Executive Summary

---

## Overview

Phase 4 transforms DGAS from a historical analysis tool into a **real-time predictive trading system** by implementing scheduled signal generation, multi-channel alerting, and performance monitoring.

**Timeline:** 8 weeks
**Exit Criteria:** Process new bars in ≤1 min, deliver alerts in <30s, validate calibration accuracy

---

## What We're Building

### 1. Scheduled Prediction Engine
- **Automated execution** on 30-minute intervals during market hours
- **Incremental data updates** from EODHD API
- **Multi-timeframe analysis** using existing Phase 2 calculations
- **Signal generation** with confidence scoring (0.0-1.0)
- **Database persistence** for signals and execution metrics

### 2. Multi-Channel Notification System
- **Console:** Rich formatted tables
- **Email:** HTML templates with signal details
- **Webhook:** JSON POST to user endpoints
- **Desktop:** Platform-specific toast notifications
- **Configurable thresholds** per channel (e.g., email only for confidence ≥0.7)

### 3. Performance Monitoring & Calibration
- **Real-time metrics:** Latency, throughput, error rates
- **Signal accuracy tracking:** Compare predictions to actual outcomes
- **Calibration reports:** Win rate by confidence bucket
- **SLA compliance:** Alert on performance degradation
- **Dashboard:** Live monitoring via CLI

### 4. Enhanced CLI
```bash
# Run single prediction cycle
dgas predict --symbols AAPL MSFT --interval 30min --notify email webhook

# Start scheduler daemon
dgas scheduler start --interval 30min --daemon

# View performance metrics
dgas monitor performance --lookback 24h

# Check calibration
dgas monitor calibration --date-range 2024-01-01 2024-01-31
```

---

## Architecture Components

### New Modules

```
src/dgas/prediction/
├── scheduler.py          # Interval-based execution, market hours awareness
├── engine.py             # Data refresh, indicator calc, signal generation
├── persistence.py        # Database operations for signals/metrics
├── notifications/
│   ├── router.py         # Multi-channel dispatch
│   └── adapters/
│       ├── console.py
│       ├── email.py
│       ├── webhook.py
│       └── desktop.py
└── monitoring/
    ├── performance.py    # Latency/throughput tracking
    └── calibration.py    # Signal accuracy validation
```

### Database Additions

**New Tables:**
- `prediction_runs` - Execution metadata and timing
- `generated_signals` - All trading signals with context
- `prediction_metrics` - Time-series performance data
- `scheduler_state` - Singleton for recovery/monitoring

**Migration:** `003_prediction_system.sql`

---

## Implementation Timeline

| Week | Focus Area | Deliverables |
|------|-----------|--------------|
| **1** | Foundation | Database schema, persistence layer, data refresh |
| **2** | Prediction Core | Signal generator, prediction engine, aggregation |
| **3** | Scheduler | Market hours manager, scheduler orchestration |
| **4** | Notifications | Console, email, webhook, desktop adapters |
| **5** | Monitoring | Performance tracking, calibration engine |
| **6** | CLI | Predict, scheduler, monitor commands |
| **7** | Integration | End-to-end testing, multi-symbol processing |
| **8** | Hardening | Error handling, documentation, benchmarking |

---

## Key Design Decisions

### 1. Reuse Phase 2/3 Infrastructure
- Leverages existing `MultiTimeframeCoordinator` for signal generation
- Uses `dgas.data.ingestion` for incremental updates
- Extends backtesting persistence patterns

### 2. Configuration-Driven
- YAML/JSON config files for scheduler settings
- Watchlist management via config or file
- Per-channel notification thresholds
- Strategy parameter overrides

### 3. Market-Aware Scheduling
- Automatic skip when market closed
- Interval alignment (9:30, 10:00, 10:30...)
- Trading session configuration (hours, timezone, days)
- Holiday calendar support

### 4. Graceful Degradation
- Failed cycles log errors but don't crash scheduler
- Notification failures fall back to console
- Stale data detection with alerts
- Automatic recovery from crashes

### 5. Observability First
- Comprehensive performance metrics
- Structured logging throughout
- Real-time monitoring dashboard
- Calibration validation against backtests

---

## Success Metrics

### Performance (SLA)
- ✅ New bars → signals: **≤60 seconds** (target: 45s)
- ✅ Signal → alert delivery: **<30 seconds**
- ✅ Process 100 symbols: **≤60 seconds**
- ✅ Scheduler uptime: **≥99%** during market hours
- ✅ Notification success: **≥99%**

### Accuracy (Calibration)
- ✅ Signal accuracy within **±10%** of backtest results
- ✅ Confidence correlation: **>0.7** with outcomes
- ✅ Win rate by bucket: 0.6-0.7 → ~55%, 0.7-0.8 → ~65%, 0.8+ → ~75%

### Quality
- ✅ Unit test coverage: **≥90%**
- ✅ Integration tests: Full cycle validation
- ✅ E2E test: Live EODHD sandbox
- ✅ Documentation: User guide, CLI reference, config docs

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **API reliability** | Retry logic, cached data fallback, health monitoring |
| **Scheduler crashes** | State persistence, auto-recovery, health watchdog |
| **DB performance** | Connection pooling, batch operations, query optimization |
| **False signals** | Calibration validation, confidence thresholds, user education |
| **Notification failures** | Retry per channel, fallback to console, delivery tracking |

---

## Dependencies

### External
- EODHD API (Phase 1 integration complete)
- PostgreSQL with migrations 001, 002 applied
- SMTP server for email (optional)
- Webhook endpoints (user-provided, optional)

### Internal
- Phase 1: Data ingestion, repository layer
- Phase 2: Multi-timeframe coordination, calculations
- Phase 3: Backtesting framework (for calibration validation)

---

## Configuration Example

```yaml
# prediction_config.yaml
scheduler:
  interval: "30min"
  market_hours:
    open: "09:30:00"
    close: "16:00:00"
    timezone: "America/New_York"

watchlist:
  symbols: [AAPL, MSFT, GOOGL, AMZN, TSLA]

timeframes:
  enabled: ["4h", "1h", "30min"]

signal_filters:
  min_confidence: 0.6
  min_alignment: 0.6

notifications:
  enabled_channels: [console, email, webhook]
  email:
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    min_confidence: 0.7
  webhook:
    urls: ["https://your-server.com/api/signals"]
    min_confidence: 0.6
```

---

## Post-Phase 4 Opportunities

### Phase 5 Candidates
- **ML-Enhanced Confidence Scoring:** Train models on calibration data
- **Adaptive Thresholds:** Auto-adjust based on recent accuracy
- **Portfolio Coordination:** Multi-position correlation management
- **Real-Time Streaming:** WebSocket for sub-second delivery
- **Web Dashboard:** React/Vue visualization
- **Mobile App:** iOS/Android signal monitoring

---

## Next Steps

### Immediate (Upon Approval)
1. ✅ Review and approve implementation plan
2. Create feature branch: `feature/phase4-prediction-alerting`
3. Set up development database with migrations 001-002
4. Begin Week 1: Database schema and persistence layer

### Week 1 Kickoff Tasks
- [ ] Create migration `003_prediction_system.sql`
- [ ] Implement `prediction/persistence.py` module
- [ ] Write unit tests for persistence layer
- [ ] Update `llms.txt` with Phase 4 roadmap

---

## Questions for Review

1. **Notification Channels:** Are console, email, webhook, and desktop sufficient? Need Slack/SMS?
2. **Scheduling Interval:** Default 30min acceptable? Need 15min or 1h options?
3. **Watchlist Size:** Expected number of symbols? (Affects performance tuning)
4. **Calibration Window:** 24-hour evaluation window appropriate?
5. **Configuration Format:** YAML preferred over JSON/TOML?

---

## Approval Checklist

- [ ] Architecture approach approved
- [ ] Timeline (8 weeks) acceptable
- [ ] Success criteria clear and measurable
- [ ] Risk mitigation strategies adequate
- [ ] Resource allocation confirmed
- [ ] Dependencies identified and available

---

**Status:** AWAITING APPROVAL
**Prepared:** 2024-01-XX
**Estimated Completion:** 8 weeks from start date
