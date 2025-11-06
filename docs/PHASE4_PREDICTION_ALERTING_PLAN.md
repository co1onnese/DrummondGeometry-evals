# Phase 4: Scheduled Prediction & Alerting System
## Comprehensive Implementation Plan

---

## 1. Executive Summary

### 1.1 Phase Objectives

Phase 4 delivers the real-time prediction and alerting capabilities required by PRD §2.2.2 (BR-004‒BR-006), transforming DGAS from a historical analysis tool into a predictive trading system. This phase builds upon the completed backtesting infrastructure (Phase 3) and multi-timeframe coordination (Phase 2) to provide automated, actionable trading signals.

**Primary Goals:**
- Enable scheduled calculation of Drummond Geometry indicators on live/recent market data
- Generate high-probability trading signals using multi-timeframe coordination with confidence scoring
- Deliver real-time alerts through multiple channels (console, email, webhook, desktop notifications)
- Monitor prediction accuracy and system performance for continuous calibration

**Exit Criteria:**
- New bars processed ≤1 min after availability (market data ingestion to signal generation)
- Alert delivery latency <30 seconds from signal generation
- Signal calibration validated against historical backtests (±10% accuracy variance)
- System runs continuously during market hours with <1% downtime

### 1.2 Integration with Existing System

Phase 4 builds directly on:
- **Phase 1**: EODHD data ingestion pipeline and PostgreSQL storage
- **Phase 2**: Multi-timeframe coordination, PLdot/envelope calculations, pattern detection
- **Phase 3**: Backtesting framework for strategy validation and performance metrics

Key integration points:
- Reuses `dgas.calculations.multi_timeframe.MultiTimeframeCoordinator` for signal generation
- Leverages `dgas.data.ingestion` for incremental market data updates
- Extends CLI architecture established in Phases 2 & 3
- Utilizes database schema from migrations 001 & 002

---

## 2. Architecture Overview

### 2.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PHASE 4 PREDICTION SYSTEM                            │
└─────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                           Scheduler Layer                                  │
│  prediction/scheduler.py                                                   │
│    ├─ CronScheduler (interval-based triggering)                           │
│    ├─ MarketHoursManager (trading session awareness)                      │
│    ├─ TaskQueue (ordered execution, retry logic)                          │
│    └─ HealthMonitor (watchdog, heartbeat tracking)                        │
└───────────────────────┬────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                      Prediction Engine Layer                               │
│  prediction/engine.py                                                      │
│    ├─ PredictionEngine (orchestrates full pipeline)                       │
│    │    • triggers incremental data updates                               │
│    │    • recalculates indicators for affected symbols                    │
│    │    • generates multi-timeframe signals                               │
│    │    • applies filtering/ranking logic                                 │
│    ├─ SignalGenerator (wraps MultiTimeframeCoordinator)                   │
│    │    • computes signal strength & confidence                           │
│    │    • enriches with historical pattern context                        │
│    │    • applies risk management rules                                   │
│    └─ SignalAggregator (combines multiple sources)                        │
│         • de-duplicates overlapping signals                               │
│         • ranks by confidence & timeframe alignment                       │
│         • applies user-defined filters                                    │
└───────────────────────┬────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                        Notification Layer                                  │
│  prediction/notifications/                                                 │
│    ├─ NotificationRouter (dispatches to configured channels)              │
│    ├─ adapters/                                                           │
│    │    ├─ ConsoleAdapter (rich table output)                             │
│    │    ├─ EmailAdapter (SMTP integration)                                │
│    │    ├─ WebhookAdapter (HTTP POST to user endpoints)                   │
│    │    ├─ DesktopAdapter (notify-send/toast notifications)               │
│    │    └─ SlackAdapter (optional Slack integration)                      │
│    └─ templates/ (Jinja2 templates for formatted messages)                │
└───────────────────────┬────────────────────────────────────────────────────┘
                        │
                        ↓
┌────────────────────────────────────────────────────────────────────────────┐
│                      Monitoring & Calibration                              │
│  prediction/monitoring/                                                    │
│    ├─ PerformanceTracker                                                  │
│    │    • latency metrics (data fetch, calc, notification)                │
│    │    • throughput (symbols/sec, signals/min)                           │
│    │    • error rates & retry statistics                                  │
│    ├─ CalibrationEngine                                                   │
│    │    • compare predicted signals to actual outcomes                    │
│    │    • track signal accuracy by confidence bucket                      │
│    │    • generate calibration reports                                    │
│    └─ HealthReporter                                                      │
│         • system status dashboard                                         │
│         • alert on anomalies (missed intervals, stale data)               │
│         • resource utilization tracking                                   │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│                        Persistence Layer                                   │
│  prediction/persistence.py                                                 │
│    ├─ save_prediction_run(metadata, signal_count, latency_ms)             │
│    ├─ save_generated_signals(symbol, signals[])                           │
│    ├─ get_recent_signals(symbol, lookback_hours)                          │
│    ├─ update_signal_outcome(signal_id, actual_result)                     │
│    └─ query_calibration_metrics(date_range)                               │
│                                                                            │
│  Database Tables (new):                                                   │
│    ├─ prediction_runs                                                     │
│    │    • id, run_timestamp, interval_type, symbols_processed             │
│    │    • execution_time_ms, signals_generated, status                    │
│    ├─ generated_signals                                                   │
│    │    • id, run_id, symbol, signal_timestamp                            │
│    │    • signal_type (LONG/SHORT/EXIT), confidence, strength             │
│    │    • entry_price, stop_price, target_price                           │
│    │    • timeframe_alignment, pattern_context (JSONB)                    │
│    │    • notification_sent, outcome, actual_move                         │
│    └─ prediction_metrics                                                  │
│         • id, metric_timestamp, metric_type                               │
│         • metric_value, metadata (JSONB)                                  │
└────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow Sequence

**Real-Time Prediction Cycle (30-minute interval):**

```
1. Scheduler Trigger (9:30 AM, 10:00 AM, 10:30 AM, ...)
   ↓
2. Market Hours Check (skip if market closed)
   ↓
3. Incremental Data Update
   ├─ Fetch latest bars from EODHD for watchlist symbols
   ├─ Validate data quality (gap detection, duplicate check)
   └─ Bulk upsert to market_data table
   ↓
4. Indicator Recalculation
   ├─ Identify affected symbols (new data available)
   ├─ Recalculate PLdot, envelopes, states, patterns
   ├─ Update market_states_v2, pattern_events tables
   └─ Run MultiTimeframeCoordinator for each symbol
   ↓
5. Signal Generation
   ├─ Extract high-confidence setups (alignment_score >= threshold)
   ├─ Apply entry/exit rules from backtested strategies
   ├─ Calculate position sizing, stop loss, targets
   └─ Persist to generated_signals table
   ↓
6. Signal Filtering & Ranking
   ├─ Remove duplicate/conflicting signals
   ├─ Rank by confidence * strength * timeframe alignment
   ├─ Apply user filters (min confidence, pattern types, etc.)
   └─ Prepare notification payload
   ↓
7. Multi-Channel Notification
   ├─ Console: Rich table with top signals
   ├─ Email: HTML report with chart links
   ├─ Webhook: JSON payload to user endpoints
   ├─ Desktop: Toast notification for urgent signals
   └─ Log delivery status
   ↓
8. Performance Logging
   ├─ Record execution time per stage
   ├─ Track signal counts, error rates
   └─ Update prediction_runs table
   ↓
9. Calibration Update (periodic)
   ├─ Compare N-periods-ago signals to actual price moves
   ├─ Update accuracy metrics by confidence bucket
   └─ Flag degraded performance for review
```

---

## 3. Detailed Module Specifications

### 3.1 Scheduler Module (`prediction/scheduler.py`)

**Purpose:** Orchestrate periodic execution of the prediction pipeline with market-awareness.

#### 3.1.1 Core Components

**`MarketHoursManager`**
```python
@dataclass(frozen=True)
class TradingSession:
    market_open: time  # 09:30:00
    market_close: time  # 16:00:00
    timezone: str  # "America/New_York"
    trading_days: list[str]  # ["MON", "TUE", "WED", "THU", "FRI"]

class MarketHoursManager:
    def __init__(self, session: TradingSession):
        """Initialize with trading session configuration."""

    def is_market_open(self, dt: datetime | None = None) -> bool:
        """Check if market is currently open (or at specific datetime)."""

    def next_market_open(self) -> datetime:
        """Calculate next market open datetime."""

    def next_market_close(self) -> datetime:
        """Calculate next market close datetime."""

    def get_session_intervals(
        self,
        interval: str = "30min",
        include_pre_market: bool = False
    ) -> list[datetime]:
        """Generate list of interval timestamps for current/next session."""
```

**`SchedulerConfig`**
```python
@dataclass
class SchedulerConfig:
    """Configuration for prediction scheduler."""
    interval: str = "30min"  # Update frequency
    symbols: list[str]  # Watchlist for monitoring
    enabled_timeframes: list[str] = ["4h", "1h", "30min"]

    # Signal filtering
    min_confidence: float = 0.6
    min_signal_strength: float = 0.5
    enabled_patterns: list[str] | None = None  # None = all patterns

    # Notification settings
    notification_channels: list[str] = ["console"]
    notification_filters: dict[str, Any] = {}

    # Performance settings
    max_concurrent_symbols: int = 10
    timeout_seconds: int = 120
    retry_attempts: int = 3

    # Data refresh
    incremental_update: bool = True
    lookback_buffer_days: int = 2
```

**`PredictionScheduler`**
```python
class PredictionScheduler:
    """Main scheduler orchestrating periodic predictions."""

    def __init__(
        self,
        config: SchedulerConfig,
        engine: PredictionEngine,
        market_hours: MarketHoursManager,
    ):
        """Initialize scheduler with dependencies."""

    def start(self, daemon: bool = True) -> None:
        """Start scheduler loop (blocking or daemon thread)."""

    def stop(self) -> None:
        """Graceful shutdown with in-flight task completion."""

    def run_once(self) -> PredictionRunResult:
        """Execute single prediction cycle (for testing/manual triggers)."""

    def schedule_next_run(self) -> datetime:
        """Calculate next execution time based on interval + market hours."""

    def _execute_cycle(self) -> PredictionRunResult:
        """Internal: execute full prediction pipeline."""

    def _should_run(self) -> bool:
        """Check if conditions are met for running (market open, not already running)."""
```

#### 3.1.2 Implementation Details

- **Interval Alignment:** Scheduler aligns to market intervals (e.g., 9:30, 10:00, 10:30 for 30min)
- **Graceful Degradation:** If a cycle takes longer than interval, skip overlap and log warning
- **Error Handling:** Failed cycles log errors, send alerts, but don't crash scheduler
- **State Persistence:** Track last successful run timestamp in DB for recovery
- **Signal Handling:** Respond to SIGTERM/SIGINT for clean shutdown

---

### 3.2 Prediction Engine (`prediction/engine.py`)

**Purpose:** Execute the core prediction logic: data refresh → calculation → signal generation.

#### 3.2.1 Core Components

**`PredictionEngine`**
```python
@dataclass(frozen=True)
class PredictionRunResult:
    """Result of a single prediction cycle."""
    run_id: int
    timestamp: datetime
    symbols_processed: int
    signals_generated: int
    execution_time_ms: int
    errors: list[str]
    status: str  # "SUCCESS", "PARTIAL", "FAILED"

class PredictionEngine:
    """Orchestrates data refresh, calculation, and signal generation."""

    def __init__(
        self,
        settings: Settings,
        signal_generator: SignalGenerator,
        persistence: PredictionPersistence,
    ):
        """Initialize with dependencies."""

    def execute_prediction_cycle(
        self,
        symbols: list[str],
        interval: str,
        timeframes: list[str],
    ) -> PredictionRunResult:
        """
        Main entry point: run full prediction cycle.

        Steps:
        1. Refresh market data (incremental update)
        2. Recalculate indicators for updated symbols
        3. Generate signals via SignalGenerator
        4. Persist signals and run metadata
        5. Return results for notification dispatch
        """

    def _refresh_market_data(
        self,
        symbols: list[str],
        interval: str,
    ) -> dict[str, int]:
        """
        Incrementally update market data for symbols.
        Returns: {symbol: bars_added}
        """

    def _recalculate_indicators(
        self,
        symbols: list[str],
        interval: str,
    ) -> dict[str, bool]:
        """
        Recalculate Drummond indicators for symbols with new data.
        Returns: {symbol: success}
        """

    def _generate_signals(
        self,
        symbols: list[str],
        timeframes: list[str],
    ) -> list[GeneratedSignal]:
        """
        Generate trading signals using SignalGenerator.
        Returns: List of signals with confidence scores.
        """
```

**`SignalGenerator`**
```python
@dataclass(frozen=True)
class GeneratedSignal:
    """A trading signal generated by the prediction system."""
    symbol: str
    timestamp: datetime
    signal_type: str  # "LONG", "SHORT", "EXIT_LONG", "EXIT_SHORT"

    # Entry details
    entry_price: Decimal
    stop_loss: Decimal
    target_price: Decimal
    confidence: float  # 0.0-1.0
    signal_strength: float  # 0.0-1.0

    # Context
    timeframe_alignment: float  # 0.0-1.0 (HTF-Trading TF agreement)
    pattern_context: dict[str, Any]  # Triggering patterns, market state
    risk_reward_ratio: float

    # Multi-timeframe details
    htf_trend: str  # "UP", "DOWN", "NEUTRAL"
    trading_tf_state: str  # Market state at trading TF
    confluence_zones: int  # Number of supporting confluence zones

class SignalGenerator:
    """Wraps multi-timeframe coordination to generate actionable signals."""

    def __init__(
        self,
        coordinator: MultiTimeframeCoordinator,
        strategy_config: dict[str, Any],
    ):
        """Initialize with coordinator and strategy parameters."""

    def generate_signals(
        self,
        symbol: str,
        htf_data: TimeframeData,
        trading_tf_data: TimeframeData,
        ltf_data: TimeframeData | None = None,
    ) -> list[GeneratedSignal]:
        """
        Generate signals for a symbol using multi-timeframe analysis.

        Logic:
        1. Run coordinator.analyze() to get MultiTimeframeAnalysis
        2. Apply strategy rules to determine signal type
        3. Calculate entry/stop/target using envelope bands + support/resistance
        4. Assign confidence based on alignment + pattern strength
        5. Return list of signals (typically 0-2 per symbol)
        """

    def _apply_entry_rules(
        self,
        analysis: MultiTimeframeAnalysis
    ) -> str | None:
        """
        Determine if entry signal should be generated.

        Entry Rules (Multi-Timeframe Strategy):
        - LONG: HTF trend UP + trading TF alignment ≥ 0.7 + price near support
        - SHORT: HTF trend DOWN + trading TF alignment ≥ 0.7 + price near resistance
        - EXIT: Timeframe alignment breaks below 0.4 OR price hits target/stop
        """

    def _calculate_levels(
        self,
        signal_type: str,
        analysis: MultiTimeframeAnalysis,
    ) -> tuple[Decimal, Decimal, Decimal]:
        """
        Calculate entry, stop, and target prices.

        Returns: (entry_price, stop_loss, target_price)
        """

    def _calculate_confidence(
        self,
        analysis: MultiTimeframeAnalysis,
    ) -> float:
        """
        Calculate signal confidence score (0.0-1.0).

        Factors:
        - Timeframe alignment strength (30%)
        - Pattern confluence (20%)
        - HTF trend strength (25%)
        - Confluence zone count (15%)
        - Historical pattern success rate (10%)
        """
```

#### 3.2.2 Signal Filtering & Aggregation

**`SignalAggregator`**
```python
class SignalAggregator:
    """De-duplicates and ranks signals for notification."""

    def aggregate_signals(
        self,
        signals: list[GeneratedSignal],
        filters: dict[str, Any],
    ) -> list[GeneratedSignal]:
        """
        Filter and rank signals.

        Steps:
        1. Remove duplicates (same symbol + signal_type within time window)
        2. Apply user filters (min confidence, enabled patterns, etc.)
        3. Rank by composite score: confidence * strength * alignment
        4. Return top N signals
        """

    def _detect_duplicates(
        self,
        signals: list[GeneratedSignal],
        time_window_minutes: int = 60,
    ) -> list[GeneratedSignal]:
        """Remove signals for same symbol+direction within time window."""

    def _apply_filters(
        self,
        signals: list[GeneratedSignal],
        filters: dict[str, Any],
    ) -> list[GeneratedSignal]:
        """Apply user-defined filters."""

    def _rank_signals(
        self,
        signals: list[GeneratedSignal],
    ) -> list[GeneratedSignal]:
        """Sort by composite score descending."""
```

---

### 3.3 Notification System (`prediction/notifications/`)

**Purpose:** Deliver signals to users through multiple channels with template-based formatting.

#### 3.3.1 Core Components

**`NotificationRouter`**
```python
@dataclass
class NotificationConfig:
    """Configuration for notification delivery."""
    enabled_channels: list[str]  # ["console", "email", "webhook"]

    # Channel-specific configs
    email_config: dict[str, Any] | None = None
    webhook_urls: list[str] = []
    slack_webhook: str | None = None

    # Filtering
    min_confidence_for_email: float = 0.7
    min_confidence_for_webhook: float = 0.6
    urgent_confidence_threshold: float = 0.8  # Desktop notifications

    # Formatting
    template_path: Path | None = None
    include_charts: bool = False

class NotificationRouter:
    """Routes signals to configured notification channels."""

    def __init__(
        self,
        config: NotificationConfig,
        adapters: dict[str, NotificationAdapter],
    ):
        """Initialize with config and channel adapters."""

    def send_notifications(
        self,
        signals: list[GeneratedSignal],
        run_metadata: dict[str, Any],
    ) -> dict[str, bool]:
        """
        Send notifications for signals through all enabled channels.

        Returns: {channel: success} status map
        """

    def _should_notify(
        self,
        signal: GeneratedSignal,
        channel: str,
    ) -> bool:
        """Check if signal meets threshold for channel."""
```

**`NotificationAdapter` (Abstract Base)**
```python
class NotificationAdapter(ABC):
    """Base class for notification channel implementations."""

    @abstractmethod
    def send(
        self,
        signals: list[GeneratedSignal],
        metadata: dict[str, Any],
    ) -> bool:
        """Send notifications. Return True on success."""

    @abstractmethod
    def format_message(
        self,
        signals: list[GeneratedSignal],
    ) -> Any:
        """Format signals for channel (string, dict, etc.)."""
```

#### 3.3.2 Channel Implementations

**Console Adapter**
```python
class ConsoleAdapter(NotificationAdapter):
    """Rich console table output."""

    def send(self, signals, metadata) -> bool:
        """Print formatted table to stdout using Rich."""
        table = Table(title="🎯 New Trading Signals")
        table.add_column("Symbol", style="cyan")
        table.add_column("Signal", style="bold")
        table.add_column("Entry", style="green")
        table.add_column("Stop", style="red")
        table.add_column("Target", style="blue")
        table.add_column("Confidence", style="yellow")
        table.add_column("R:R", justify="right")

        for signal in signals:
            # Add rows with conditional formatting
            ...

        console.print(table)
        return True
```

**Email Adapter**
```python
class EmailAdapter(NotificationAdapter):
    """SMTP email delivery with HTML formatting."""

    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        username: str,
        password: str,
        from_addr: str,
        to_addrs: list[str],
        template_path: Path,
    ):
        """Initialize SMTP connection details."""

    def send(self, signals, metadata) -> bool:
        """Send HTML email with signal details."""
        html_content = self._render_template(signals, metadata)
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"DGAS Signals: {len(signals)} New Setups"
        msg["From"] = self.from_addr
        msg["To"] = ", ".join(self.to_addrs)

        msg.attach(MIMEText(html_content, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            return True
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False
```

**Webhook Adapter**
```python
class WebhookAdapter(NotificationAdapter):
    """HTTP POST to user-defined endpoints."""

    def __init__(self, urls: list[str], timeout: int = 10):
        """Initialize with webhook URLs."""
        self.urls = urls
        self.timeout = timeout

    def send(self, signals, metadata) -> bool:
        """POST JSON payload to all configured URLs."""
        payload = self.format_message(signals)

        success = True
        for url in self.urls:
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
                response.raise_for_status()
            except Exception as e:
                logger.error(f"Webhook POST to {url} failed: {e}")
                success = False

        return success

    def format_message(self, signals) -> dict:
        """Convert signals to JSON-serializable dict."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signals": [
                {
                    "symbol": s.symbol,
                    "type": s.signal_type,
                    "entry": float(s.entry_price),
                    "stop": float(s.stop_loss),
                    "target": float(s.target_price),
                    "confidence": s.confidence,
                    "strength": s.signal_strength,
                    "pattern_context": s.pattern_context,
                }
                for s in signals
            ],
        }
```

**Desktop Adapter**
```python
class DesktopAdapter(NotificationAdapter):
    """Desktop toast notifications (platform-specific)."""

    def send(self, signals, metadata) -> bool:
        """Show desktop notification for urgent signals."""
        if not signals:
            return True

        # Only notify for highest-confidence signals
        urgent = [s for s in signals if s.confidence >= 0.8]
        if not urgent:
            return True

        for signal in urgent[:3]:  # Max 3 notifications at once
            title = f"{signal.symbol} {signal.signal_type}"
            body = (
                f"Entry: ${signal.entry_price} | "
                f"Stop: ${signal.stop_loss} | "
                f"Confidence: {signal.confidence:.0%}"
            )

            try:
                # Platform-specific notification
                if sys.platform == "linux":
                    subprocess.run(["notify-send", title, body])
                elif sys.platform == "darwin":
                    subprocess.run(["osascript", "-e",
                                  f'display notification "{body}" with title "{title}"'])
                elif sys.platform == "win32":
                    # Use Windows toast library
                    from win10toast import ToastNotifier
                    toaster = ToastNotifier()
                    toaster.show_toast(title, body, duration=10)
            except Exception as e:
                logger.error(f"Desktop notification failed: {e}")
                return False

        return True
```

---

### 3.4 Monitoring & Calibration (`prediction/monitoring/`)

**Purpose:** Track system performance and validate prediction accuracy.

#### 3.4.1 Performance Tracker

```python
@dataclass(frozen=True)
class LatencyMetrics:
    """Latency measurements for prediction cycle stages."""
    data_fetch_ms: int
    indicator_calc_ms: int
    signal_generation_ms: int
    notification_ms: int
    total_ms: int

@dataclass(frozen=True)
class ThroughputMetrics:
    """Throughput measurements."""
    symbols_processed: int
    signals_generated: int
    execution_time_ms: int
    symbols_per_second: float

class PerformanceTracker:
    """Tracks and reports system performance metrics."""

    def __init__(self, persistence: PredictionPersistence):
        """Initialize with database persistence."""

    def track_cycle(
        self,
        run_id: int,
        latency: LatencyMetrics,
        throughput: ThroughputMetrics,
        errors: list[str],
    ) -> None:
        """Record metrics for a prediction cycle."""

    def get_performance_summary(
        self,
        lookback_hours: int = 24,
    ) -> dict[str, Any]:
        """
        Get performance summary statistics.

        Returns:
        {
            "avg_latency_ms": float,
            "p95_latency_ms": float,
            "avg_throughput": float,
            "error_rate": float,
            "uptime_pct": float,
        }
        """

    def check_sla_compliance(self) -> bool:
        """
        Verify system meets SLA requirements.

        SLA Targets:
        - P95 total latency ≤ 60 seconds
        - Error rate ≤ 1%
        - Uptime ≥ 99% during market hours
        """
```

#### 3.4.2 Calibration Engine

```python
@dataclass(frozen=True)
class SignalOutcome:
    """Actual outcome of a generated signal."""
    signal_id: int
    evaluation_timestamp: datetime

    # Price movement
    actual_high: Decimal  # Highest price within window
    actual_low: Decimal   # Lowest price within window
    close_price: Decimal  # Closing price at window end

    # Outcome classification
    hit_target: bool
    hit_stop: bool
    outcome: str  # "WIN", "LOSS", "NEUTRAL", "PENDING"
    pnl_pct: float  # % gain/loss if signal was taken

class CalibrationEngine:
    """Validates signal accuracy and tracks calibration metrics."""

    def __init__(
        self,
        persistence: PredictionPersistence,
        evaluation_window_hours: int = 24,
    ):
        """Initialize with evaluation parameters."""

    def evaluate_signal(
        self,
        signal: GeneratedSignal,
        actual_prices: list[IntervalData],
    ) -> SignalOutcome:
        """
        Evaluate signal against actual price movement.

        Logic:
        1. Find price data for N hours after signal timestamp
        2. Check if stop or target was hit
        3. Calculate actual P&L if position was taken
        4. Classify outcome
        """

    def batch_evaluate(
        self,
        lookback_hours: int = 24,
    ) -> list[SignalOutcome]:
        """
        Evaluate all signals from lookback period.
        Returns: List of outcomes ready for persistence.
        """

    def get_calibration_report(
        self,
        date_range: tuple[datetime, datetime] | None = None,
    ) -> CalibrationReport:
        """
        Generate calibration report showing signal accuracy.

        Metrics by confidence bucket:
        - Win rate
        - Avg P&L
        - Target hit rate
        - Stop hit rate
        """

@dataclass(frozen=True)
class CalibrationReport:
    """Calibration metrics report."""
    date_range: tuple[datetime, datetime]
    total_signals: int
    evaluated_signals: int

    # Overall metrics
    win_rate: float
    avg_pnl_pct: float
    target_hit_rate: float
    stop_hit_rate: float

    # By confidence bucket
    by_confidence: dict[str, dict[str, float]]
    # e.g., {"0.6-0.7": {"win_rate": 0.58, "avg_pnl": 0.02}, ...}

    # By signal type
    by_signal_type: dict[str, dict[str, float]]
    # e.g., {"LONG": {"win_rate": 0.62, ...}, "SHORT": {...}}
```

---

## 4. Database Schema Additions

### 4.1 Migration: `003_prediction_system.sql`

```sql
-- Prediction run tracking
CREATE TABLE prediction_runs (
    id BIGSERIAL PRIMARY KEY,
    run_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    interval_type VARCHAR(20) NOT NULL,

    -- Execution metrics
    symbols_requested INT NOT NULL,
    symbols_processed INT NOT NULL,
    signals_generated INT NOT NULL,
    execution_time_ms INT NOT NULL,
    status VARCHAR(20) NOT NULL,  -- SUCCESS, PARTIAL, FAILED

    -- Latency breakdown (milliseconds)
    data_fetch_ms INT,
    indicator_calc_ms INT,
    signal_generation_ms INT,
    notification_ms INT,

    -- Error tracking
    errors TEXT[],

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT prediction_runs_status_check
        CHECK (status IN ('SUCCESS', 'PARTIAL', 'FAILED'))
);

CREATE INDEX idx_prediction_runs_timestamp
    ON prediction_runs(run_timestamp DESC);
CREATE INDEX idx_prediction_runs_status
    ON prediction_runs(status, run_timestamp DESC);

-- Generated trading signals
CREATE TABLE generated_signals (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES prediction_runs(id) ON DELETE CASCADE,

    -- Symbol & timing
    symbol VARCHAR(10) NOT NULL,
    signal_timestamp TIMESTAMPTZ NOT NULL,

    -- Signal details
    signal_type VARCHAR(20) NOT NULL,  -- LONG, SHORT, EXIT_LONG, EXIT_SHORT
    entry_price NUMERIC(12,6) NOT NULL,
    stop_loss NUMERIC(12,6) NOT NULL,
    target_price NUMERIC(12,6) NOT NULL,

    -- Confidence & strength
    confidence NUMERIC(4,3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    signal_strength NUMERIC(4,3) NOT NULL CHECK (signal_strength BETWEEN 0 AND 1),
    timeframe_alignment NUMERIC(4,3) NOT NULL CHECK (timeframe_alignment BETWEEN 0 AND 1),
    risk_reward_ratio NUMERIC(6,2),

    -- Context
    htf_trend VARCHAR(10),  -- UP, DOWN, NEUTRAL
    trading_tf_state VARCHAR(30),  -- Market state at trading timeframe
    confluence_zones INT DEFAULT 0,
    pattern_context JSONB,  -- {patterns: [...], indicators: {...}}

    -- Notification tracking
    notification_sent BOOLEAN DEFAULT FALSE,
    notification_channels TEXT[],
    notification_timestamp TIMESTAMPTZ,

    -- Outcome tracking (populated later)
    outcome VARCHAR(20),  -- WIN, LOSS, NEUTRAL, PENDING
    actual_high NUMERIC(12,6),
    actual_low NUMERIC(12,6),
    actual_close NUMERIC(12,6),
    pnl_pct NUMERIC(8,4),
    evaluated_at TIMESTAMPTZ,

    created_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT generated_signals_type_check
        CHECK (signal_type IN ('LONG', 'SHORT', 'EXIT_LONG', 'EXIT_SHORT')),
    CONSTRAINT generated_signals_outcome_check
        CHECK (outcome IN ('WIN', 'LOSS', 'NEUTRAL', 'PENDING', NULL))
);

CREATE INDEX idx_generated_signals_symbol_timestamp
    ON generated_signals(symbol, signal_timestamp DESC);
CREATE INDEX idx_generated_signals_run
    ON generated_signals(run_id);
CREATE INDEX idx_generated_signals_confidence
    ON generated_signals(confidence DESC, signal_timestamp DESC);
CREATE INDEX idx_generated_signals_pending_evaluation
    ON generated_signals(signal_timestamp)
    WHERE outcome IS NULL AND signal_timestamp < NOW() - INTERVAL '1 hour';

-- Performance & calibration metrics
CREATE TABLE prediction_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_type VARCHAR(50) NOT NULL,  -- latency_p95, throughput_avg, win_rate, etc.
    metric_value NUMERIC(12,4) NOT NULL,

    -- Optional aggregation metadata
    aggregation_period VARCHAR(20),  -- hourly, daily, weekly
    metadata JSONB,  -- {symbol: "AAPL", confidence_bucket: "0.7-0.8", ...}

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_prediction_metrics_type_timestamp
    ON prediction_metrics(metric_type, metric_timestamp DESC);
CREATE INDEX idx_prediction_metrics_timestamp
    ON prediction_metrics(metric_timestamp DESC);

-- Scheduler state (for recovery and monitoring)
CREATE TABLE scheduler_state (
    id SERIAL PRIMARY KEY,
    last_run_timestamp TIMESTAMPTZ,
    next_scheduled_run TIMESTAMPTZ,
    status VARCHAR(20) DEFAULT 'IDLE',  -- IDLE, RUNNING, STOPPED, ERROR
    current_run_id BIGINT REFERENCES prediction_runs(id),
    error_message TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT scheduler_state_singleton CHECK (id = 1)
);

-- Insert singleton row
INSERT INTO scheduler_state (id) VALUES (1);
```

### 4.2 Schema Rationale

**`prediction_runs` Table:**
- Tracks each scheduled execution with detailed timing breakdown
- Enables performance monitoring and bottleneck identification
- Status field allows filtering for failed runs requiring investigation

**`generated_signals` Table:**
- Core storage for all generated trading signals
- Includes rich context (patterns, confluence zones) for post-analysis
- Outcome tracking enables calibration validation
- JSONB pattern_context allows flexible storage of triggering conditions

**`prediction_metrics` Table:**
- Time-series storage for aggregated metrics
- Supports dashboard visualization and trend analysis
- Flexible metadata JSONB for dimensional slicing

**`scheduler_state` Table:**
- Singleton table tracking scheduler status
- Enables recovery after crashes (resume from last successful run)
- Provides health monitoring endpoint

---

## 5. CLI Integration

### 5.1 New CLI Commands

#### `dgas predict` - Run Single Prediction Cycle

```bash
# Run prediction for watchlist symbols
python -m dgas predict \
    --symbols AAPL MSFT GOOGL \
    --interval 30min \
    --timeframes 4h 1h 30min \
    --min-confidence 0.6 \
    --notify console email \
    --save

# Run with custom filters
python -m dgas predict \
    --symbols @watchlist.txt \
    --interval 1h \
    --min-confidence 0.7 \
    --min-alignment 0.6 \
    --patterns PLDOT_PUSH EXHAUST \
    --notify webhook \
    --webhook-url https://my-server.com/signals

# Dry run (no notifications or persistence)
python -m dgas predict \
    --symbols AAPL \
    --interval 30min \
    --dry-run \
    --output-format detailed
```

**CLI Arguments:**
```python
predict_parser = subparsers.add_parser(
    "predict",
    help="Generate trading signals from current market data",
)
predict_parser.add_argument(
    "symbols",
    nargs="+",
    help="Symbols to analyze (or @file.txt for watchlist)",
)
predict_parser.add_argument(
    "--interval",
    default="30min",
    help="Primary interval for analysis (default: 30min)",
)
predict_parser.add_argument(
    "--timeframes",
    nargs="+",
    default=["4h", "1h", "30min"],
    help="Timeframes for multi-TF analysis (default: 4h 1h 30min)",
)
predict_parser.add_argument(
    "--min-confidence",
    type=float,
    default=0.6,
    help="Minimum signal confidence threshold (default: 0.6)",
)
predict_parser.add_argument(
    "--min-alignment",
    type=float,
    default=0.5,
    help="Minimum timeframe alignment score (default: 0.5)",
)
predict_parser.add_argument(
    "--patterns",
    nargs="*",
    help="Filter to specific patterns (omit for all)",
)
predict_parser.add_argument(
    "--notify",
    nargs="+",
    choices=["console", "email", "webhook", "desktop"],
    default=["console"],
    help="Notification channels to use",
)
predict_parser.add_argument(
    "--webhook-url",
    action="append",
    help="Webhook URL(s) for signal delivery",
)
predict_parser.add_argument(
    "--save",
    action="store_true",
    default=True,
    help="Save signals to database (default: True)",
)
predict_parser.add_argument(
    "--no-save",
    action="store_true",
    help="Disable database persistence",
)
predict_parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Run analysis without notifications or persistence",
)
predict_parser.add_argument(
    "--output-format",
    choices=["summary", "detailed", "json"],
    default="summary",
)
```

#### `dgas scheduler` - Manage Prediction Scheduler

```bash
# Start scheduler in foreground
python -m dgas scheduler start --interval 30min --foreground

# Start scheduler as daemon
python -m dgas scheduler start --interval 30min --daemon --log scheduler.log

# Stop running scheduler
python -m dgas scheduler stop

# Check scheduler status
python -m dgas scheduler status

# View scheduler configuration
python -m dgas scheduler config

# Update scheduler configuration
python -m dgas scheduler config \
    --set interval=1h \
    --set symbols=AAPL,MSFT,GOOGL \
    --set min-confidence=0.7
```

**CLI Arguments:**
```python
scheduler_parser = subparsers.add_parser(
    "scheduler",
    help="Manage prediction scheduler",
)
scheduler_subparsers = scheduler_parser.add_subparsers(dest="scheduler_command")

# Start command
start_parser = scheduler_subparsers.add_parser("start", help="Start scheduler")
start_parser.add_argument("--interval", default="30min")
start_parser.add_argument("--symbols", help="Comma-separated symbol list or @file")
start_parser.add_argument("--config", type=Path, help="Config file (YAML/JSON)")
start_parser.add_argument("--foreground", action="store_true", help="Run in foreground")
start_parser.add_argument("--daemon", action="store_true", help="Run as daemon")
start_parser.add_argument("--log", type=Path, help="Log file path")
start_parser.add_argument("--pid-file", type=Path, help="PID file for daemon")

# Stop command
stop_parser = scheduler_subparsers.add_parser("stop", help="Stop scheduler")
stop_parser.add_argument("--pid-file", type=Path, help="PID file to read")

# Status command
status_parser = scheduler_subparsers.add_parser("status", help="Show scheduler status")
status_parser.add_argument("--verbose", action="store_true")

# Config command
config_parser = scheduler_subparsers.add_parser("config", help="Manage configuration")
config_parser.add_argument("--show", action="store_true", help="Display current config")
config_parser.add_argument("--set", action="append", help="Set config value (key=value)")
config_parser.add_argument("--file", type=Path, help="Load config from file")
```

#### `dgas monitor` - View Metrics & Calibration

```bash
# Show performance summary
python -m dgas monitor performance --lookback 24h

# Show calibration metrics
python -m dgas monitor calibration --date-range 2024-01-01 2024-01-31

# Show recent signals
python -m dgas monitor signals --limit 50 --min-confidence 0.7

# Export metrics to CSV
python -m dgas monitor performance --export metrics.csv

# Real-time dashboard (updates every 30s)
python -m dgas monitor dashboard --refresh 30
```

**CLI Arguments:**
```python
monitor_parser = subparsers.add_parser(
    "monitor",
    help="View performance metrics and calibration data",
)
monitor_subparsers = monitor_parser.add_subparsers(dest="monitor_command")

# Performance command
perf_parser = monitor_subparsers.add_parser("performance")
perf_parser.add_argument("--lookback", default="24h", help="Lookback window")
perf_parser.add_argument("--export", type=Path, help="Export to CSV")

# Calibration command
calib_parser = monitor_subparsers.add_parser("calibration")
calib_parser.add_argument("--date-range", nargs=2, help="Start and end dates")
calib_parser.add_argument("--by-confidence", action="store_true")
calib_parser.add_argument("--by-signal-type", action="store_true")

# Signals command
signals_parser = monitor_subparsers.add_parser("signals")
signals_parser.add_argument("--limit", type=int, default=20)
signals_parser.add_argument("--min-confidence", type=float)
signals_parser.add_argument("--symbol", help="Filter by symbol")
signals_parser.add_argument("--outcome", choices=["WIN", "LOSS", "NEUTRAL", "PENDING"])

# Dashboard command
dashboard_parser = monitor_subparsers.add_parser("dashboard")
dashboard_parser.add_argument("--refresh", type=int, default=60, help="Refresh seconds")
```

### 5.2 Configuration File Format

**`prediction_config.yaml` Example:**
```yaml
# Prediction configuration
scheduler:
  interval: "30min"
  market_hours:
    open: "09:30:00"
    close: "16:00:00"
    timezone: "America/New_York"
    trading_days: ["MON", "TUE", "WED", "THU", "FRI"]

  performance:
    max_concurrent_symbols: 10
    timeout_seconds: 120
    retry_attempts: 3

watchlist:
  symbols:
    - AAPL
    - MSFT
    - GOOGL
    - AMZN
    - TSLA
  # Or load from file:
  # symbols_file: "watchlists/tech_stocks.txt"

timeframes:
  enabled:
    - "4h"
    - "1h"
    - "30min"
  higher_timeframe: "4h"
  trading_timeframe: "1h"

signal_filters:
  min_confidence: 0.6
  min_signal_strength: 0.5
  min_alignment: 0.6
  enabled_patterns:
    - PLDOT_PUSH
    - PLDOT_REFRESH
    - EXHAUST
    - C_WAVE
  # null = all patterns enabled

notifications:
  enabled_channels:
    - console
    - email
    - webhook

  console:
    output_format: "summary"
    max_signals_displayed: 10

  email:
    smtp_host: "smtp.gmail.com"
    smtp_port: 587
    username: "your-email@gmail.com"
    password_env: "DGAS_EMAIL_PASSWORD"  # Load from env var
    from_addr: "dgas-alerts@yourdomain.com"
    to_addrs:
      - "trader@example.com"
    min_confidence: 0.7
    template: "templates/email_signal.html"

  webhook:
    urls:
      - "https://your-server.com/api/signals"
      - "https://backup-server.com/webhooks/dgas"
    min_confidence: 0.6
    timeout: 10

  desktop:
    enabled: true
    min_confidence: 0.8  # Only urgent signals

data_refresh:
  incremental_update: true
  lookback_buffer_days: 2

monitoring:
  calibration:
    evaluation_window_hours: 24
    batch_evaluate_interval: "1h"

  performance:
    track_latency: true
    track_throughput: true
    sla_alert_email: "ops@example.com"
```

---

## 6. Testing Strategy

### 6.1 Unit Tests

**Location:** `tests/prediction/`

#### Test Modules

**`test_scheduler.py`**
```python
def test_market_hours_manager_open_hours():
    """Test market open detection during trading hours."""

def test_market_hours_manager_weekend():
    """Test market closed detection on weekends."""

def test_market_hours_manager_next_open():
    """Test calculation of next market open time."""

def test_scheduler_interval_alignment():
    """Test scheduler aligns to market intervals (9:30, 10:00, etc.)."""

def test_scheduler_skip_overlap():
    """Test scheduler skips cycle if previous still running."""

def test_scheduler_graceful_shutdown():
    """Test scheduler stops cleanly on SIGTERM."""
```

**`test_prediction_engine.py`**
```python
def test_data_refresh_incremental(mock_client):
    """Test incremental data update fetches only new bars."""

def test_indicator_recalculation(mock_persistence):
    """Test indicators recalculated only for updated symbols."""

def test_signal_generation_confidence_threshold():
    """Test signals filtered by confidence threshold."""

def test_signal_generation_alignment_threshold():
    """Test signals filtered by timeframe alignment."""

def test_execute_cycle_end_to_end(mock_dependencies):
    """Integration test: full prediction cycle with mocked dependencies."""
```

**`test_signal_generator.py`**
```python
def test_entry_rules_long_signal():
    """Test LONG signal generated when HTF trend UP + alignment high."""

def test_entry_rules_short_signal():
    """Test SHORT signal generated when HTF trend DOWN + alignment high."""

def test_entry_rules_no_signal_low_alignment():
    """Test no signal when timeframe alignment below threshold."""

def test_calculate_levels_long():
    """Test entry/stop/target calculation for LONG signal."""

def test_calculate_confidence_score():
    """Test confidence score calculation uses correct weights."""

def test_signal_generator_multiple_signals():
    """Test multiple signals generated when conditions met."""
```

**`test_notifications.py`**
```python
def test_console_adapter_format():
    """Test console output formatting with Rich."""

def test_email_adapter_send(mock_smtp):
    """Test email sending with mocked SMTP."""

def test_webhook_adapter_retry(requests_mock):
    """Test webhook retries on failure."""

def test_notification_router_channel_filtering():
    """Test signals filtered by confidence per channel."""

def test_notification_router_multi_channel():
    """Test simultaneous delivery to multiple channels."""
```

**`test_monitoring.py`**
```python
def test_performance_tracker_latency():
    """Test latency tracking and aggregation."""

def test_performance_tracker_sla_check():
    """Test SLA compliance validation."""

def test_calibration_evaluate_win():
    """Test signal evaluation identifies winning trade."""

def test_calibration_evaluate_loss():
    """Test signal evaluation identifies losing trade."""

def test_calibration_report_by_confidence():
    """Test calibration report grouped by confidence buckets."""
```

### 6.2 Integration Tests

**`test_cli_predict.py`**
```python
def test_predict_command_basic(cli_runner, test_db):
    """Test basic predict command execution."""
    result = cli_runner.invoke(
        main,
        ["predict", "AAPL", "--interval", "30min", "--dry-run"]
    )
    assert result.exit_code == 0
    assert "AAPL" in result.output

def test_predict_command_with_save(cli_runner, test_db):
    """Test predict command persists signals to DB."""
    result = cli_runner.invoke(
        main,
        ["predict", "AAPL", "--interval", "30min", "--save"]
    )

    # Verify signals written to database
    with get_connection() as conn:
        signals = fetch_recent_signals(conn, "AAPL", lookback_hours=1)
        assert len(signals) > 0
```

**`test_scheduler_integration.py`**
```python
def test_scheduler_start_stop(cli_runner):
    """Test scheduler start and stop commands."""

def test_scheduler_execution_cycle(test_db, mock_market_data):
    """Test scheduler executes full cycle on schedule."""

def test_scheduler_recovery_after_failure(test_db):
    """Test scheduler recovers from failed cycle and continues."""
```

### 6.3 End-to-End Tests

**`test_e2e_prediction_flow.py`**
```python
def test_full_prediction_pipeline(live_db, eodhd_sandbox):
    """
    E2E test: Data fetch → calculation → signal gen → notification.

    Uses sandbox EODHD account and temporary database.
    """

def test_calibration_workflow(live_db, historical_signals):
    """
    E2E test: Signal generation → evaluation → calibration report.
    """
```

### 6.4 Test Fixtures

**`conftest.py`**
```python
@pytest.fixture
def test_db():
    """Temporary PostgreSQL database for testing."""

@pytest.fixture
def mock_market_data():
    """Synthetic market data for deterministic tests."""

@pytest.fixture
def mock_multi_timeframe_analysis():
    """Sample MultiTimeframeAnalysis objects."""

@pytest.fixture
def sample_signals():
    """Pre-generated signals for notification/calibration tests."""
```

---

## 7. Implementation Sequence

### 7.1 Week-by-Week Breakdown

#### **Week 1: Foundation & Database**
**Days 1-2: Database Schema**
- [ ] Create migration `003_prediction_system.sql`
- [ ] Add tables: `prediction_runs`, `generated_signals`, `prediction_metrics`, `scheduler_state`
- [ ] Write migration tests
- [ ] Apply migration to dev database

**Days 3-5: Persistence Layer**
- [ ] Implement `prediction/persistence.py`
  - [ ] `save_prediction_run()`
  - [ ] `save_generated_signals()`
  - [ ] `get_recent_signals()`
  - [ ] `update_signal_outcome()`
- [ ] Write unit tests for persistence
- [ ] Integration test with database

**Days 6-7: Data Refresh Enhancement**
- [ ] Extend `dgas/data/ingestion.py` with batch incremental update
- [ ] Add `fetch_symbols_list()` helper for watchlist processing
- [ ] Test incremental updates with recent data
- [ ] Performance testing: 100 symbols in <30s

---

#### **Week 2: Prediction Engine Core**
**Days 1-3: Signal Generator**
- [ ] Implement `prediction/engine.py`
  - [ ] `SignalGenerator` class
  - [ ] Entry rules (`_apply_entry_rules`)
  - [ ] Level calculation (`_calculate_levels`)
  - [ ] Confidence scoring (`_calculate_confidence`)
- [ ] Write unit tests for signal generation
- [ ] Test with sample `MultiTimeframeAnalysis` inputs

**Days 4-5: Prediction Engine**
- [ ] Implement `PredictionEngine` class
  - [ ] `execute_prediction_cycle()`
  - [ ] `_refresh_market_data()`
  - [ ] `_recalculate_indicators()`
  - [ ] `_generate_signals()`
- [ ] Write unit tests with mocked dependencies
- [ ] Integration test: full cycle with test data

**Days 6-7: Signal Aggregation**
- [ ] Implement `SignalAggregator` class
  - [ ] Duplicate detection
  - [ ] Filtering logic
  - [ ] Ranking algorithm
- [ ] Write unit tests
- [ ] Performance test with 1000 signals

---

#### **Week 3: Scheduler & Orchestration**
**Days 1-2: Market Hours Manager**
- [ ] Implement `prediction/scheduler.py`
  - [ ] `TradingSession` dataclass
  - [ ] `MarketHoursManager` class
- [ ] Write tests for market hour detection
- [ ] Test edge cases (holidays, DST transitions)

**Days 3-5: Scheduler Core**
- [ ] Implement `PredictionScheduler` class
  - [ ] Interval-based triggering
  - [ ] Integration with `PredictionEngine`
  - [ ] Error handling and retry logic
  - [ ] Graceful shutdown
- [ ] Write unit tests for scheduler logic
- [ ] Integration test: scheduler with mock engine

**Days 6-7: Scheduler State Management**
- [ ] Implement state persistence to `scheduler_state` table
- [ ] Add recovery logic (resume after crash)
- [ ] Test scheduler restart scenarios
- [ ] Add health monitoring hooks

---

#### **Week 4: Notification System**
**Days 1-2: Notification Infrastructure**
- [ ] Implement `prediction/notifications/router.py`
  - [ ] `NotificationRouter` class
  - [ ] `NotificationAdapter` abstract base
- [ ] Implement `ConsoleAdapter`
- [ ] Write tests for routing logic

**Days 3-4: Email & Webhook Adapters**
- [ ] Implement `EmailAdapter`
  - [ ] SMTP integration
  - [ ] HTML template rendering
- [ ] Implement `WebhookAdapter`
  - [ ] HTTP POST with retries
- [ ] Write tests with mocked SMTP/HTTP
- [ ] Create email templates (Jinja2)

**Days 5-6: Desktop & Advanced Adapters**
- [ ] Implement `DesktopAdapter`
  - [ ] Platform-specific notification APIs
- [ ] Optional: Implement `SlackAdapter`
- [ ] Write tests for all adapters
- [ ] Integration test: multi-channel delivery

**Day 7: Notification Templates**
- [ ] Create Jinja2 templates for email
- [ ] Design rich console output format
- [ ] Test templates with sample signals
- [ ] Documentation for custom templates

---

#### **Week 5: Monitoring & Calibration**
**Days 1-3: Performance Tracking**
- [ ] Implement `prediction/monitoring/performance.py`
  - [ ] `PerformanceTracker` class
  - [ ] Latency metrics collection
  - [ ] Throughput tracking
  - [ ] SLA compliance checks
- [ ] Write unit tests
- [ ] Integration test with database

**Days 4-6: Calibration Engine**
- [ ] Implement `prediction/monitoring/calibration.py`
  - [ ] `CalibrationEngine` class
  - [ ] Signal outcome evaluation
  - [ ] Batch evaluation
  - [ ] Calibration reporting
- [ ] Write unit tests
- [ ] Test with historical backtest data

**Day 7: Monitoring Integration**
- [ ] Integrate performance tracking into scheduler
- [ ] Add metric collection to prediction engine
- [ ] Test end-to-end metric flow
- [ ] Verify metric persistence

---

#### **Week 6: CLI & Configuration**
**Days 1-2: Predict Command**
- [ ] Extend `dgas/__main__.py` with `predict` subcommand
- [ ] Implement `cli/predict.py`
  - [ ] Argument parsing
  - [ ] Watchlist loading
  - [ ] Output formatting
- [ ] Write CLI tests
- [ ] Test with real database

**Days 3-4: Scheduler Command**
- [ ] Implement `scheduler` subcommand
  - [ ] `start`, `stop`, `status` actions
  - [ ] Configuration management
  - [ ] Daemon mode
- [ ] Implement PID file management
- [ ] Write CLI tests
- [ ] Test scheduler lifecycle

**Days 5-6: Monitor Command**
- [ ] Implement `monitor` subcommand
  - [ ] Performance metrics display
  - [ ] Calibration report viewer
  - [ ] Signal history browser
- [ ] Implement dashboard mode (live updating)
- [ ] Write CLI tests

**Day 7: Configuration System**
- [ ] Implement YAML/JSON config file parser
- [ ] Add `SchedulerConfig.from_file()` factory
- [ ] Write validation logic
- [ ] Create sample configuration files
- [ ] Documentation for config format

---

#### **Week 7-8: Integration & Testing**
**Week 7: Integration Testing**
- [ ] End-to-end tests for full prediction cycle
- [ ] Multi-symbol concurrent processing tests
- [ ] Notification delivery tests
- [ ] Calibration workflow tests
- [ ] Performance benchmarking (target: 100 symbols in 60s)

**Week 8: Hardening & Documentation**
- [ ] Error handling review and enhancement
- [ ] Logging improvements (structured logs)
- [ ] Configuration validation
- [ ] CLI help text and examples
- [ ] Write user documentation
  - [ ] Getting Started guide
  - [ ] Configuration reference
  - [ ] CLI command reference
  - [ ] Troubleshooting guide
- [ ] Update `llms.txt` with Phase 4 details

---

### 7.2 Dependencies & Critical Path

**Critical Path:**
```
Database Schema (Week 1)
  → Persistence Layer (Week 1)
    → Signal Generator (Week 2)
      → Prediction Engine (Week 2)
        → Scheduler (Week 3)
          → CLI Integration (Week 6)
            → Testing (Week 7-8)
```

**Parallel Work:**
- Notification system (Week 4) can develop in parallel with Scheduler (Week 3)
- Monitoring system (Week 5) can develop in parallel with CLI (Week 6)
- Templates and documentation can be ongoing throughout

---

## 8. Performance Requirements & Optimization

### 8.1 Target Performance Metrics

**Latency Targets:**
- Data fetch (100 symbols): ≤20 seconds
- Indicator calculation (100 symbols): ≤30 seconds
- Signal generation (100 signals): ≤5 seconds
- Notification delivery: ≤5 seconds
- **Total cycle time: ≤60 seconds** (1 minute SLA)

**Throughput Targets:**
- Process 1,000 symbols in ≤10 minutes
- Generate 500 signals/minute
- Support 10 concurrent users

**Reliability Targets:**
- Uptime: 99% during market hours
- Error rate: <1%
- Alert delivery success: >99%

### 8.2 Optimization Strategies

**Data Loading:**
- Use `executemany()` for bulk inserts (Phase 1 pattern)
- Implement connection pooling (consider for Phase 4)
- Batch symbol processing (chunks of 10-20)
- Cache recent OHLCV data in memory (Redis optional)

**Indicator Calculation:**
- Only recalculate for symbols with new data
- Reuse Phase 2 calculation modules (already optimized)
- Consider parallel processing with `multiprocessing` for large watchlists
- Limit lookback to required window (e.g., 200 bars)

**Signal Generation:**
- Filter symbols before full analysis (quick market state check)
- Batch multi-timeframe coordination calls
- Limit pattern detection to enabled patterns only

**Notification:**
- Async notification delivery (don't block main thread)
- Batch webhook deliveries
- Rate limit email sending (avoid SMTP throttling)

---

## 9. Risk Assessment & Mitigation

### 9.1 Technical Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Data API reliability** | High | Medium | Implement retry logic with exponential backoff; fallback to cached data; monitor API health |
| **Scheduler stability** | High | Low | Comprehensive error handling; state persistence for recovery; health monitoring; graceful shutdown |
| **Database performance** | Medium | Medium | Connection pooling; query optimization; index tuning; batch operations |
| **Notification delivery failures** | Medium | Medium | Retry logic per channel; fallback channels; delivery status tracking; user alerts on failures |
| **Signal accuracy degradation** | High | Medium | Continuous calibration monitoring; automated alerts on accuracy drop; backtesting validation |
| **Memory leaks in long-running scheduler** | Medium | Low | Resource monitoring; periodic restarts; profiling; garbage collection tuning |
| **Timezone/DST handling** | Medium | Low | Use UTC internally; explicit timezone conversions; test edge cases; DST transition tests |

### 9.2 Operational Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **Market data delays** | High | Medium | Monitor data freshness; alert on stale data; display last update timestamp |
| **False signal alerts** | Medium | Medium | Confidence thresholds; calibration validation; user education on risk |
| **System overload during high volatility** | Medium | Low | Rate limiting; queue management; graceful degradation; scale symbols processed |
| **Configuration errors** | Low | Medium | Configuration validation; safe defaults; schema validation; test configurations |

---

## 10. Success Criteria & Exit Checklist

### 10.1 Functional Requirements

- [ ] Scheduler executes prediction cycles on configured interval (e.g., 30min)
- [ ] Market hours detection prevents execution outside trading hours
- [ ] Incremental data updates fetch only new bars since last run
- [ ] Indicators recalculated only for symbols with new data
- [ ] Multi-timeframe coordination generates signals with confidence scores
- [ ] Signals persist to `generated_signals` table with rich context
- [ ] Console notifications display signals in formatted tables
- [ ] Email notifications deliver HTML-formatted alerts
- [ ] Webhook notifications POST JSON payloads successfully
- [ ] Desktop notifications trigger for high-confidence signals
- [ ] Performance metrics tracked and persisted
- [ ] Calibration engine evaluates signal outcomes
- [ ] CLI commands (`predict`, `scheduler`, `monitor`) functional
- [ ] Configuration file (YAML/JSON) loading works
- [ ] Graceful shutdown on SIGTERM/SIGINT

### 10.2 Performance Requirements

- [ ] New bars processed ≤1 min after availability (data fetch to signal generation)
- [ ] Alert delivery latency <30 seconds from signal generation
- [ ] Process 100 symbols in ≤60 seconds
- [ ] P95 latency for full cycle ≤75 seconds
- [ ] Scheduler uptime ≥99% during market hours
- [ ] Error rate ≤1%
- [ ] Notification delivery success ≥99%

### 10.3 Quality Requirements

- [ ] Unit test coverage ≥90% for new modules
- [ ] Integration tests for full prediction cycle pass
- [ ] End-to-end test with live EODHD sandbox passes
- [ ] No critical bugs in production testing
- [ ] Documentation complete (user guide, CLI reference, config reference)
- [ ] Code review completed
- [ ] Security review (credential handling, input validation)

### 10.4 Calibration Requirements

- [ ] Signal accuracy validated against historical backtests (±10% variance)
- [ ] Calibration reports show win rate by confidence bucket
- [ ] Confidence scores correlate with actual outcomes (>0.7 correlation)
- [ ] Automated calibration runs every 24 hours
- [ ] Alert triggered if accuracy drops >15% below baseline

### 10.5 Operational Requirements

- [ ] Scheduler survives 7-day continuous run without failures
- [ ] Scheduler recovers from manual stop/restart
- [ ] Logs provide sufficient debugging information
- [ ] Monitoring dashboard displays real-time metrics
- [ ] Runbook created for common issues
- [ ] Deployment procedure documented
- [ ] Backup and recovery tested

---

## 11. Future Enhancements (Post-Phase 4)

### 11.1 Advanced Features

**Phase 5 Candidates:**
- **Machine Learning Integration:** Use historical calibration data to train confidence score models
- **Adaptive Thresholds:** Automatically adjust confidence thresholds based on recent accuracy
- **Portfolio-Level Analysis:** Coordinate signals across multiple positions to manage correlation risk
- **Advanced Risk Management:** Position sizing recommendations based on volatility and account size
- **Real-Time Streaming:** WebSocket integration for sub-second signal delivery
- **Multi-Asset Support:** Extend beyond equities (futures, forex, crypto)

### 11.2 Scalability Enhancements

- **Distributed Processing:** Use Celery or Ray for parallel symbol processing
- **Cloud Deployment:** Kubernetes deployment with auto-scaling
- **Advanced Caching:** Redis caching layer for frequently accessed data
- **Database Optimization:** TimescaleDB for time-series data or partitioned tables
- **API Layer:** RESTful API for third-party integrations

### 11.3 User Experience Improvements

- **Web Dashboard:** React/Vue.js dashboard for visualization
- **Mobile App:** iOS/Android app for signal monitoring
- **Slack Integration:** Native Slack app for team notifications
- **Custom Strategies:** User-defined signal generation rules via DSL
- **Backtesting Integration:** One-click backtest of generated signals

---

## 12. Appendices

### 12.1 Glossary

**Terms:**
- **Prediction Cycle:** Complete execution of data refresh, calculation, and signal generation
- **Signal Confidence:** 0.0-1.0 score indicating probability of signal success
- **Timeframe Alignment:** Agreement between higher and trading timeframes on market direction
- **Calibration:** Process of comparing predicted signals to actual outcomes
- **Confluence Zone:** Price level where multiple support/resistance indicators align

### 12.2 References

**Internal Documents:**
- PRD: `/opt/DrummondGeometry-evals/prd/01_comprehensive_prd.md`
- Implementation Plan: `/opt/DrummondGeometry-evals/implementation_plan.md`
- Phase 3 Plan: `/opt/DrummondGeometry-evals/docs/PHASE3_BACKTESTING_PLAN.md`
- llms.txt: `/opt/DrummondGeometry-evals/src/llms.txt`

**External Resources:**
- EODHD API Documentation: https://eodhd.com/financial-apis
- Drummond Geometry: "How to Make Money Trading the 3 Day Chart" (Book)
- PostgreSQL Documentation: https://www.postgresql.org/docs/

### 12.3 Configuration Examples

See full configuration examples in `/opt/DrummondGeometry-evals/config/examples/`.

---

## Document Metadata

**Version:** 1.0
**Date:** 2024-01-XX
**Author:** Phase 4 Implementation Planning
**Status:** Draft - Awaiting Approval
**Next Review:** After user approval

---

**END OF PHASE 4 IMPLEMENTATION PLAN**
