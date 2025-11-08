"""Signal accuracy evaluation for backtesting.

Tracks predicted signals vs actual trade outcomes to measure signal accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from .entities import Trade
from ..prediction.engine import GeneratedSignal, SignalType


@dataclass
class SignalPrediction:
    """A predicted signal with its expected outcome."""

    signal_id: str
    symbol: str
    signal_timestamp: datetime
    signal_type: SignalType
    predicted_entry: Decimal
    predicted_stop_loss: Decimal
    predicted_target: Decimal
    confidence: float
    signal_strength: float


@dataclass
class SignalOutcome:
    """Actual outcome of a signal prediction."""

    signal_id: str
    actual_entry: Decimal | None = None
    actual_exit: Decimal | None = None
    actual_entry_time: datetime | None = None
    actual_exit_time: datetime | None = None
    trade_executed: bool = False
    trade_id: str | None = None
    pnl: Decimal | None = None
    hit_stop_loss: bool = False
    hit_target: bool = False
    exit_reason: str | None = None


@dataclass
class SignalAccuracyMetrics:
    """Accuracy metrics for signal evaluation."""

    total_signals: int
    executed_signals: int
    winning_signals: int
    losing_signals: int
    win_rate: float
    avg_confidence_winning: float
    avg_confidence_losing: float
    avg_confidence_all: float
    signals_by_type: Dict[str, int] = field(default_factory=dict)
    win_rate_by_type: Dict[str, float] = field(default_factory=dict)
    win_rate_by_confidence_bucket: Dict[str, float] = field(default_factory=dict)


class SignalEvaluator:
    """Evaluate signal accuracy by comparing predictions to actual outcomes."""

    def __init__(self):
        """Initialize signal evaluator."""
        self.predictions: Dict[str, SignalPrediction] = {}
        self.outcomes: Dict[str, SignalOutcome] = {}

    def register_signal(self, signal: GeneratedSignal) -> None:
        """Register a predicted signal.

        Args:
            signal: Generated signal from SignalGenerator
        """
        signal_id = f"{signal.symbol}_{signal.signal_timestamp.isoformat()}"
        
        prediction = SignalPrediction(
            signal_id=signal_id,
            symbol=signal.symbol,
            signal_timestamp=signal.signal_timestamp,
            signal_type=signal.signal_type,
            predicted_entry=signal.entry_price,
            predicted_stop_loss=signal.stop_loss,
            predicted_target=signal.target_price,
            confidence=signal.confidence,
            signal_strength=signal.signal_strength,
        )
        
        self.predictions[signal_id] = prediction
        
        # Initialize outcome
        self.outcomes[signal_id] = SignalOutcome(signal_id=signal_id)

    def register_trade(
        self,
        trade: Trade,
        signal_id: str | None = None,
    ) -> None:
        """Register a completed trade and match it to a signal.

        Args:
            trade: Completed trade
            signal_id: Optional signal ID if known
        """
        # Try to find matching signal by symbol and timestamp proximity
        if signal_id is None:
            signal_id = self._find_matching_signal(trade)
        
        if signal_id and signal_id in self.outcomes:
            outcome = self.outcomes[signal_id]
            outcome.trade_executed = True
            outcome.actual_entry = trade.entry_price
            outcome.actual_exit = trade.exit_price
            outcome.actual_entry_time = trade.entry_time
            outcome.actual_exit_time = trade.exit_time
            outcome.pnl = trade.net_profit
            outcome.trade_id = f"{trade.symbol}_{trade.entry_time.isoformat()}"
            
            # Check if stop loss or target was hit
            if signal_id in self.predictions:
                prediction = self.predictions[signal_id]
                
                # Determine exit reason
                if prediction.signal_type == SignalType.LONG:
                    if trade.exit_price <= prediction.predicted_stop_loss:
                        outcome.hit_stop_loss = True
                        outcome.exit_reason = "stop_loss"
                    elif trade.exit_price >= prediction.predicted_target:
                        outcome.hit_target = True
                        outcome.exit_reason = "target"
                elif prediction.signal_type == SignalType.SHORT:
                    if trade.exit_price >= prediction.predicted_stop_loss:
                        outcome.hit_stop_loss = True
                        outcome.exit_reason = "stop_loss"
                    elif trade.exit_price <= prediction.predicted_target:
                        outcome.hit_target = True
                        outcome.exit_reason = "target"

    def _find_matching_signal(self, trade: Trade) -> str | None:
        """Find signal that matches a trade.

        Args:
            trade: Trade to match

        Returns:
            Signal ID or None if not found
        """
        # Look for signals for this symbol around the entry time
        for signal_id, prediction in self.predictions.items():
            if prediction.symbol != trade.symbol:
                continue
            
            # Check if entry time is within 1 hour of signal time
            time_diff = abs((trade.entry_time - prediction.signal_timestamp).total_seconds())
            if time_diff <= 3600:  # 1 hour
                return signal_id
        
        return None

    def calculate_metrics(self) -> SignalAccuracyMetrics:
        """Calculate accuracy metrics.

        Returns:
            SignalAccuracyMetrics with calculated metrics
        """
        total_signals = len(self.predictions)
        executed_signals = sum(1 for o in self.outcomes.values() if o.trade_executed)
        winning_signals = sum(
            1 for o in self.outcomes.values()
            if o.trade_executed and o.pnl is not None and o.pnl > 0
        )
        losing_signals = sum(
            1 for o in self.outcomes.values()
            if o.trade_executed and o.pnl is not None and o.pnl <= 0
        )

        win_rate = winning_signals / executed_signals if executed_signals > 0 else 0.0

        # Calculate average confidence
        winning_confidences = [
            self.predictions[sid].confidence
            for sid, outcome in self.outcomes.items()
            if outcome.trade_executed and outcome.pnl is not None and outcome.pnl > 0
        ]
        losing_confidences = [
            self.predictions[sid].confidence
            for sid, outcome in self.outcomes.items()
            if outcome.trade_executed and outcome.pnl is not None and outcome.pnl <= 0
        ]
        all_confidences = [p.confidence for p in self.predictions.values()]

        avg_confidence_winning = (
            sum(winning_confidences) / len(winning_confidences)
            if winning_confidences else 0.0
        )
        avg_confidence_losing = (
            sum(losing_confidences) / len(losing_confidences)
            if losing_confidences else 0.0
        )
        avg_confidence_all = (
            sum(all_confidences) / len(all_confidences)
            if all_confidences else 0.0
        )

        # Signals by type
        signals_by_type: Dict[str, int] = {}
        win_rate_by_type: Dict[str, float] = {}
        
        for signal_type in [SignalType.LONG, SignalType.SHORT]:
            type_str = signal_type.value
            type_signals = [
                sid for sid, p in self.predictions.items()
                if p.signal_type == signal_type
            ]
            signals_by_type[type_str] = len(type_signals)
            
            type_executed = [
                sid for sid in type_signals
                if self.outcomes[sid].trade_executed
            ]
            type_winning = [
                sid for sid in type_executed
                if self.outcomes[sid].pnl is not None and self.outcomes[sid].pnl > 0
            ]
            win_rate_by_type[type_str] = (
                len(type_winning) / len(type_executed)
                if type_executed else 0.0
            )

        # Win rate by confidence bucket
        win_rate_by_confidence_bucket: Dict[str, float] = {}
        buckets = [(0.0, 0.5), (0.5, 0.7), (0.7, 0.85), (0.85, 1.0)]
        
        for low, high in buckets:
            bucket_name = f"{low:.0%}-{high:.0%}"
            bucket_signals = [
                sid for sid, p in self.predictions.items()
                if low <= p.confidence < high
            ]
            bucket_executed = [
                sid for sid in bucket_signals
                if self.outcomes[sid].trade_executed
            ]
            bucket_winning = [
                sid for sid in bucket_executed
                if self.outcomes[sid].pnl is not None and self.outcomes[sid].pnl > 0
            ]
            win_rate_by_confidence_bucket[bucket_name] = (
                len(bucket_winning) / len(bucket_executed)
                if bucket_executed else 0.0
            )

        return SignalAccuracyMetrics(
            total_signals=total_signals,
            executed_signals=executed_signals,
            winning_signals=winning_signals,
            losing_signals=losing_signals,
            win_rate=win_rate,
            avg_confidence_winning=avg_confidence_winning,
            avg_confidence_losing=avg_confidence_losing,
            avg_confidence_all=avg_confidence_all,
            signals_by_type=signals_by_type,
            win_rate_by_type=win_rate_by_type,
            win_rate_by_confidence_bucket=win_rate_by_confidence_bucket,
        )


__all__ = [
    "SignalEvaluator",
    "SignalPrediction",
    "SignalOutcome",
    "SignalAccuracyMetrics",
]
