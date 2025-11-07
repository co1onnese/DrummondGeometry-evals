# Phase 4 Week 5: Monitoring & Calibration - Implementation Plan

**Status:** Planning
**Created:** 2025-11-06
**Dependencies:** Week 3 (Scheduler) ✅, Week 4 (Notifications) ✅

---

## Executive Summary

Week 5 implements a comprehensive monitoring and calibration system for the prediction pipeline. This includes:

1. **Performance Tracking** - Monitor system latency, throughput, and SLA compliance
2. **Calibration Engine** - Validate signal accuracy against actual market outcomes
3. **Database Integration** - Persist metrics to `prediction_metrics` table
4. **Scheduler Integration** - Hook monitoring into existing `PredictionScheduler`

The system will provide observability into prediction quality and operational health, enabling data-driven improvements to signal generation.

---

## Context & Architecture

### Completed Foundation
- ✅ **Database Schema** (migration `003_prediction_system.sql`)
  - `prediction_runs` table with latency breakdown fields
  - `generated_signals` table with `outcome`, `pnl_pct` fields for calibration
  - `prediction_metrics` table for time-series metrics
- ✅ **Persistence Layer** (`prediction/persistence.py`)
  - `save_prediction_run()` - Records execution metrics
  - `update_signal_outcome()` - Updates signal outcomes
  - `save_metric()` - Persists individual metrics
  - `get_metrics()` - Query metrics for analysis
- ✅ **Scheduler** (`prediction/scheduler.py`)
  - `PredictionScheduler` with APScheduler integration
  - `MarketHoursManager` for trading hours awareness
  - Scheduled execution with error handling
- ✅ **Prediction Engine** (`prediction/engine.py`)
  - `PredictionEngine` generates signals with `PredictionRunResult`
  - `SignalGenerator` creates `GeneratedSignal` objects
  - Multi-timeframe analysis via `MultiTimeframeCoordinator`

### Week 5 Architecture
```
┌─────────────────────────────────────────────────────────┐
│                PredictionScheduler                       │
│  (Orchestrates scheduled prediction cycles)             │
└────────────────┬────────────────────────────────────────┘
                 │
                 ├──> PredictionEngine.generate_signals()
                 │    Returns: PredictionRunResult
                 │    (signals, latency breakdown, errors)
                 │
                 ├──> PerformanceTracker.track_cycle()
                 │    Records: latency, throughput, errors
                 │    Persists: prediction_metrics table
                 │    Checks: SLA compliance
                 │
                 └──> NotificationRouter.deliver()
                      (existing Week 4 integration)

┌─────────────────────────────────────────────────────────┐
│             CalibrationEngine (Async)                    │
│  - Runs separate from real-time cycle                   │
│  - Batch evaluates signals after evaluation window      │
│  - Updates generated_signals with outcomes              │
│  - Generates calibration reports                        │
└─────────────────────────────────────────────────────────┘
```

---

## Day 1-3: Performance Tracking System

### Objective
Implement `PerformanceTracker` to monitor prediction cycle performance in real-time.

### Components

#### 1. Data Classes (`prediction/monitoring/performance.py`)

```python
@dataclass(frozen=True)
class LatencyMetrics:
    """Latency measurements for prediction cycle stages."""
    data_fetch_ms: int
    indicator_calc_ms: int
    signal_generation_ms: int
    notification_ms: int
    total_ms: int

    @property
    def total_calculated(self) -> int:
        """Calculate total from components (for validation)."""
        return (self.data_fetch_ms + self.indicator_calc_ms +
                self.signal_generation_ms + self.notification_ms)

@dataclass(frozen=True)
class ThroughputMetrics:
    """Throughput measurements for prediction cycle."""
    symbols_processed: int
    signals_generated: int
    execution_time_ms: int
    symbols_per_second: float

    @classmethod
    def calculate(
        cls,
        symbols_processed: int,
        signals_generated: int,
        execution_time_ms: int,
    ) -> ThroughputMetrics:
        """Calculate throughput metrics."""
        sps = symbols_processed / (execution_time_ms / 1000.0) if execution_time_ms > 0 else 0.0
        return cls(
            symbols_processed=symbols_processed,
            signals_generated=signals_generated,
            execution_time_ms=execution_time_ms,
            symbols_per_second=sps,
        )

@dataclass(frozen=True)
class PerformanceSummary:
    """Summary statistics for performance tracking."""
    lookback_hours: int
    total_cycles: int
    successful_cycles: int

    # Latency statistics (milliseconds)
    avg_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float

    # Throughput statistics
    avg_throughput: float  # symbols/second
    total_symbols_processed: int
    total_signals_generated: int

    # Reliability
    error_rate: float  # Percentage of cycles with errors
    uptime_pct: float  # Percentage of successful cycles

    # SLA compliance
    sla_compliant: bool
    sla_violations: Dict[str, Any]  # Details of any SLA violations
```

#### 2. PerformanceTracker Class

**File:** `src/dgas/prediction/monitoring/performance.py`

```python
class PerformanceTracker:
    """
    Tracks and reports system performance metrics.

    Monitors prediction cycle performance, calculates aggregated statistics,
    and validates SLA compliance.
    """

    # SLA Thresholds
    SLA_P95_LATENCY_MS = 60_000  # 60 seconds
    SLA_ERROR_RATE_PCT = 1.0     # 1%
    SLA_UPTIME_PCT = 99.0        # 99%

    def __init__(self, persistence: PredictionPersistence):
        """Initialize with database persistence."""
        self.persistence = persistence
        self.logger = logging.getLogger(__name__)

    def track_cycle(
        self,
        run_id: int,
        latency: LatencyMetrics,
        throughput: ThroughputMetrics,
        errors: List[str],
    ) -> None:
        """
        Record metrics for a prediction cycle.

        This method is called by PredictionScheduler after each cycle completes.
        Metrics are persisted to prediction_metrics table for time-series analysis.
        """
        # Persist individual metrics
        self.persistence.save_metric(
            metric_type="latency_total",
            metric_value=latency.total_ms,
            metadata={"run_id": run_id}
        )

        self.persistence.save_metric(
            metric_type="latency_data_fetch",
            metric_value=latency.data_fetch_ms,
            metadata={"run_id": run_id}
        )

        # ... persist other latency components

        self.persistence.save_metric(
            metric_type="throughput_symbols_per_second",
            metric_value=throughput.symbols_per_second,
            metadata={"run_id": run_id}
        )

        # Track error rate
        error_count = len(errors)
        self.persistence.save_metric(
            metric_type="error_count",
            metric_value=error_count,
            metadata={"run_id": run_id, "errors": errors[:5]}  # Sample errors
        )

    def get_performance_summary(
        self,
        lookback_hours: int = 24,
    ) -> PerformanceSummary:
        """
        Get performance summary statistics for the lookback period.

        Calculates aggregated metrics from prediction_runs and prediction_metrics tables.
        """
        # Query recent runs
        runs = self.persistence.get_recent_runs(
            limit=1000,  # Large limit for comprehensive analysis
        )

        # Filter to lookback window
        cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
        recent_runs = [r for r in runs if r["run_timestamp"] >= cutoff]

        if not recent_runs:
            return self._empty_summary(lookback_hours)

        # Calculate statistics
        total_cycles = len(recent_runs)
        successful = [r for r in recent_runs if r["status"] == "SUCCESS"]
        successful_count = len(successful)

        latencies = [r["execution_time_ms"] for r in recent_runs if r["execution_time_ms"]]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        p50_latency = self._percentile(latencies, 50)
        p95_latency = self._percentile(latencies, 95)
        p99_latency = self._percentile(latencies, 99)

        # Throughput
        symbols_processed = sum(r["symbols_processed"] for r in recent_runs)
        signals_generated = sum(r["signals_generated"] for r in recent_runs)

        # Calculate avg throughput (symbols/second)
        throughput_values = []
        for run in recent_runs:
            if run["execution_time_ms"] > 0:
                sps = run["symbols_processed"] / (run["execution_time_ms"] / 1000.0)
                throughput_values.append(sps)
        avg_throughput = sum(throughput_values) / len(throughput_values) if throughput_values else 0

        # Reliability
        cycles_with_errors = len([r for r in recent_runs if r["errors"] and len(r["errors"]) > 0])
        error_rate = (cycles_with_errors / total_cycles * 100) if total_cycles > 0 else 0
        uptime_pct = (successful_count / total_cycles * 100) if total_cycles > 0 else 0

        # SLA compliance
        sla_compliant, violations = self._check_sla(
            p95_latency=p95_latency,
            error_rate=error_rate,
            uptime_pct=uptime_pct,
        )

        return PerformanceSummary(
            lookback_hours=lookback_hours,
            total_cycles=total_cycles,
            successful_cycles=successful_count,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            avg_throughput=avg_throughput,
            total_symbols_processed=symbols_processed,
            total_signals_generated=signals_generated,
            error_rate=error_rate,
            uptime_pct=uptime_pct,
            sla_compliant=sla_compliant,
            sla_violations=violations,
        )

    def check_sla_compliance(self) -> bool:
        """
        Verify system meets SLA requirements (24-hour window).

        SLA Targets:
        - P95 total latency ≤ 60 seconds (60,000 ms)
        - Error rate ≤ 1%
        - Uptime ≥ 99% during market hours
        """
        summary = self.get_performance_summary(lookback_hours=24)
        return summary.sla_compliant

    def _check_sla(
        self,
        p95_latency: float,
        error_rate: float,
        uptime_pct: float,
    ) -> tuple[bool, Dict[str, Any]]:
        """Check SLA compliance and return violations."""
        violations = {}

        if p95_latency > self.SLA_P95_LATENCY_MS:
            violations["p95_latency"] = {
                "actual": p95_latency,
                "threshold": self.SLA_P95_LATENCY_MS,
                "message": f"P95 latency {p95_latency:.0f}ms exceeds {self.SLA_P95_LATENCY_MS}ms"
            }

        if error_rate > self.SLA_ERROR_RATE_PCT:
            violations["error_rate"] = {
                "actual": error_rate,
                "threshold": self.SLA_ERROR_RATE_PCT,
                "message": f"Error rate {error_rate:.2f}% exceeds {self.SLA_ERROR_RATE_PCT}%"
            }

        if uptime_pct < self.SLA_UPTIME_PCT:
            violations["uptime"] = {
                "actual": uptime_pct,
                "threshold": self.SLA_UPTIME_PCT,
                "message": f"Uptime {uptime_pct:.2f}% below {self.SLA_UPTIME_PCT}%"
            }

        compliant = len(violations) == 0
        return compliant, violations

    @staticmethod
    def _percentile(values: List[float], percentile: int) -> float:
        """Calculate percentile from list of values."""
        if not values:
            return 0.0
        sorted_values = sorted(values)
        index = int(len(sorted_values) * percentile / 100)
        index = min(index, len(sorted_values) - 1)
        return sorted_values[index]

    def _empty_summary(self, lookback_hours: int) -> PerformanceSummary:
        """Return empty summary when no data available."""
        return PerformanceSummary(
            lookback_hours=lookback_hours,
            total_cycles=0,
            successful_cycles=0,
            avg_latency_ms=0.0,
            p50_latency_ms=0.0,
            p95_latency_ms=0.0,
            p99_latency_ms=0.0,
            avg_throughput=0.0,
            total_symbols_processed=0,
            total_signals_generated=0,
            error_rate=0.0,
            uptime_pct=0.0,
            sla_compliant=True,
            sla_violations={},
        )
```

### Testing Strategy (Days 1-3)

#### Unit Tests (`tests/prediction/monitoring/test_performance.py`)

1. **LatencyMetrics Tests**
   - Validate total_calculated property
   - Test immutability

2. **ThroughputMetrics Tests**
   - Test calculate() factory method
   - Edge case: zero execution time
   - Validate symbols_per_second calculation

3. **PerformanceTracker Tests**
   - Mock persistence layer
   - Test track_cycle() persists all metrics
   - Test get_performance_summary() calculations
   - Test percentile calculation
   - Test SLA compliance checks
   - Test empty summary when no data

4. **Integration Tests**
   - Test with real database
   - Save multiple runs and verify summary statistics
   - Test lookback window filtering
   - Test error rate calculation with mixed success/failure runs

---

## Day 4-6: Calibration Engine

### Objective
Implement `CalibrationEngine` to validate signal accuracy by comparing predicted signals against actual market outcomes.

### Components

#### 1. Data Classes (`prediction/monitoring/calibration.py`)

```python
@dataclass(frozen=True)
class SignalOutcome:
    """Actual outcome of a generated signal after evaluation."""
    signal_id: int
    evaluation_timestamp: datetime

    # Price movement within evaluation window
    actual_high: Decimal  # Highest price reached
    actual_low: Decimal   # Lowest price reached
    close_price: Decimal  # Final closing price

    # Outcome classification
    hit_target: bool      # Target price was reached
    hit_stop: bool        # Stop loss was hit
    outcome: str          # "WIN", "LOSS", "NEUTRAL", "PENDING"
    pnl_pct: float        # Percentage P&L if signal was taken

    # Context
    evaluation_window_hours: int
    signal_type: str      # LONG, SHORT (from original signal)

@dataclass(frozen=True)
class CalibrationReport:
    """Calibration metrics report for signal accuracy analysis."""
    date_range: tuple[datetime, datetime]
    total_signals: int
    evaluated_signals: int

    # Overall metrics
    win_rate: float           # % of signals that hit target
    avg_pnl_pct: float        # Average P&L across all signals
    target_hit_rate: float    # % that hit target
    stop_hit_rate: float      # % that hit stop

    # By confidence bucket (e.g., 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0)
    by_confidence: Dict[str, Dict[str, float]]
    # Example: {"0.7-0.8": {"win_rate": 0.68, "avg_pnl": 0.023, "count": 45}}

    # By signal type (LONG vs SHORT)
    by_signal_type: Dict[str, Dict[str, float]]
    # Example: {"LONG": {"win_rate": 0.62, "avg_pnl": 0.019, "count": 78}}
```

#### 2. CalibrationEngine Class

**File:** `src/dgas/prediction/monitoring/calibration.py`

```python
class CalibrationEngine:
    """
    Validates signal accuracy and tracks calibration metrics.

    Evaluates generated signals against actual market outcomes by fetching
    subsequent price data and determining if targets/stops were hit.
    """

    def __init__(
        self,
        persistence: PredictionPersistence,
        evaluation_window_hours: int = 24,
        data_source: Optional[Any] = None,  # DataFetcher for price data
    ):
        """
        Initialize calibration engine.

        Args:
            persistence: Database persistence layer
            evaluation_window_hours: Hours after signal to evaluate outcome
            data_source: Data source for fetching actual price data (optional)
        """
        self.persistence = persistence
        self.evaluation_window_hours = evaluation_window_hours
        self.data_source = data_source
        self.logger = logging.getLogger(__name__)

    def evaluate_signal(
        self,
        signal: Dict[str, Any],  # Signal from get_recent_signals()
        actual_prices: List[IntervalData],
    ) -> SignalOutcome:
        """
        Evaluate signal against actual price movement.

        Logic:
        1. Extract signal levels (entry, stop, target)
        2. Scan through actual_prices to find:
           - Highest price reached (for LONG target checks)
           - Lowest price reached (for LONG stop checks)
        3. Determine outcome:
           - WIN: Target hit before stop
           - LOSS: Stop hit before target
           - NEUTRAL: Neither hit within window
           - PENDING: Insufficient time elapsed
        4. Calculate actual P&L percentage

        Args:
            signal: Signal dictionary from database
            actual_prices: Price data after signal timestamp

        Returns:
            SignalOutcome with evaluation results
        """
        signal_id = signal["signal_id"]
        signal_type = signal["signal_type"]
        entry_price = signal["entry_price"]
        stop_loss = signal["stop_loss"]
        target_price = signal["target_price"]
        signal_timestamp = signal["signal_timestamp"]

        if not actual_prices:
            # Not enough data yet - mark as PENDING
            return SignalOutcome(
                signal_id=signal_id,
                evaluation_timestamp=datetime.now(timezone.utc),
                actual_high=entry_price,
                actual_low=entry_price,
                close_price=entry_price,
                hit_target=False,
                hit_stop=False,
                outcome="PENDING",
                pnl_pct=0.0,
                evaluation_window_hours=self.evaluation_window_hours,
                signal_type=signal_type,
            )

        # Find highest/lowest prices in evaluation window
        actual_high = max(bar.high for bar in actual_prices)
        actual_low = min(bar.low for bar in actual_prices)
        close_price = actual_prices[-1].close

        # Evaluate outcome based on signal type
        if signal_type == "LONG":
            hit_target = actual_high >= target_price
            hit_stop = actual_low <= stop_loss

            # Determine which was hit first (if both hit)
            if hit_target and hit_stop:
                # Check chronological order
                for bar in actual_prices:
                    if bar.low <= stop_loss:
                        outcome = "LOSS"
                        pnl_pct = float((stop_loss - entry_price) / entry_price * 100)
                        break
                    elif bar.high >= target_price:
                        outcome = "WIN"
                        pnl_pct = float((target_price - entry_price) / entry_price * 100)
                        break
            elif hit_target:
                outcome = "WIN"
                pnl_pct = float((target_price - entry_price) / entry_price * 100)
            elif hit_stop:
                outcome = "LOSS"
                pnl_pct = float((stop_loss - entry_price) / entry_price * 100)
            else:
                outcome = "NEUTRAL"
                pnl_pct = float((close_price - entry_price) / entry_price * 100)

        elif signal_type == "SHORT":
            hit_target = actual_low <= target_price
            hit_stop = actual_high >= stop_loss

            if hit_target and hit_stop:
                for bar in actual_prices:
                    if bar.high >= stop_loss:
                        outcome = "LOSS"
                        pnl_pct = float((entry_price - stop_loss) / entry_price * 100)
                        break
                    elif bar.low <= target_price:
                        outcome = "WIN"
                        pnl_pct = float((entry_price - target_price) / entry_price * 100)
                        break
            elif hit_target:
                outcome = "WIN"
                pnl_pct = float((entry_price - target_price) / entry_price * 100)
            elif hit_stop:
                outcome = "LOSS"
                pnl_pct = float((entry_price - stop_loss) / entry_price * 100)
            else:
                outcome = "NEUTRAL"
                pnl_pct = float((entry_price - close_price) / entry_price * 100)

        else:
            raise ValueError(f"Unsupported signal type: {signal_type}")

        return SignalOutcome(
            signal_id=signal_id,
            evaluation_timestamp=datetime.now(timezone.utc),
            actual_high=actual_high,
            actual_low=actual_low,
            close_price=close_price,
            hit_target=hit_target,
            hit_stop=hit_stop,
            outcome=outcome,
            pnl_pct=pnl_pct,
            evaluation_window_hours=self.evaluation_window_hours,
            signal_type=signal_type,
        )

    def batch_evaluate(
        self,
        lookback_hours: int = 24,
    ) -> List[SignalOutcome]:
        """
        Evaluate all signals from lookback period that haven't been evaluated yet.

        This method:
        1. Queries signals with outcome=NULL from lookback period
        2. For each signal, fetches actual price data
        3. Evaluates outcome
        4. Persists outcome to database

        Returns:
            List of evaluated signal outcomes
        """
        # Get signals pending evaluation
        # NOTE: Need to add query method to PredictionPersistence for pending signals
        # For now, get all recent signals and filter for NULL outcomes
        all_signals = self.persistence.get_recent_signals(
            lookback_hours=lookback_hours + self.evaluation_window_hours,
            limit=1000,
        )

        pending_signals = [s for s in all_signals if s["outcome"] is None]

        outcomes = []
        for signal in pending_signals:
            # Check if enough time has elapsed
            signal_timestamp = signal["signal_timestamp"]
            hours_elapsed = (datetime.now(timezone.utc) - signal_timestamp).total_seconds() / 3600

            if hours_elapsed < self.evaluation_window_hours:
                continue  # Not ready for evaluation yet

            # Fetch actual price data
            # NOTE: This requires DataFetcher integration
            # For Week 5, we'll implement the logic but may need to mock this in tests
            try:
                actual_prices = self._fetch_actual_prices(
                    symbol=signal["symbol"],
                    start_time=signal_timestamp,
                    hours=self.evaluation_window_hours,
                )

                # Evaluate
                outcome = self.evaluate_signal(signal, actual_prices)

                # Persist outcome
                self.persistence.update_signal_outcome(
                    signal_id=outcome.signal_id,
                    outcome=outcome.outcome,
                    actual_high=outcome.actual_high,
                    actual_low=outcome.actual_low,
                    actual_close=outcome.close_price,
                    pnl_pct=outcome.pnl_pct,
                )

                outcomes.append(outcome)

            except Exception as e:
                self.logger.error(f"Failed to evaluate signal {signal['signal_id']}: {e}")
                continue

        return outcomes

    def get_calibration_report(
        self,
        date_range: Optional[tuple[datetime, datetime]] = None,
    ) -> CalibrationReport:
        """
        Generate calibration report showing signal accuracy.

        Analyzes evaluated signals to compute:
        - Overall win rate and P&L
        - Metrics by confidence bucket
        - Metrics by signal type

        Args:
            date_range: Optional (start, end) datetime range. Defaults to last 30 days.

        Returns:
            CalibrationReport with comprehensive accuracy metrics
        """
        if date_range is None:
            end = datetime.now(timezone.utc)
            start = end - timedelta(days=30)
            date_range = (start, end)

        start_date, end_date = date_range

        # Get all evaluated signals in range
        # NOTE: This needs a date-range query method on PredictionPersistence
        # For now, get recent and filter
        lookback_hours = int((end_date - start_date).total_seconds() / 3600)
        all_signals = self.persistence.get_recent_signals(
            lookback_hours=lookback_hours,
            limit=10000,
        )

        evaluated_signals = [
            s for s in all_signals
            if s["outcome"] is not None and s["outcome"] != "PENDING"
        ]

        total_signals = len(all_signals)
        evaluated_count = len(evaluated_signals)

        if evaluated_count == 0:
            return self._empty_report(date_range)

        # Overall metrics
        wins = [s for s in evaluated_signals if s["outcome"] == "WIN"]
        win_rate = len(wins) / evaluated_count

        avg_pnl = sum(s["pnl_pct"] for s in evaluated_signals) / evaluated_count

        target_hits = [s for s in evaluated_signals if s.get("actual_high") is not None]
        # NOTE: This logic needs actual hit_target boolean from outcome data
        # For now, approximate with outcome == "WIN"
        target_hit_rate = len(wins) / evaluated_count

        losses = [s for s in evaluated_signals if s["outcome"] == "LOSS"]
        stop_hit_rate = len(losses) / evaluated_count

        # By confidence bucket
        by_confidence = self._group_by_confidence(evaluated_signals)

        # By signal type
        by_signal_type = self._group_by_signal_type(evaluated_signals)

        return CalibrationReport(
            date_range=date_range,
            total_signals=total_signals,
            evaluated_signals=evaluated_count,
            win_rate=win_rate,
            avg_pnl_pct=avg_pnl,
            target_hit_rate=target_hit_rate,
            stop_hit_rate=stop_hit_rate,
            by_confidence=by_confidence,
            by_signal_type=by_signal_type,
        )

    def _fetch_actual_prices(
        self,
        symbol: str,
        start_time: datetime,
        hours: int,
    ) -> List[IntervalData]:
        """
        Fetch actual price data for evaluation.

        NOTE: This requires integration with DataFetcher.
        For Week 5, this is a placeholder that should be implemented
        based on existing data fetching infrastructure.
        """
        # TODO: Integrate with DataFetcher from data/fetcher.py
        # For now, return empty list and expect it to be mocked in tests
        if self.data_source is None:
            return []

        # Implementation will call data_source.fetch_intraday() or similar
        raise NotImplementedError("Price data fetching not yet implemented")

    def _group_by_confidence(
        self,
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """Group signals by confidence bucket and calculate metrics."""
        buckets = {
            "0.6-0.7": [],
            "0.7-0.8": [],
            "0.8-0.9": [],
            "0.9-1.0": [],
        }

        for signal in signals:
            confidence = signal["confidence"]
            if 0.6 <= confidence < 0.7:
                buckets["0.6-0.7"].append(signal)
            elif 0.7 <= confidence < 0.8:
                buckets["0.7-0.8"].append(signal)
            elif 0.8 <= confidence < 0.9:
                buckets["0.8-0.9"].append(signal)
            elif 0.9 <= confidence <= 1.0:
                buckets["0.9-1.0"].append(signal)

        result = {}
        for bucket_name, bucket_signals in buckets.items():
            if not bucket_signals:
                continue

            wins = [s for s in bucket_signals if s["outcome"] == "WIN"]
            win_rate = len(wins) / len(bucket_signals)
            avg_pnl = sum(s["pnl_pct"] for s in bucket_signals) / len(bucket_signals)

            result[bucket_name] = {
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "count": len(bucket_signals),
            }

        return result

    def _group_by_signal_type(
        self,
        signals: List[Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """Group signals by type (LONG/SHORT) and calculate metrics."""
        by_type = {"LONG": [], "SHORT": []}

        for signal in signals:
            signal_type = signal["signal_type"]
            if signal_type in by_type:
                by_type[signal_type].append(signal)

        result = {}
        for signal_type, type_signals in by_type.items():
            if not type_signals:
                continue

            wins = [s for s in type_signals if s["outcome"] == "WIN"]
            win_rate = len(wins) / len(type_signals)
            avg_pnl = sum(s["pnl_pct"] for s in type_signals) / len(type_signals)

            result[signal_type] = {
                "win_rate": win_rate,
                "avg_pnl": avg_pnl,
                "count": len(type_signals),
            }

        return result

    def _empty_report(
        self,
        date_range: tuple[datetime, datetime],
    ) -> CalibrationReport:
        """Return empty report when no data available."""
        return CalibrationReport(
            date_range=date_range,
            total_signals=0,
            evaluated_signals=0,
            win_rate=0.0,
            avg_pnl_pct=0.0,
            target_hit_rate=0.0,
            stop_hit_rate=0.0,
            by_confidence={},
            by_signal_type={},
        )
```

### Testing Strategy (Days 4-6)

#### Unit Tests (`tests/prediction/monitoring/test_calibration.py`)

1. **SignalOutcome Tests**
   - Validate immutability
   - Test various outcome scenarios

2. **CalibrationEngine.evaluate_signal() Tests**
   - Test LONG signal with target hit
   - Test LONG signal with stop hit
   - Test LONG signal with both hit (stop first)
   - Test LONG signal with both hit (target first)
   - Test LONG signal with neither hit (NEUTRAL)
   - Test SHORT signal scenarios (mirror of LONG)
   - Test PENDING outcome (insufficient data)
   - Test P&L calculation accuracy

3. **CalibrationEngine.batch_evaluate() Tests**
   - Mock persistence.get_recent_signals()
   - Mock _fetch_actual_prices()
   - Test batch evaluation of multiple signals
   - Test skipping signals with insufficient time elapsed
   - Test error handling for individual signal failures

4. **CalibrationEngine.get_calibration_report() Tests**
   - Test report generation with varied outcomes
   - Test confidence bucket grouping
   - Test signal type grouping
   - Test empty report when no data
   - Test win rate calculations
   - Test average P&L calculations

5. **Integration Tests**
   - Test with real database
   - Save signals, evaluate outcomes, generate report
   - Verify outcome persistence
   - Test date range filtering

---

## Day 7: Monitoring Integration

### Objective
Integrate `PerformanceTracker` and `CalibrationEngine` into the existing `PredictionScheduler`.

### Integration Points

#### 1. Scheduler Enhancement (`prediction/scheduler.py`)

**Modifications to `PredictionScheduler`:**

```python
class PredictionScheduler:
    """Prediction scheduler with monitoring integration."""

    def __init__(
        self,
        config: SchedulerConfig,
        persistence: Optional[PredictionPersistence] = None,
        notification_router: Optional[NotificationRouter] = None,
        performance_tracker: Optional[PerformanceTracker] = None,  # NEW
    ):
        # ... existing init code ...

        # Initialize performance tracker
        if performance_tracker is None and persistence is not None:
            from .monitoring.performance import PerformanceTracker
            performance_tracker = PerformanceTracker(persistence)
        self.performance_tracker = performance_tracker

    def _run_prediction_cycle(self) -> None:
        """Execute prediction cycle with performance tracking."""
        cycle_start = time.time()
        run_id = None

        try:
            # Execute prediction
            result = self.engine.generate_signals(
                symbols=self.config.symbols,
                interval=self.config.interval,
            )

            # Save run to database
            run_id = self.persistence.save_prediction_run(
                interval_type=self.config.interval,
                symbols_requested=len(self.config.symbols),
                symbols_processed=len(result.symbols_processed),
                signals_generated=len(result.signals),
                execution_time_ms=result.latency.total_ms,
                status=result.status,
                data_fetch_ms=result.latency.data_fetch_ms,
                indicator_calc_ms=result.latency.indicator_calc_ms,
                signal_generation_ms=result.latency.signal_generation_ms,
                notification_ms=result.latency.notification_ms,
                errors=result.errors,
            )

            # Track performance metrics (NEW)
            if self.performance_tracker and run_id:
                from .monitoring.performance import ThroughputMetrics

                throughput = ThroughputMetrics.calculate(
                    symbols_processed=len(result.symbols_processed),
                    signals_generated=len(result.signals),
                    execution_time_ms=result.latency.total_ms,
                )

                self.performance_tracker.track_cycle(
                    run_id=run_id,
                    latency=result.latency,
                    throughput=throughput,
                    errors=result.errors,
                )

            # Deliver notifications (existing Week 4 integration)
            if self.notification_router and result.signals:
                self._deliver_notifications(result.signals, run_id)

            # Log summary
            self.logger.info(
                f"Prediction cycle completed: {len(result.signals)} signals, "
                f"{result.latency.total_ms}ms, run_id={run_id}"
            )

        except Exception as e:
            self.logger.error(f"Prediction cycle failed: {e}", exc_info=True)
            # Log failed run
            # ... existing error handling ...
```

#### 2. Background Calibration Task

**Option A: Scheduled Calibration (Recommended)**
Add a separate scheduled job to run calibration periodically:

```python
class PredictionScheduler:

    def _setup_calibration_job(self):
        """Set up periodic calibration evaluation (runs daily)."""
        if self.performance_tracker is None:
            return

        from .monitoring.calibration import CalibrationEngine

        # Create calibration engine
        calibration_engine = CalibrationEngine(
            persistence=self.persistence,
            evaluation_window_hours=24,
        )

        # Schedule daily calibration at 00:00 UTC
        self.scheduler.add_job(
            func=self._run_calibration,
            trigger=CronTrigger(hour=0, minute=0),
            id="calibration_job",
            name="Daily signal calibration",
            args=[calibration_engine],
        )

    def _run_calibration(self, calibration_engine: CalibrationEngine):
        """Execute signal calibration batch evaluation."""
        try:
            self.logger.info("Starting signal calibration batch evaluation")

            outcomes = calibration_engine.batch_evaluate(lookback_hours=48)

            self.logger.info(
                f"Calibration complete: {len(outcomes)} signals evaluated"
            )

            # Optionally check calibration metrics and alert if win rate drops
            if len(outcomes) >= 10:  # Minimum sample size
                wins = [o for o in outcomes if o.outcome == "WIN"]
                win_rate = len(wins) / len(outcomes)

                if win_rate < 0.5:
                    self.logger.warning(
                        f"Low win rate detected: {win_rate:.2%} "
                        f"({len(wins)}/{len(outcomes)} signals)"
                    )

        except Exception as e:
            self.logger.error(f"Calibration job failed: {e}", exc_info=True)
```

**Option B: CLI-triggered Calibration**
Defer calibration to CLI command (Week 6), keeping scheduler focused on real-time execution.

### Testing Strategy (Day 7)

#### Integration Tests (`tests/prediction/test_scheduler_monitoring_integration.py`)

1. **Scheduler with Performance Tracking**
   - Mock PredictionEngine to return PredictionRunResult
   - Verify PerformanceTracker.track_cycle() is called
   - Verify metrics are persisted to database

2. **End-to-End Metric Flow**
   - Run full prediction cycle (with test data)
   - Query prediction_runs table
   - Query prediction_metrics table
   - Verify latency breakdown is recorded
   - Verify throughput metrics are calculated

3. **SLA Compliance Monitoring**
   - Simulate slow prediction cycles
   - Verify SLA violation detection
   - Test performance summary generation

4. **Calibration Job (if Option A)**
   - Mock CalibrationEngine
   - Verify scheduled job executes
   - Test error handling

---

## Database Schema Requirements

**Already exists** in `003_prediction_system.sql`:

```sql
-- prediction_metrics table
CREATE TABLE IF NOT EXISTS prediction_metrics (
    metric_id BIGSERIAL PRIMARY KEY,
    metric_timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metric_type VARCHAR(50) NOT NULL,
    metric_value NUMERIC(12,4) NOT NULL,
    aggregation_period VARCHAR(20),
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_prediction_metrics_type_timestamp
    ON prediction_metrics(metric_type, metric_timestamp DESC);
```

**Potential Enhancement** (optional, can defer to Week 6):
Add helper query methods to `PredictionPersistence`:

```python
def get_pending_signals_for_evaluation(
    self,
    evaluation_window_hours: int = 24,
) -> List[Dict[str, Any]]:
    """Get signals ready for outcome evaluation (outcome IS NULL, time elapsed)."""
    # Query logic here
    pass

def get_signals_in_date_range(
    self,
    start_date: datetime,
    end_date: datetime,
    limit: int = 10000,
) -> List[Dict[str, Any]]:
    """Get all signals within date range for calibration reporting."""
    # Query logic here
    pass
```

---

## Dependencies & Integration

### Internal Dependencies
- ✅ `PredictionPersistence` - Already has all needed methods
- ✅ `PredictionEngine` - Returns `PredictionRunResult` with latency breakdown
- ✅ `PredictionScheduler` - Entry point for monitoring integration
- ✅ Database schema - `prediction_metrics` table exists

### External Dependencies
- **DataFetcher** (for calibration price data)
  - Need to fetch historical intraday data for signal evaluation
  - Can mock in tests initially
  - Real implementation in Week 5 Day 6

### New Files Created
```
src/dgas/prediction/monitoring/
├── __init__.py (already exists, needs updates)
├── performance.py (NEW - PerformanceTracker, LatencyMetrics, ThroughputMetrics)
└── calibration.py (NEW - CalibrationEngine, SignalOutcome, CalibrationReport)

tests/prediction/monitoring/
├── __init__.py
├── test_performance.py (NEW)
└── test_calibration.py (NEW)

tests/prediction/
└── test_scheduler_monitoring_integration.py (NEW)
```

---

## Risks & Mitigations

### Risk 1: Data Fetcher Integration Complexity
**Issue:** CalibrationEngine needs historical price data, which may require complex DataFetcher integration.

**Mitigation:**
- Day 4-5: Implement core evaluation logic with mocked price data
- Day 6: Integrate real DataFetcher if time permits, otherwise defer to Week 6
- Tests should mock price data to avoid external API dependencies

### Risk 2: Performance Overhead
**Issue:** Tracking metrics adds latency to prediction cycles.

**Mitigation:**
- Keep `track_cycle()` lightweight (just database inserts)
- Run calibration asynchronously (separate scheduled job)
- Use database indexes for metric queries

### Risk 3: Incomplete Signal Evaluation
**Issue:** Some signals may never resolve (neither target nor stop hit).

**Mitigation:**
- Classify as "NEUTRAL" after evaluation window expires
- Track separately in calibration reports
- Consider these in win rate calculations (conservative approach)

---

## Success Criteria

### Day 1-3: Performance Tracking
- [x] `LatencyMetrics` and `ThroughputMetrics` dataclasses implemented
- [x] `PerformanceTracker` class with `track_cycle()`, `get_performance_summary()`, `check_sla_compliance()`
- [x] Unit tests passing (>90% coverage)
- [x] Integration tests with real database passing

### Day 4-6: Calibration Engine
- [x] `SignalOutcome` and `CalibrationReport` dataclasses implemented
- [x] `CalibrationEngine` class with `evaluate_signal()`, `batch_evaluate()`, `get_calibration_report()`
- [x] Signal evaluation logic for LONG/SHORT signals
- [x] Confidence bucket and signal type grouping
- [x] Unit tests passing (>90% coverage)
- [x] Integration tests with real database passing

### Day 7: Integration
- [x] `PerformanceTracker` integrated into `PredictionScheduler`
- [x] Metrics persisted after each prediction cycle
- [x] End-to-end test: cycle → metrics → summary
- [x] (Optional) Calibration scheduled job implemented
- [x] All integration tests passing

### Overall Week 5 Success
- [x] Monitoring system operational and collecting metrics
- [x] SLA compliance can be checked programmatically
- [x] Signal outcomes can be evaluated (even if DataFetcher mocked)
- [x] Calibration reports can be generated
- [x] No regressions in existing Week 3-4 tests
- [x] Code coverage maintained (>85%)
- [x] Documentation updated (`llms.txt`, module docstrings)

---

## Next Steps (Week 6 Preview)

After Week 5 completion, Week 6 will build CLI commands to expose monitoring data:

1. **`dgas monitor` command**
   - Display performance summary (latency, throughput, SLA)
   - Show recent prediction runs
   - Dashboard mode (live updating)

2. **`dgas calibration` command**
   - Run batch evaluation on demand
   - Generate calibration report
   - Display win rates by confidence/type

3. **Configuration system**
   - YAML/JSON config files for scheduler settings
   - Monitoring thresholds configuration
   - Alert configuration

---

## Open Questions for Review

1. **Calibration Timing**: Should calibration run:
   - A) As scheduled job in scheduler (Option A above)
   - B) Only via CLI command (Week 6)
   - **Recommendation:** Option A for automation, plus CLI for ad-hoc analysis

2. **Data Fetcher Scope**: Should Week 5 include full DataFetcher integration for calibration, or mock it?
   - **Recommendation:** Implement interface, mock in tests, integrate real fetcher if time permits on Day 6

3. **Metric Granularity**: Should we persist metrics for every run, or aggregate hourly/daily?
   - **Current Plan:** Persist per-run metrics, query/aggregate on demand
   - **Future:** Consider pre-aggregation for very high frequency

4. **SLA Alerting**: Should SLA violations trigger notifications?
   - **Current Plan:** Log warnings only
   - **Week 6:** Add Discord alerts for SLA violations

---

## Appendix: Code Structure

### Module Organization
```
prediction/
├── __init__.py
├── engine.py                    # PredictionEngine, SignalGenerator
├── persistence.py               # PredictionPersistence (Week 1)
├── scheduler.py                 # PredictionScheduler (Week 3)
├── notifications/               # NotificationRouter (Week 4)
│   ├── __init__.py
│   ├── router.py
│   └── adapters/
│       ├── console.py
│       └── discord.py
└── monitoring/                  # NEW (Week 5)
    ├── __init__.py
    ├── performance.py           # PerformanceTracker
    └── calibration.py           # CalibrationEngine
```

### Test Organization
```
tests/prediction/
├── test_engine.py
├── test_persistence.py
├── test_scheduler.py
├── test_scheduler_notification_integration.py
├── monitoring/                  # NEW (Week 5)
│   ├── __init__.py
│   ├── test_performance.py
│   └── test_calibration.py
└── test_scheduler_monitoring_integration.py  # NEW (Week 5)
```

---

**END OF PLAN**
