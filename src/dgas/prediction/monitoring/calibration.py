"""
Signal calibration and accuracy validation.

This module evaluates generated trading signals against actual market outcomes
to measure prediction accuracy and track calibration metrics over time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ...data.models import IntervalData
from ..persistence import PredictionPersistence


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalOutcome:
    """
    Actual outcome of a generated signal after evaluation.

    Compares predicted signal levels (entry, stop, target) against
    actual price movement during the evaluation window.
    """
    signal_id: int
    evaluation_timestamp: datetime

    # Price movement within evaluation window
    actual_high: Decimal  # Highest price reached
    actual_low: Decimal  # Lowest price reached
    close_price: Decimal  # Final closing price

    # Outcome classification
    hit_target: bool  # Target price was reached
    hit_stop: bool  # Stop loss was hit
    outcome: str  # "WIN", "LOSS", "NEUTRAL", "PENDING"
    pnl_pct: float  # Percentage P&L if signal was taken

    # Context
    evaluation_window_hours: int
    signal_type: str  # LONG, SHORT (from original signal)


@dataclass(frozen=True)
class CalibrationReport:
    """
    Calibration metrics report for signal accuracy analysis.

    Provides comprehensive accuracy metrics grouped by confidence level
    and signal type to identify prediction quality patterns.
    """
    date_range: tuple[datetime, datetime]
    total_signals: int
    evaluated_signals: int

    # Overall metrics
    win_rate: float  # % of signals that hit target
    avg_pnl_pct: float  # Average P&L across all signals
    target_hit_rate: float  # % that hit target
    stop_hit_rate: float  # % that hit stop

    # By confidence bucket (e.g., 0.6-0.7, 0.7-0.8, 0.8-0.9, 0.9-1.0)
    by_confidence: Dict[str, Dict[str, float]]
    # Example: {"0.7-0.8": {"win_rate": 0.68, "avg_pnl": 0.023, "count": 45}}

    # By signal type (LONG vs SHORT)
    by_signal_type: Dict[str, Dict[str, float]]
    # Example: {"LONG": {"win_rate": 0.62, "avg_pnl": 0.019, "count": 78}}


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
        data_source: Optional[Any] = None,
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
        signal: Dict[str, Any],
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
                outcome = None
                pnl_pct = 0.0
                for bar in actual_prices:
                    if bar.low <= stop_loss:
                        outcome = "LOSS"
                        pnl_pct = float((stop_loss - entry_price) / entry_price * 100)
                        break
                    elif bar.high >= target_price:
                        outcome = "WIN"
                        pnl_pct = float((target_price - entry_price) / entry_price * 100)
                        break

                # Safety: if we couldn't determine order, use target as outcome
                if outcome is None:
                    outcome = "WIN"
                    pnl_pct = float((target_price - entry_price) / entry_price * 100)

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
                outcome = None
                pnl_pct = 0.0
                for bar in actual_prices:
                    if bar.high >= stop_loss:
                        outcome = "LOSS"
                        pnl_pct = float((entry_price - stop_loss) / entry_price * 100)
                        break
                    elif bar.low <= target_price:
                        outcome = "WIN"
                        pnl_pct = float((entry_price - target_price) / entry_price * 100)
                        break

                # Safety: if we couldn't determine order, use target as outcome
                if outcome is None:
                    outcome = "WIN"
                    pnl_pct = float((entry_price - target_price) / entry_price * 100)

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

        Args:
            lookback_hours: Hours to look back for signals to evaluate

        Returns:
            List of evaluated signal outcomes
        """
        # Get all recent signals (includes evaluated and pending)
        all_signals = self.persistence.get_recent_signals(
            lookback_hours=lookback_hours + self.evaluation_window_hours,
            limit=1000,
        )

        # Filter for pending evaluation (outcome is None)
        pending_signals = [s for s in all_signals if s["outcome"] is None]

        self.logger.info(
            f"Found {len(pending_signals)} signals pending evaluation "
            f"(out of {len(all_signals)} total)"
        )

        outcomes = []
        for signal in pending_signals:
            # Check if enough time has elapsed
            signal_timestamp = signal["signal_timestamp"]
            hours_elapsed = (
                datetime.now(timezone.utc) - signal_timestamp
            ).total_seconds() / 3600

            if hours_elapsed < self.evaluation_window_hours:
                self.logger.debug(
                    f"Signal {signal['signal_id']} not ready "
                    f"({hours_elapsed:.1f}h elapsed, need {self.evaluation_window_hours}h)"
                )
                continue  # Not ready for evaluation yet

            # Fetch actual price data
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

                self.logger.debug(
                    f"Evaluated signal {outcome.signal_id}: {outcome.outcome} "
                    f"(P&L: {outcome.pnl_pct:.2f}%)"
                )

            except Exception as e:
                self.logger.error(f"Failed to evaluate signal {signal['signal_id']}: {e}")
                continue

        self.logger.info(f"Calibration complete: {len(outcomes)} signals evaluated")
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

        # Get all signals in range
        lookback_hours = int((end_date - start_date).total_seconds() / 3600)
        all_signals = self.persistence.get_recent_signals(
            lookback_hours=lookback_hours,
            limit=10000,
        )

        # Filter to date range and evaluated signals
        evaluated_signals = [
            s
            for s in all_signals
            if s["outcome"] is not None
            and s["outcome"] != "PENDING"
            and start_date <= s["signal_timestamp"] <= end_date
        ]

        total_signals = len(
            [s for s in all_signals if start_date <= s["signal_timestamp"] <= end_date]
        )
        evaluated_count = len(evaluated_signals)

        if evaluated_count == 0:
            return self._empty_report(date_range)

        # Overall metrics
        wins = [s for s in evaluated_signals if s["outcome"] == "WIN"]
        win_rate = len(wins) / evaluated_count

        avg_pnl = sum(s["pnl_pct"] for s in evaluated_signals) / evaluated_count

        # Target and stop hit rates
        target_hits = len(wins)  # WIN means target hit
        target_hit_rate = target_hits / evaluated_count

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
        For Week 5, this returns empty list and should be mocked in tests.
        Real implementation will be added when DataFetcher integration is ready.

        Args:
            symbol: Symbol to fetch data for
            start_time: Start of evaluation window
            hours: Duration in hours

        Returns:
            List of IntervalData for the evaluation window
        """
        if self.data_source is None:
            self.logger.warning(
                f"No data source configured for calibration - "
                f"cannot fetch prices for {symbol}"
            )
            return []

        # Note: Price data fetching integration needed
        # This requires connecting to the data ingestion layer
        # End time for the window
        # end_time = start_time + timedelta(hours=hours)
        # return self.data_source.fetch_intraday(symbol, start_time, end_time, interval="5min")

        raise NotImplementedError(
            "Price data fetching not yet implemented - "
            "integrate with DataFetcher or mock in tests"
        )

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


__all__ = [
    "SignalOutcome",
    "CalibrationReport",
    "CalibrationEngine",
]
